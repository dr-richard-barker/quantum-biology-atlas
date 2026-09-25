"""
QBM maps: parse the declarative source, lay it out, emit SBGN-ML and SVG.

A map source names *what is on the diagram and how it is grouped*; it never
names a coordinate. Geometry is derived — box size from measured text, position
from lane order — which is what stops a label from outgrowing its box and two
boxes from landing on top of each other.

A node usually carries only an id and a `qbo:` reference; its label, kind,
compartment, quantum classes and evidence tier are pulled from the ontology, so
the same entity cannot say one thing on QBM-01 and another on QBM-05.
"""
from __future__ import annotations

import dataclasses
import pathlib
import re
from typing import Sequence

import yaml

from . import render, sbgn
from .layout import (
    COMPARTMENT_PAD,
    MIN_GUTTER_X,
    MIN_GUTTER_Y,
    Box,
    LaidOutNode,
    bounding_box,
    place_rows,
    resolve_collisions,
    size_node,
)
from .ontology import Ontology, OntologyError

ROOT = pathlib.Path(__file__).resolve().parents[2]
MAP_SRC_DIR = ROOT / "maps" / "src"
MAP_OUT_DIR = ROOT / "maps"

#: Clear visual separation between two adjacent compartment bands, on top of the
#: padding each one already reserves. Without this they would merely touch.
BAND_SEPARATION = 18.0

COMPARTMENT_LABEL = {
    "mitochondrial_matrix": "Mitochondrial matrix",
    "mitochondrial_inner_membrane": "Inner mitochondrial membrane",
    "mitochondrial_intermembrane_space": "Intermembrane space",
    "mitochondrion": "Mitochondrion",
    "chloroplast_stroma": "Chloroplast stroma",
    "thylakoid_membrane": "Thylakoid membrane",
    "thylakoid_lumen": "Thylakoid lumen",
    "chloroplast": "Chloroplast",
    "cytosol": "Cytosol",
    "nucleus": "Nucleus",
    "peroxisome": "Peroxisome",
    "plasma_membrane": "Plasma membrane",
    "apoplast": "Apoplast",
    "vacuole": "Vacuole",
    "endoplasmic_reticulum": "Endoplasmic reticulum",
    "cell": "Cell",
    "organism": "Organism",
    "environment": "Environment",
}


class MapError(Exception):
    """Raised when a map source is inconsistent. Never warned, always raised."""


@dataclasses.dataclass
class MapSpec:
    id: str
    title: str
    subtitle: str
    caption: str
    derived_from: str
    species_anchor: str
    lanes: list[dict]
    nodes: dict[str, dict]
    edges: list[tuple[str, str, str, str]]
    source_path: pathlib.Path

    @property
    def node_ids(self) -> list[str]:
        return [nid for lane in self.lanes for nid in lane.get("nodes", [])]


def load_spec(path: pathlib.Path) -> MapSpec:
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    for field in ("id", "title", "lanes"):
        if field not in doc:
            raise MapError(f"{path.name}: map is missing required field {field!r}")

    nodes = {n["id"]: n for n in (doc.get("nodes") or [])}
    edges = []
    for e in doc.get("edges") or []:
        if isinstance(e, dict):
            edges.append((e["from"], e["to"], e.get("class", "direct_influence"), e.get("label", "")))
        elif isinstance(e, (list, tuple)) and len(e) >= 3:
            edges.append((e[0], e[1], e[2], e[3] if len(e) > 3 else ""))
        else:
            raise MapError(f"{path.name}: cannot parse edge {e!r}")

    return MapSpec(
        id=doc["id"],
        title=doc["title"],
        subtitle=doc.get("subtitle", ""),
        caption=doc.get("caption", ""),
        derived_from=doc.get("derived_from", ""),
        species_anchor=doc.get("species_anchor", "arabidopsis_thaliana"),
        lanes=doc["lanes"],
        nodes=nodes,
        edges=edges,
        source_path=path,
    )


