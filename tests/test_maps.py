"""Map compilation, SBGN validity and the no-synthetic-data guard.

Figure legibility is NOT tested here. It is asserted against what a browser actually
painted, by `tests/legibility_probe.js`, because a Python-side check would only
re-run the compiler's own arithmetic. See that file's header.
"""
from __future__ import annotations

import pathlib
import re
import xml.etree.ElementTree as ET

import pytest

SBGN_NS = "http://sbgn.org/libsbgn/0.3"
QBO_NS = "https://dr-richard-barker.github.io/quantum-biology-atlas/qbo/1.0"

#: SBGN PD's fixed glyph vocabulary. Anything outside it would not open in Newt,
#: VANTED or the SBGN Pathway Visualizer.
VALID_PD_GLYPHS = {
    "unspecified entity", "simple chemical", "macromolecule",
    "nucleic acid feature", "perturbing agent", "source and sink", "complex",
    "process", "omitted process", "uncertain process", "association",
    "dissociation", "phenotype", "compartment", "submap", "tag",
    "unit of information", "state variable", "annotation", "variable value",
    "entity", "outcome", "interaction", "and", "or", "not",
}
VALID_PD_ARCS = {
    "production", "consumption", "catalysis", "modulation", "stimulation",
    "inhibition", "necessary stimulation", "logic arc", "equivalence arc",
}


def test_all_maps_compile(map_records):
    assert len(map_records) == 10, f"expected 10 maps, compiled {len(map_records)}"


def test_no_map_drops_an_edge_label(map_records):
    """A label that cannot be placed without covering a node is dropped and reported.
    Zero is the standing expectation; a non-zero count means a map needs re-laning."""
    offenders = {r["id"]: r["dropped_edge_labels"] for r in map_records if r["dropped_edge_labels"]}
    assert offenders == {}, f"maps dropping edge labels: {offenders}"


def test_every_map_node_is_ontology_annotated(map_records):
    for r in map_records:
        assert r["annotated_nodes"] == r["nodes"], (
            f"{r['id']}: {r['nodes'] - r['annotated_nodes']} node(s) carry no QBO entity"
        )


def test_every_map_states_its_provenance(map_records):
    for r in map_records:
        assert r["derived_from"], f"{r['id']} does not say what it was derived from"
        assert len(r["caption"]) > 200, f"{r['id']} caption is too short to be useful"


def test_maps_carry_identifiers_to_join_on(map_records):
    """A map with no loci can never receive data, which would make it decorative."""
    for r in map_records:
        assert r["agi_loci"], f"{r['id']} binds no AGI locus"


# ---------------------------------------------------------------------------
# SBGN
# ---------------------------------------------------------------------------
def _parse(path: pathlib.Path):
    root = ET.fromstring(path.read_text(encoding="utf-8"))
    pmap = root.find(f"{{{SBGN_NS}}}map")
    assert pmap is not None, f"{path.name}: no <map> in the SBGN namespace"
    return pmap


def test_sbgn_is_well_formed_process_description(root, map_records):
    for r in map_records:
        pmap = _parse(root / r["sbgn"])
        assert pmap.get("language") == "process description", (
            f"{r['id']}: language is {pmap.get('language')!r}"
        )


def test_sbgn_glyph_and_arc_classes_are_in_the_pd_vocabulary(root, map_records):
    for r in map_records:
        pmap = _parse(root / r["sbgn"])
        glyphs = pmap.iter(f"{{{SBGN_NS}}}glyph")
        bad_g = sorted({g.get("class") for g in glyphs} - VALID_PD_GLYPHS)
        arcs = pmap.iter(f"{{{SBGN_NS}}}arc")
        bad_a = sorted({a.get("class") for a in arcs} - VALID_PD_ARCS)
        assert bad_g == [], f"{r['id']}: glyph classes outside SBGN PD: {bad_g}"
        assert bad_a == [], f"{r['id']}: arc classes outside SBGN PD: {bad_a}"


def test_sbgn_every_glyph_has_a_bounding_box(root, map_records):
    """Geometry is the whole reason for emitting SBGN rather than a node list — a
    renderer lays the map out from these coordinates."""
    for r in map_records:
        pmap = _parse(root / r["sbgn"])
        for g in pmap.findall(f"{{{SBGN_NS}}}glyph"):
            bbox = g.find(f"{{{SBGN_NS}}}bbox")
            assert bbox is not None, f"{r['id']}: glyph {g.get('id')} has no bbox"
            w, h = float(bbox.get("w")), float(bbox.get("h"))
            assert w > 0 and h > 0, f"{r['id']}: glyph {g.get('id')} has zero-area bbox"


