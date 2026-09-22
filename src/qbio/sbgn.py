"""
SBGN-ML Process Description emitter.

Why SBGN-ML rather than a bespoke format: it is a real standard, so a QBM map
opens in Newt, VANTED/SBGN-ED, CySBGN and SBGNviz, and — the immediate reason —
in the SBGN Pathway Visualizer already published at
https://dr-richard-barker.github.io/SBGN-Pathway-viewer/app/ , which renders
SBGN-ML deterministically from the file's own geometry and overlays omics data
on it. Emitting SBGN means the atlas inherits a working viewer instead of
shipping another one.

SBGN PD has no vocabulary for "this macromolecule carries a [4Fe-4S] cluster
whose hyperfine coupling could make it field-sensitive". That is what the
`<extension>` element is for: each glyph carries a `<qbo:annotation>` block with
its quantum class, evidence tier and citations. Renderers that do not understand
it ignore it, which is exactly the required behaviour — the map stays valid SBGN
and degrades to an ordinary pathway diagram.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Iterable, Sequence

from .layout import LaidOutNode

SBGN_NS = "http://sbgn.org/libsbgn/0.3"
QBO_NS = "https://dr-richard-barker.github.io/quantum-biology-atlas/qbo/1.0"

#: QBO `kind` -> SBGN PD glyph class. SBGN's vocabulary is fixed, so anything
#: without a natural home becomes an annotated `unspecified entity` rather than
#: an invented class that would break validation.
KIND_TO_GLYPH = {
    "macromolecule": "macromolecule",
    "complex": "complex",
    "simple_chemical": "simple chemical",
    "cofactor": "simple chemical",
    "process": "process",
    "phenotype": "phenotype",
    "compartment": "compartment",
    "perturbation": "perturbing agent",
}

#: QBO edge class -> SBGN PD arc class.
EDGE_TO_ARC = {
    "electron_transfer": "consumption",
    "catalysis": "catalysis",
    "cofactor_insertion": "catalysis",
    "inhibition": "inhibition",
    "direct_influence": "stimulation",
    "indirect_influence": "modulation",
    "hormonal_feedback": "modulation",
    "circadian_feedback": "modulation",
    "redox_feedback": "modulation",
    "energy_feedback": "modulation",
}


def _bbox(el: ET.Element, x: float, y: float, w: float, h: float) -> None:
    ET.SubElement(
        el,
        "bbox",
        {"x": f"{x:.2f}", "y": f"{y:.2f}", "w": f"{w:.2f}", "h": f"{h:.2f}"},
    )


def _annotation(glyph: ET.Element, payload: dict) -> None:
    """Attach the QBO annotation as an SBGN <extension>.

    Standard-compliant and ignorable: a renderer that does not know QBO still
    sees a valid glyph.
    """
    ext = ET.SubElement(glyph, "extension")
    ann = ET.SubElement(ext, f"{{{QBO_NS}}}annotation", {"xmlns:qbo": QBO_NS})
    if payload.get("qbo"):
        ann.set("entity", payload["qbo"])
    ann.set("evidenceTier", payload.get("evidence_tier", "T4"))
    if payload.get("confidence"):
        ann.set("confidence", payload["confidence"])
    for cls in payload.get("quantum_class", ()):
        ET.SubElement(ann, f"{{{QBO_NS}}}quantumClass").text = cls
    for nucleus in payload.get("nuclei", ()):
        ET.SubElement(ann, f"{{{QBO_NS}}}nucleus").text = nucleus
    for cofactor in payload.get("cofactors", ()):
        ET.SubElement(ann, f"{{{QBO_NS}}}cofactor").text = cofactor
    for ns, ids in (payload.get("xref") or {}).items():
        for ident in ids:
            ET.SubElement(ann, f"{{{QBO_NS}}}xref", {"db": ns}).text = ident
    for ev in payload.get("evidence", ()):
        e = ET.SubElement(ann, f"{{{QBO_NS}}}evidence")
        e.set("ref", ev.get("ref", ""))
        if ev.get("doi"):
            e.set("doi", ev["doi"])
        if ev.get("direction"):
            e.set("direction", ev["direction"])
        if ev.get("field_regime"):
            e.set("fieldRegime", ev["field_regime"])
        e.text = ev.get("claim", "")
    if payload.get("rationale"):
        ET.SubElement(ann, f"{{{QBO_NS}}}rationale").text = payload["rationale"]
    if payload.get("caveat"):
        ET.SubElement(ann, f"{{{QBO_NS}}}caveat").text = payload["caveat"]


def build(
    *,
    map_id: str,
    title: str,
    nodes: Sequence[LaidOutNode],
    edges: Sequence[tuple[str, str, str, str]],
    compartments: Sequence[tuple[str, str, object]] = (),
    notes: str = "",
) -> str:
    """Emit an SBGN-ML PD document as a string.

    `edges` items are (source_id, target_id, edge_class, label).
    `compartments` items are (compartment_id, label, Box).
    """
    ET.register_namespace("", SBGN_NS)
    ET.register_namespace("qbo", QBO_NS)

    sbgn = ET.Element(f"{{{SBGN_NS}}}sbgn")
    pmap = ET.SubElement(sbgn, "map", {"id": map_id, "language": "process description"})

    if notes:
        ext = ET.SubElement(pmap, "extension")
        ET.SubElement(ext, f"{{{QBO_NS}}}mapNotes", {"xmlns:qbo": QBO_NS}).text = notes

    # Compartments first: SBGN requires a glyph's compartmentRef to be declared
    # before it is referenced.
    declared: set[str] = set()
    for cid, clabel, box in compartments:
        g = ET.SubElement(pmap, "glyph", {"id": cid, "class": "compartment"})
        ET.SubElement(g, "label", {"text": clabel})
        _bbox(g, box.x, box.y, box.w, box.h)
        declared.add(cid)

    for n in nodes:
        glyph_class = KIND_TO_GLYPH.get(n.payload.get("kind", "macromolecule"), "unspecified entity")
        attrs = {"id": n.id, "class": glyph_class}
        comp = n.payload.get("compartment")
        if comp and comp in declared:
            attrs["compartmentRef"] = comp
        g = ET.SubElement(pmap, "glyph", attrs)
        ET.SubElement(g, "label", {"text": n.payload.get("label") or n.id})
        _bbox(g, n.box.x, n.box.y, n.box.w, n.box.h)

        # Cofactors ride as SBGN unit-of-information glyphs, which is how a
        # reader sees "[4Fe-4S]" on the box itself rather than only in a tooltip.
        for i, unit in enumerate(n.payload.get("units", ())):
            u = ET.SubElement(g, "glyph", {"id": f"{n.id}__u{i}", "class": "unit of information"})
            ET.SubElement(u, "label", {"text": unit})
            _bbox(u, n.box.x + 6, n.box.y - 9, max(30.0, 7.0 * len(unit)), 16.0)

        _annotation(g, n.payload)

    for i, (src, tgt, edge_class, label) in enumerate(edges):
        arc_class = EDGE_TO_ARC.get(edge_class, "modulation")
        a = ET.SubElement(
            pmap, "arc", {"id": f"arc{i}", "class": arc_class, "source": src, "target": tgt}
        )
        by_id = {n.id: n for n in nodes}
        s, t = by_id.get(src), by_id.get(tgt)
        if s and t:
            ET.SubElement(a, "start", {"x": f"{s.box.cx:.2f}", "y": f"{s.box.cy:.2f}"})
            ET.SubElement(a, "end", {"x": f"{t.box.cx:.2f}", "y": f"{t.box.cy:.2f}"})
        if label:
            ET.SubElement(a, "glyph", {"id": f"arc{i}__lbl", "class": "annotation"}).append(
                ET.Element("label", {"text": label})
            )
        ext = ET.SubElement(a, "extension")
        ET.SubElement(
            ext, f"{{{QBO_NS}}}edgeClass", {"xmlns:qbo": QBO_NS}
        ).text = edge_class

    ET.indent(sbgn, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(sbgn, encoding="unicode")


def parse_check(xml_text: str) -> dict:
    """Re-parse emitted SBGN and report structure. Used by the round-trip test."""
    root = ET.fromstring(xml_text)
    ns = {"s": SBGN_NS}
    pmap = root.find("s:map", ns)
    if pmap is None:                       # namespace-stripped fallback
        pmap = root.find("map")
    glyphs = pmap.findall("glyph") + pmap.findall("s:glyph", ns)
    arcs = pmap.findall("arc") + pmap.findall("s:arc", ns)
    return {
        "language": pmap.get("language"),
        "glyphs": len(glyphs),
        "arcs": len(arcs),
        "classes": sorted({g.get("class") for g in glyphs}),
        "glyph_ids": [g.get("id") for g in glyphs],
    }