def _node_payload(spec: MapSpec, nid: str, onto: Ontology) -> dict:
    """Merge the map's node declaration with its ontology entity.

    The ontology wins on anything it defines, so an entity cannot claim one
    evidence tier on one map and a different tier on another. The map may only
    add presentation (an override label, unit-of-information chips).
    """
    decl = spec.nodes.get(nid, {})
    payload: dict = {
        "label": decl.get("label") or nid.replace("_", " "),
        "sublabel": decl.get("sublabel", ""),
        "kind": decl.get("kind", "macromolecule"),
        "evidence_tier": "T4",
        "quantum_class": (),
        "nuclei": (),
        "cofactors": (),
        "xref": {},
        "evidence": (),
        "units": tuple(decl.get("units") or ()),
        "compartment": decl.get("compartment"),
    }

    qbo_id = decl.get("qbo")
    if qbo_id:
        try:
            ent = onto[qbo_id]
        except OntologyError as exc:
            raise MapError(f"{spec.source_path.name}: node {nid!r} -> {exc}") from None
        payload.update(
            {
                "qbo": ent.id,
                "label": decl.get("label") or ent.label,
                "kind": ent.kind,
                "evidence_tier": ent.evidence_tier,
                "confidence": ent.confidence,
                "quantum_class": ent.quantum_class,
                "nuclei": ent.nuclei,
                "cofactors": ent.cofactors,
                "xref": {k: list(v) for k, v in ent.xref.items()},
                "compartment": decl.get("compartment") or ent.compartment,
                "rationale": ent.rationale,
                "caveat": ent.caveat,
                "evidence": tuple(
                    {
                        "ref": ev.ref,
                        "claim": ev.claim,
                        "direction": ev.direction,
                        "field_regime": ev.field_regime,
                        "doi": (onto.references.get(ev.ref) or {}).get("doi", ""),
                    }
                    for ev in ent.evidence
                ),
            }
        )
        # The sublabel carries the identifier a reader would need to look it up.
        if not payload["sublabel"] and ent.agi:
            payload["sublabel"] = " · ".join(ent.agi[:3]) + ("…" if len(ent.agi) > 3 else "")
        payload["tooltip"] = _tooltip(ent, onto)
    else:
        payload["tooltip"] = payload["label"]

    return payload


def _tooltip(ent, onto: Ontology) -> str:
    bits = [ent.label, f"tier {ent.evidence_tier} ({ent.confidence})"]
    if ent.quantum_class:
        bits.append("quantum class: " + ", ".join(ent.quantum_class))
    if ent.nuclei:
        bits.append("nuclei: " + ", ".join(ent.nuclei))
    if ent.agi:
        bits.append("AGI: " + ", ".join(ent.agi))
    for ev in ent.evidence:
        doi = (onto.references.get(ev.ref) or {}).get("doi", "")
        bits.append(f"{ev.ref}: {ev.claim}" + (f" [{doi}]" if doi else ""))
    if ent.rationale:
        bits.append("rationale: " + ent.rationale)
    if ent.caveat:
        bits.append("caveat: " + ent.caveat)
    return "\n".join(bits)