def test_sbgn_arcs_reference_declared_glyphs(root, map_records):
    for r in map_records:
        pmap = _parse(root / r["sbgn"])
        ids = {g.get("id") for g in pmap.iter(f"{{{SBGN_NS}}}glyph")}
        for a in pmap.findall(f"{{{SBGN_NS}}}arc"):
            for end in ("source", "target"):
                ref = a.get(end)
                assert ref in ids, f"{r['id']}: arc {a.get('id')} {end}={ref!r} is not a glyph"


def test_sbgn_carries_the_qbo_annotation(root, map_records):
    """The annotation layer is the point. A map that lost it would render as an
    ordinary pathway diagram with no evidence channel."""
    for r in map_records:
        text = (root / r["sbgn"]).read_text(encoding="utf-8")
        assert QBO_NS in text, f"{r['id']}: no QBO namespace in the SBGN"
        assert "evidenceTier" in text, f"{r['id']}: no evidence tier in the SBGN annotation"


def test_sbgn_round_trips(root, map_records, onto):
    """Recompiling must reproduce the same structure, or the build is not deterministic."""
    from qbio import maps, sbgn

    for r in map_records:
        before = sbgn.parse_check((root / r["sbgn"]).read_text(encoding="utf-8"))
        rebuilt = maps.compile_map(
            next(p for p in (root / "maps" / "src").glob("*.yaml")
                 if maps.load_spec(p).id == r["id"]),
            onto,
        )
        after = sbgn.parse_check((root / rebuilt["sbgn"]).read_text(encoding="utf-8"))
        assert before == after, f"{r['id']}: SBGN changed on recompilation"


# ---------------------------------------------------------------------------
# the no-synthetic-data guard
# ---------------------------------------------------------------------------
#: Long literal numeric arrays in a figure or table script are how the review's
#: Figure 4 came to show six identical 40% effects that were never measured.
_NUMERIC_ARRAY = re.compile(r"\[\s*-?\d+(?:\.\d+)?\s*(?:,\s*-?\d+(?:\.\d+)?\s*){3,}\]")


def test_no_figure_script_hard_codes_a_numeric_array(root):
    """Every rendered number must trace to a file in results/, not to a literal.

    The exemptions below are geometry and statistics constants, not data: layout
    offsets, a power curve's x-axis, and colour stops. They are listed explicitly so
    that adding a new one is a visible decision.
    """
    exempt = {
        "layout.py",        # geometry: gutters, padding, offsets
        "render.py",        # geometry: label search offsets, legend stops
        "preregistered_test.py",  # statistics: the odds-ratio grid for the power curve
    }
    offenders = []
    for path in sorted((root / "src" / "qbio").glob("*.py")) + sorted((root / "scripts").glob("*.py")):
        if path.name in exempt:
            continue
        for i, line in enumerate(path.read_text().splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            if _NUMERIC_ARRAY.search(line):
                offenders.append(f"{path.name}:{i}: {line.strip()[:80]}")
    assert offenders == [], (
        "hard-coded numeric arrays outside the geometry/statistics exemptions:\n  "
        + "\n  ".join(offenders)
    )


def _caption_text(svg: str) -> str:
    """Join the caption's wrapped lines back into one string.

    The caption is emitted as one <text> per wrapped line, so a phrase can be split
    across two elements — a naive substring search on the raw SVG misses it depending
    on where the wrap happens to fall, which is a property of the page width rather
    than of the content.
    """
    lines = re.findall(r'<text class="qbm-caption"[^>]*>(.*?)</text>', svg, re.S)
    return re.sub(r"\s+", " ", " ".join(lines))


def test_base_maps_encode_no_quantitative_value(root, map_records):
    """A base map is schematic topology. Numbers arrive only via qbio.project."""
    for r in map_records:
        svg = (root / r["svg"]).read_text(encoding="utf-8")
        assert "data-value-for" not in svg, f"{r['id']}: base map carries data value chips"
        caption = _caption_text(svg)
        assert "no quantitative value is encoded" in caption, (
            f"{r['id']}: base map does not state that it carries no data"
        )


def test_every_map_caption_names_its_source(root, map_records):
    """Checked on the joined caption text for the same wrapping reason."""
    for r in map_records:
        caption = _caption_text((root / r["svg"]).read_text(encoding="utf-8"))
        assert re.search(r"derived from", caption, re.I), (
            f"{r['id']}: caption does not state its provenance"
        )