def layout_map(
    spec: MapSpec, onto: Ontology, *, reserve_bottom: float = 0.0
) -> tuple[list[LaidOutNode], list[tuple], Box]:
    """Measure, size and place every node. Returns (nodes, compartment boxes, canvas).

    `reserve_bottom` grows every node box by that much and keeps the text centred in
    the remaining height, so a time-course sparkline has somewhere to live that is not
    on top of the node's own identifiers. Geometry still follows content — the content
    simply now includes the data strip.
    """
    seen: set[str] = set()
    rows: list[list[LaidOutNode]] = []
    all_nodes: list[LaidOutNode] = []

    for lane in spec.lanes:
        row: list[LaidOutNode] = []
        for nid in lane.get("nodes", []):
            if nid in seen:
                raise MapError(f"{spec.source_path.name}: node {nid!r} appears in more than one lane")
            seen.add(nid)
            payload = _node_payload(spec, nid, onto)
            if lane.get("compartment") and not payload.get("compartment"):
                payload["compartment"] = lane["compartment"]

            box, lines, sublines = size_node(
                payload["label"],
                render.NODE_SIZE,
                sublabel=payload["sublabel"],
                sub_font_size=render.SUB_SIZE,
                preferred_width=float(lane.get("node_width", 186)),
            )
            box.h += reserve_bottom
            node = LaidOutNode(
                id=nid,
                box=box,
                reserve_bottom=reserve_bottom,
                lines=lines,
                font_size=render.NODE_SIZE,
                font_weight="600",
                sublines=sublines,
                sub_font_size=render.SUB_SIZE,
                lane=lane.get("id"),
                payload=payload,
            )
            row.append(node)
            all_nodes.append(node)
        rows.append(row)

    unknown = {nid for e in spec.edges for nid in (e[0], e[1])} - seen
    if unknown:
        raise MapError(
            f"{spec.source_path.name}: edges reference node(s) not placed in any lane: "
            f"{sorted(unknown)}"
        )

    # Vertical gutters are per-gap, not uniform.
    #
    # A compartment band is drawn COMPARTMENT_PAD below its last node and
    # COMPARTMENT_PAD + COMPARTMENT_LABEL_BAND above its first. So where the
    # compartment changes between two lanes, the gap has to swallow both paddings
    # AND the label band, or the two bands overlap — which they did, by exactly the
    # 12px this arithmetic predicts. Derive the figure instead of guessing it, so it
    # stays correct if the padding constants change.
    within_gutter = MIN_GUTTER_Y + 30.0        # room for unit chips between lanes
    boundary_gutter = (
        2 * COMPARTMENT_PAD + render.COMPARTMENT_LABEL_BAND + BAND_SEPARATION
    )
    lane_compartments = [lane.get("compartment") for lane in spec.lanes]
    gutters = [
        boundary_gutter if lane_compartments[i] != lane_compartments[i + 1] else within_gutter
        for i in range(len(rows) - 1)
    ]

    place_rows(
        rows,
        origin_x=0.0,
        origin_y=0.0,
        gutter_x=MIN_GUTTER_X,
        gutter_y=gutters,
    )
    resolve_collisions(all_nodes)

    # Compartment boxes are drawn per CONTIGUOUS RUN of lanes, not per compartment.
    #
    # The mitochondrial matrix legitimately appears both above and below the inner
    # membrane. Drawing one box around every matrix node would stretch it over the
    # membrane lanes in between and swallow the whole diagram — which is exactly
    # what the first build did. Two separate bands is both prettier and more honest
    # about the topology.
    # The band follows the LANE's declared compartment — that is the author's
    # grouping intent. A node whose ontology compartment differs from its lane
    # then gets its own smaller box nested inside, which is how cytochrome c reads
    # as intermembrane space while sitting in the membrane band.
    lane_comp: list[tuple[str | None, list[LaidOutNode]]] = []
    for lane in spec.lanes:
        members = [n for n in all_nodes if n.lane == lane.get("id")]
        if not members:
            continue
        declared = lane.get("compartment")
        if not declared:
            seen_comps = {n.payload.get("compartment") for n in members}
            declared = seen_comps.pop() if len(seen_comps) == 1 else None
        lane_comp.append((declared, members))

    comps: list[tuple[str, str, Box]] = []
    run_comp: str | None = None
    run_members: list[LaidOutNode] = []

    def _flush() -> None:
        if run_comp and run_members:
            b = bounding_box(run_members, pad=COMPARTMENT_PAD)
            comps.append((run_comp, COMPARTMENT_LABEL.get(run_comp, run_comp.replace("_", " ").title()), b))

    for cid, members in lane_comp:
        if cid == run_comp:
            run_members.extend(members)
        else:
            _flush()
            run_comp, run_members = cid, list(members)
    _flush()

    # A node whose own compartment differs from its lane's is tagged on the node
    # itself rather than wrapped in a nested box. Nested boxes were tried first and
    # were worse: their labels landed on top of the parent band's label and on the
    # unit chips, reintroducing exactly the overlap this pipeline exists to prevent.
    for lane_cid, members in lane_comp:
        for n in members:
            c = n.payload.get("compartment")
            if c and c != lane_cid:
                n.payload["compartment_tag"] = COMPARTMENT_LABEL.get(
                    c, c.replace("_", " ").title()
                )

    # The canvas is the union of node boxes, their unit chips and every
    # compartment box, so nothing can be clipped by the viewBox.
    canvas = bounding_box(all_nodes, pad=COMPARTMENT_PAD + 26.0)
    extras = [
        Box(b.x - 14.0, b.y - render.COMPARTMENT_LABEL_BAND - 14.0,
            b.w + 28.0, b.h + render.COMPARTMENT_LABEL_BAND + 28.0)
        for _, _, b in comps
    ]
    extras += [
        u.expanded(6.0)
        for u in (render.unit_row_box(n) for n in all_nodes)
        if u is not None
    ]
    for padded in extras:
        x1 = min(canvas.x, padded.x)
        y1 = min(canvas.y, padded.y)
        canvas = Box(x1, y1, max(canvas.x2, padded.x2) - x1, max(canvas.y2, padded.y2) - y1)
    return all_nodes, comps, canvas


def render_svg(
    spec: MapSpec, nodes: Sequence[LaidOutNode], comps: Sequence[tuple], canvas: Box
) -> tuple[str, dict]:
    """Render the map. Returns (svg, stats) — stats records any dropped edge label."""
    by_id = {n.id: n for n in nodes}
    # Edge labels must avoid node boxes AND their unit chips.
    obstacles: list[Box] = [n.box for n in nodes]
    obstacles += [b for b in (render.unit_row_box(n) for n in nodes) if b is not None]
    obstacles += [
        Box(box.x, box.y - render.COMPARTMENT_LABEL_BAND, box.w, render.COMPARTMENT_LABEL_BAND)
        for _cid, _lbl, box in comps
    ]

    body: list[str] = []
    for cid, label, box in comps:
        body.append(render.compartment_svg(box, cid, label))

    dropped: list[str] = []
    for src, tgt, cls, label in spec.edges:
        svg, drawn = render.edge_svg(by_id[src], by_id[tgt], cls, label, obstacles=obstacles)
        body.append(svg)
        if label and not drawn:
            dropped.append(f"{src}->{tgt}: {label!r}")

    for n in nodes:
        body.append(render.node_svg(n))
        body.append(render.unit_chips_svg(n))
        body.append(render.compartment_tag_svg(n))

    tiers = sorted({n.payload.get("evidence_tier", "T4") for n in nodes})
    legend, legend_h = render.tier_legend_svg(x=16.0, y=0.0, tiers_present=tiers)

    caption = spec.caption
    if spec.derived_from:
        caption = f"{caption} Derived from: {spec.derived_from}."
    counts = {t: sum(1 for n in nodes if n.payload.get("evidence_tier") == t) for t in tiers}
    caption += "  Node counts by evidence tier: " + ", ".join(f"{t}={counts[t]}" for t in tiers) + "."
    caption += (
        " Schematic topology only — no quantitative value is encoded in this base map;"
        " numbers appear only when measured data is projected onto it."
    )

    svg = render.document(
        title=f"{spec.id} · {spec.title}",
        subtitle=spec.subtitle,
        caption=caption.strip(),
        body="".join(body),
        canvas=canvas,
        legend=legend,
        legend_h=legend_h,
    )
    return svg, {"dropped_edge_labels": dropped}


def compile_map(path: pathlib.Path, onto: Ontology, out_dir: pathlib.Path = MAP_OUT_DIR) -> dict:
    """Compile one map source to SBGN-ML + SVG. Returns a build record."""
    spec = load_spec(path)
    nodes, comps, canvas = layout_map(spec, onto)

    svg, stats = render_svg(spec, nodes, comps, canvas)
    xml = sbgn.build(
        map_id=spec.id,
        title=spec.title,
        nodes=nodes,
        edges=spec.edges,
        compartments=comps,
        notes=f"{spec.title}. {spec.caption} Derived from: {spec.derived_from}",
    )

    (out_dir / "sbgn").mkdir(parents=True, exist_ok=True)
    (out_dir / "svg").mkdir(parents=True, exist_ok=True)
    sbgn_path = out_dir / "sbgn" / f"{spec.id}.sbgn"
    svg_path = out_dir / "svg" / f"{spec.id}.svg"
    sbgn_path.write_text(xml, encoding="utf-8")
    svg_path.write_text(svg, encoding="utf-8")

    tiers = {}
    for n in nodes:
        t = n.payload.get("evidence_tier", "T4")
        tiers[t] = tiers.get(t, 0) + 1

    return {
        "id": spec.id,
        "title": spec.title,
        "subtitle": spec.subtitle,
        "caption": spec.caption,
        "derived_from": spec.derived_from,
        "species_anchor": spec.species_anchor,
        "nodes": len(nodes),
        "edges": len(spec.edges),
        "compartments": [c[0] for c in comps],
        "tiers": tiers,
        "annotated_nodes": sum(1 for n in nodes if n.payload.get("qbo")),
        "agi_loci": sorted({a for n in nodes for a in n.payload.get("xref", {}).get("agi", [])}),
        "sbgn": str(sbgn_path.relative_to(ROOT)),
        "svg": str(svg_path.relative_to(ROOT)),
        "width": round(canvas.w, 1),
        "height": round(canvas.h, 1),
        # Reported, not swallowed: a label that could not be placed without
        # covering a node is dropped, and the build says which.
        "dropped_edge_labels": stats["dropped_edge_labels"],
    }


def compile_all(onto: Ontology, src_dir: pathlib.Path = MAP_SRC_DIR, out_dir: pathlib.Path = MAP_OUT_DIR) -> list[dict]:
    records = [compile_map(p, onto, out_dir) for p in sorted(src_dir.glob("*.yaml"))]
    if not records:
        raise MapError(f"no map sources found in {src_dir} — nothing was built")
    return records


def render_projection(
    spec: MapSpec,
    onto: Ontology,
    projection,
    out_dir: pathlib.Path = MAP_OUT_DIR,
    vmax: float | None = None,
) -> dict:
    """Render a map with measured data overlaid, and write it beside the base map.

    The base map is laid out exactly as before — the overlay is a CSS layer keyed on
    each node's reserved slot, so geometry never changes for a data run and the same
    base map can carry any number of studies.

    The provenance paragraph is appended to the caption, not attached separately.
    A figure that leaves the building must say what data is on it.
    """
    nodes, comps, canvas = layout_map(spec, onto)
    values = projection.values
    if not values:
        raise MapError(f"{spec.id}: projection carries no values — nothing to overlay")

    limit = vmax if vmax is not None else max(abs(v.value) for v in values.values())
    if limit <= 0:
        raise MapError(
            f"{spec.id}: every projected value is 0.0, so the colour scale would be "
            f"degenerate. Check the contrast — this is almost certainly a join failure."
        )

    svg, stats = render_svg(spec, nodes, comps, canvas)

    # Mark measured nodes in the drawing itself: a ring for significance, and the
    # value printed, because colour alone should never be the only channel.
    extra = [render.overlay_svg(values, limit)]
    marks = []
    by_id = {n.id: n for n in nodes}
    for nid, nv in values.items():
        n = by_id.get(nid)
        if n is None:
            continue
        txt = f"{nv.value:+.2f}" + ("*" if nv.significant else "")
        w = render.measure(txt, render.UNIT_SIZE)[0] + 2 * render.UNIT_PAD_X
        x = n.box.x2 - w / 2.0
        y = n.box.y2 - render.UNIT_H / 2.0
        marks.append(
            f'<g class="qbm-value" data-value-for="{render.esc(nid)}">'
            f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{render.UNIT_H}" '
            f'rx="7" class="qbm-unit"/>'
            f'<text class="qbm-unit-label" x="{x + w/2:.2f}" y="{y + render.UNIT_H - 4:.2f}" '
            f'text-anchor="middle">{render.esc(txt)}</text></g>'
        )

    caption_add = (
        " " + projection.provenance()
        + " An asterisk marks a node with at least one locus significant at the stated "
        "threshold. Colour intensity encodes magnitude; a node with no measurement is "
        "left unfilled and is not the same as a measured zero."
    )
    # The marks are positioned from node boxes, which are in LAYOUT coordinates, while
    # anything appended before `</svg>` is in document coordinates. They differ by the
    # header height, so a mark appended directly lands well away from its node. Emitting
    # them as a sibling group with the body's own transform puts them back on the map.
    tf = render.body_transform(svg)
    overlay_css = "".join(extra)
    svg = svg.replace(
        "</svg>", f'{overlay_css}<g transform="{tf}">{"".join(marks)}</g></svg>'
    )
    svg = _append_caption(svg, caption_add, vmax=limit)

    (out_dir / "svg").mkdir(parents=True, exist_ok=True)
    stem = f"{spec.id}__{_slug(projection.study)}"
    path = out_dir / "svg" / f"{stem}.svg"
    path.write_text(svg, encoding="utf-8")

    return {
        "id": spec.id,
        "study": projection.study,
        "contrast": projection.contrast,
        "organism": projection.organism,
        "svg": str(path.relative_to(ROOT)),
        "nodes_with_data": projection.nodes_with_data,
        "fraction_covered": round(projection.fraction_covered, 4),
        "vmax": round(limit, 4),
        "provenance": projection.provenance(),
        "dropped_edge_labels": stats["dropped_edge_labels"],
    }


def _slug(text: str) -> str:
    import re

    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-")[:60]


def _append_caption(svg: str, extra: str, vmax: float | None = None,
                    extra_legend=None) -> str:
    """Re-render the caption with the provenance appended, then the colour bar.

    The caption is re-wrapped rather than having a line tacked on, so the added text
    obeys the same width and the figure does not grow a line that runs off the edge.
    The colour bar goes in reserved space BELOW the finished caption and the page
    grows to fit it — trying to tuck it into whatever looked empty put it over a
    compartment label, then over the title.
    """
    import re

    m = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg)
    if not m:
        return svg
    width, height = float(m.group(1)), float(m.group(2))

    import html

    caption_tags = re.findall(r'<text class="qbm-caption"[^>]*>(.*?)</text>', svg)
    # Unescape before re-wrapping: this text came back out of the SVG already
    # escaped, and escaping it again yields "Porterfield &amp;amp; Barker".
    existing = html.unescape(" ".join(caption_tags))
    lines, _, _ = render._caption_block(existing + extra, width - 32)

    first = re.search(r'<text class="qbm-caption" x="16" y="([\d.]+)"', svg)
    if not first:
        return svg
    start_y = float(first.group(1))

    svg = re.sub(r'<text class="qbm-caption"[^>]*>.*?</text>\s*', "", svg)
    block = []
    y = start_y
    for line in lines:
        block.append(f'<text class="qbm-caption" x="16" y="{y:.2f}">{render.esc(line)}</text>')
        y += render.CAPTION_SIZE * render.LINE_SPACING
    legend_svg = ""
    if vmax is not None:
        legend_svg, legend_h = render.overlay_legend_svg(
            x=16.0, y=y + 10.0, vmax=vmax, label="log2 fold change (measured)"
        )
        y += 10.0 + legend_h
    # A downloaded SVG has to explain its own marks; the page's prose does not travel
    # with the file.
    if extra_legend is not None:
        more_svg, more_h = extra_legend(16.0, y + 12.0)
        legend_svg += more_svg
        y += 12.0 + more_h
    new_height = max(height, y + 12.0)
    svg = svg.replace(
        f'viewBox="0 0 {m.group(1)} {m.group(2)}"', f'viewBox="0 0 {m.group(1)} {new_height:.2f}"'
    ).replace(f'height="{m.group(2)}"', f'height="{new_height:.2f}"', 1)
    # Grow the background rect too, or the new caption lines sit off the canvas.
    svg = re.sub(
        r'(<rect class="qbm-canvas" x="0" y="0" width="[\d.]+" height=")[\d.]+(")',
        rf"\g<1>{new_height:.2f}\g<2>",
        svg,
        count=1,
    )
    return svg.replace("</svg>", "".join(block) + legend_svg + "</svg>")


def render_series_projection(
    spec: MapSpec,
    onto: Ontology,
    projection,
    out_dir: pathlib.Path = MAP_OUT_DIR,
    vmax: float | None = None,
) -> dict:
    """Render a map carrying a whole time course: tint by extreme, draw the trajectory.

    This is the one thing a static pathway diagram cannot do. Each node gets the colour
    of its most extreme timepoint and a sparkline of the full series, so a reader can
    see not only how far a node moved but when, and whether it reversed.

    Raises if any sparkline overlaps a node box. That check exists because the
    compartment-band overlap shipped once: the renderer had no assertion about overlap,
    so nothing failed and the defect reached the page.
    """
    # Lay the map out with room for the traces. A multi-locus node needs more than a
    # sparkline's strip, because it gets a per-locus heatmap instead: the aggregate is
    # exactly what hides a gene family splitting. The reservation is sized to the widest
    # heatmap on this map, so no node has to be shrunk to fit.
    #
    # The base map and the single-contrast OSDR overlays are unaffected — they call
    # layout_map with no reservation and are byte-identical.
    reserve = render.heatmap_reserve(projection.values, min_reserve=render.SPARK_RESERVE)
    nodes, comps, canvas = layout_map(spec, onto, reserve_bottom=reserve)
    values = projection.values
    if not values:
        raise MapError(f"{spec.id}: series projection carries no values")

    limit = vmax if vmax is not None else projection.vmax()
    if limit <= 0:
        raise MapError(
            f"{spec.id}: every projected value is 0.0 across every timepoint, so the "
            f"colour scale would be degenerate. This is almost certainly a join failure."
        )

    svg, stats = render_svg(spec, nodes, comps, canvas)

    # Tint by the extreme timepoint, reusing the single-contrast overlay machinery so a
    # time-course map and an OSDR map are coloured by exactly the same code.
    peak_values = {nid: _peak_nodevalue(ns) for nid, ns in values.items()}
    boxes = {n.id: n.box for n in nodes}

    # A node with one locus gets a sparkline; a node with several gets a heatmap.
    with_box = {nid: boxes[nid] for nid in values if nid in boxes}
    single = {nid: ns for nid, ns in values.items()
              if nid in with_box and len(getattr(ns, "per_locus", {})) <= 1}
    multi = {nid: ns for nid, ns in values.items()
             if nid in with_box and len(getattr(ns, "per_locus", {})) > 1}

    spark_svg, collisions = render.sparkline_svg(
        {nid: with_box[nid] for nid in single}, single, limit
    )
    heat_svg, heat_collisions = render.locus_heatmap_svg(
        {nid: with_box[nid] for nid in multi}, multi, limit
    )
    collisions = list(collisions) + list(heat_collisions)
    if collisions:
        raise MapError(
            f"{spec.id}: {len(collisions)} overlay mark(s) do not sit inside their node "
            f"— the figure would be legible-looking and wrong.\n  "
            + "\n  ".join(collisions[:8])
        )
    spark_svg = spark_svg + heat_svg

    caption_add = (
        " " + projection.provenance()
        + " Each node is tinted by its most extreme timepoint. A node standing for ONE "
        "locus carries a sparkline of its trajectory — the colour says how far it moved, "
        "the line says when. A node standing for SEVERAL carries a per-locus heatmap "
        "instead, one row per locus and one column per timepoint, because an aggregate "
        "cannot show a gene family splitting and under a strong perturbation families "
        "do split. A node with no measurement is left unfilled, which is not the same "
        "as a measured zero."
    )
    tf = render.body_transform(svg)
    svg = svg.replace(
        "</svg>",
        render.overlay_svg(peak_values, limit)
        + f'<g transform="{tf}">{spark_svg}</g></svg>',
    )
    heat_legend = None
    if multi:
        tps = projection.timepoints

        page_w = float(re.search(r'viewBox="0 0 ([\d.]+)', svg).group(1))

        def heat_legend(x, y, _tps=tps, _w=page_w):
            return render.heatmap_legend_svg(x, y, _tps, page_width=_w)

    svg = _append_caption(svg, caption_add, vmax=limit, extra_legend=heat_legend)

    (out_dir / "svg").mkdir(parents=True, exist_ok=True)
    stem = f"{spec.id}__{_slug(projection.study)}__{_slug(projection.tissue)}"
    path = out_dir / "svg" / f"{stem}.svg"
    path.write_text(svg, encoding="utf-8")

    reversing = sorted(nid for nid, ns in values.items() if ns.crosses_zero())
    return {
        "id": spec.id,
        "study": projection.study,
        "tissue": projection.tissue,
        "organism": projection.organism,
        "svg": str(path.relative_to(ROOT)),
        "timepoints": list(projection.timepoints),
        "nodes_with_data": projection.nodes_with_data,
        "fraction_covered": round(projection.fraction_covered, 4),
        "vmax": round(limit, 4),
        "nodes_reversing_direction": reversing,
        "nodes_with_heatmap": sorted(multi),
        "nodes_with_diverging_loci": sorted(
            nid for nid, ns in values.items() if getattr(ns, "loci_diverge", False)
        ),
        "provenance": projection.provenance(),
        "dropped_edge_labels": stats["dropped_edge_labels"],
    }


def _peak_nodevalue(ns):
    """A `NodeValue` standing for the series' most extreme timepoint, for the tint."""
    from .project import NodeValue

    return NodeValue(
        node_id=ns.node_id,
        qbo_id=ns.qbo_id,
        value=ns.extreme(),
        n_loci=ns.n_loci,
        loci_used=ns.loci_used,
        loci_missing=ns.loci_missing,
        aggregator=ns.aggregator,
        evidence_tier=ns.evidence_tier,
        significant=None,
    )
