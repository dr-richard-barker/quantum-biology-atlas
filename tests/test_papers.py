"""Published-results ingestion and the time-course projection.

Two of these tests guard bugs that had already shipped, and both were invisible to
every other check in the suite:

  * overlay marks were appended in document coordinates while node boxes are in layout
    coordinates, so every measured value in the published OSD-38 figure sat next to the
    wrong node. The numbers were right. Nothing failed.
  * a fold-change table fed to a log2 renderer colours every unchanged gene as strongly
    upregulated, and the figure looks entirely normal.

Both are the same class of defect the atlas exists to prevent: a figure that is wrong
and looks fine. So they are asserted directly rather than left to visual review.
"""
from __future__ import annotations

import math
import pathlib
import re

import pytest

from qbio import layout, maps, ontology, papers, project, render

ROOT = pathlib.Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# identifiers
# ---------------------------------------------------------------------------


def test_source_identifiers_defeat_a_naive_agi_pattern():
    """The reason `normalise_agi` exists, stated as a test.

    Parmagnani's table writes `At1g01980.1`. A plain AGI regex matches none of them, so
    a caller that skipped normalisation would join zero rows and render a blank map.
    """
    raw = "At1g01980.1"
    assert re.match(r"^AT[1-5CM]G\d{5}$", raw) is None
    assert papers.normalise_agi(raw) == "AT1G01980"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("At1g01980.1", "AT1G01980"),
        ("AT1G01980", "AT1G01980"),
        ("at5g64210.2", "AT5G64210"),
        ("ATMG00580", "ATMG00580"),
        ("  At3g09640.1  ", "AT3G09640"),
        ("not a locus", None),
        ("", None),
        (None, None),
    ],
)
def test_normalise_agi(raw, expected):
    assert papers.normalise_agi(raw) == expected


def test_parse_mean_sd():
    assert papers.parse_mean_sd("2.34 ± 0.31") == (2.34, 0.31)
    assert papers.parse_mean_sd("1 ± 0.09") == (1.0, 0.09)
    assert papers.parse_mean_sd("0.4") == (0.4, 0.0)
    assert papers.parse_mean_sd(1.5) == (1.5, 0.0)
    assert papers.parse_mean_sd("") is None
    assert papers.parse_mean_sd("n.d.") is None


# ---------------------------------------------------------------------------
# scale
# ---------------------------------------------------------------------------


def test_ratio_to_log2_moves_no_change_to_zero():
    """A ratio of 1.0 means no change and must become log2 0.0, not stay at 1.0."""
    m = papers.Measurement(1.0, 0.09, papers.RATIO).to_log2()
    assert m.value == pytest.approx(0.0)
    assert m.scale == papers.LOG2
    assert papers.Measurement(2.0, 0.0, papers.RATIO).to_log2().value == pytest.approx(1.0)
    assert papers.Measurement(0.5, 0.0, papers.RATIO).to_log2().value == pytest.approx(-1.0)


def test_sd_is_transformed_not_carried_across_unchanged():
    """Carrying the SD through a log transform unchanged states it in the wrong units."""
    m = papers.Measurement(2.34, 0.31, papers.RATIO).to_log2()
    assert m.sd == pytest.approx(0.31 / (2.34 * math.log(2)))
    assert m.sd != pytest.approx(0.31)


def test_log2_of_a_non_positive_ratio_raises():
    with pytest.raises(papers.PaperError):
        papers.Measurement(0.0, 0.0, papers.RATIO).to_log2()


def test_series_extreme_uses_the_right_centre_for_its_scale():
    tp = ("a", "b", "c")
    ratio = papers.Series("AT1G01010", "ROOTS", tp, tuple(
        papers.Measurement(v, 0.0, papers.RATIO) for v in (1.1, 0.4, 1.2)))
    # On a ratio scale no-change is 1.0, so 0.4 is further from it than 1.2.
    assert ratio.extreme() == pytest.approx(0.4)
    log2 = ratio.to_log2()
    assert log2.extreme() == pytest.approx(math.log2(0.4))


# ---------------------------------------------------------------------------
# the real table
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def parmagnani():
    import zipfile

    src = ROOT / "data" / "external" / "papers" / "PMC9775259_suppl.zip"
    if not src.exists():
        pytest.skip("Parmagnani 2022 supplementary archive not cached")
    zf = papers.open_nested_zip(zipfile.ZipFile(src), "biomolecules-12-01824-s001.zip")
    data = zf.read(papers.find_member(zf, "Table S2.xlsx"))
    return papers.read_banded_timecourse(
        data, locus_column="Gene", band_row=2, header_row=3,
        tissues=("ROOTS", "SHOOTS"), scale=papers.RATIO,
        extra_columns={"gene_code": "Gene code"},
    )


def test_the_published_table_parses_completely(parmagnani):
    """Every number in the source is accounted for — none skipped, none invented."""
    series, report = parmagnani
    assert len(report["loci"]) == 194
    assert report["rows_no_locus"] == 0
    assert report["cells_blank"] == 0
    # 194 loci x 7 timepoints x 2 tissues
    assert report["cells_parsed"] == 194 * 7 * 2
    assert report["tissues"] == {"ROOTS": 194, "SHOOTS": 194}
    assert len(series) == 388


def test_tissue_bands_come_from_the_merged_ranges(parmagnani):
    series, _ = parmagnani
    roots = [s for s in series if s.tissue == "ROOTS"]
    assert {s.timepoints for s in roots} == {
        ("10 min", "1 h", "2 h", "4 h", "24 h", "48 h", "96 h")
    }


def test_a_missing_tissue_band_raises_rather_than_guessing(parmagnani):
    """Splitting the columns in half would silently assign shoot values to root nodes."""
    import zipfile

    src = ROOT / "data" / "external" / "papers" / "PMC9775259_suppl.zip"
    zf = papers.open_nested_zip(zipfile.ZipFile(src), "biomolecules-12-01824-s001.zip")
    data = zf.read(papers.find_member(zf, "Table S2.xlsx"))
    with pytest.raises(papers.PaperError, match="no merged band"):
        papers.read_banded_timecourse(
            data, locus_column="Gene", band_row=2, header_row=3,
            tissues=("ROOTS", "LEAVES"), scale=papers.RATIO,
        )


# ---------------------------------------------------------------------------
# projection
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def qbm07(onto):
    spec = maps.load_spec(ROOT / "maps" / "src" / "QBM-07_ros_redox.yaml")
    nodes = [(n, onto.get(spec.nodes.get(n, {}).get("qbo", ""))) for n in spec.node_ids]
    return spec, nodes


def _log2_by_locus(series, tissue):
    return {
        s.locus: s.to_log2() for s in series if s.tissue == tissue
    }


def test_project_series_refuses_a_ratio_scale_series(parmagnani, qbm07):
    """The guard that stops the worst available failure on this data path.

    A ratio series rendered as log2 paints every unchanged gene as strongly
    upregulated. Nothing about the resulting figure looks wrong.
    """
    series, _ = parmagnani
    spec, nodes = qbm07
    ratios = {s.locus: s for s in series if s.tissue == "ROOTS"}
    with pytest.raises(project.ProjectionError, match="ratio scale"):
        project.project_series(
            map_id=spec.id, nodes=nodes, series_by_locus=ratios,
            study="test", tissue="ROOTS",
        )


def test_project_series_refuses_a_mixed_timebase(parmagnani, qbm07):
    series, _ = parmagnani
    spec, nodes = qbm07
    by_locus = _log2_by_locus(series, "ROOTS")
    victim = next(iter(by_locus))
    import dataclasses

    by_locus[victim] = dataclasses.replace(
        by_locus[victim],
        timepoints=("t0", "t1", "t2", "t3", "t4", "t5", "t6"),
    )
    with pytest.raises(project.ProjectionError, match="timebase"):
        project.project_series(
            map_id=spec.id, nodes=nodes, series_by_locus=by_locus,
            study="test", tissue="ROOTS",
        )


def test_project_series_covers_the_redox_map(parmagnani, qbm07):
    series, _ = parmagnani
    spec, nodes = qbm07
    proj = project.project_series(
        map_id=spec.id, nodes=nodes, series_by_locus=_log2_by_locus(series, "ROOTS"),
        study="Parmagnani", tissue="ROOTS",
    )
    # Above the 25% refusal threshold without needing allow_low_coverage: the source
    # table is filtered to oxidative-reaction enzymes, which is what this map is.
    assert proj.fraction_covered >= 0.25
    assert proj.nodes_with_data == 4
    assert {"ASCORBATE_PEROXIDASE", "CATALASE", "SUPEROXIDE_DISMUTASES"} <= set(proj.values)


def test_direction_matches_the_papers_own_conclusion(parmagnani, qbm07):
    """The paper reports lower H2O2 under NNMF, "in agreement with the expression of
    ROS-related genes". The scavenging enzymes should therefore come out DOWN."""
    series, _ = parmagnani
    spec, nodes = qbm07
    proj = project.project_series(
        map_id=spec.id, nodes=nodes, series_by_locus=_log2_by_locus(series, "ROOTS"),
        study="Parmagnani", tissue="ROOTS",
    )
    assert proj.values["ASCORBATE_PEROXIDASE"].extreme() < 0
    assert proj.values["CATALASE"].extreme() < 0


def test_a_series_that_reverses_is_reported(parmagnani, qbm07):
    """The behaviour a single-contrast overlay cannot represent, surfaced explicitly."""
    series, _ = parmagnani
    spec, nodes = qbm07
    proj = project.project_series(
        map_id=spec.id, nodes=nodes, series_by_locus=_log2_by_locus(series, "ROOTS"),
        study="Parmagnani", tissue="ROOTS",
    )
    assert any(ns.crosses_zero() for ns in proj.values.values())
    assert "reverse direction" in proj.provenance()


def test_at_returns_a_single_timepoint_projection(parmagnani, qbm07):
    series, _ = parmagnani
    spec, nodes = qbm07
    proj = project.project_series(
        map_id=spec.id, nodes=nodes, series_by_locus=_log2_by_locus(series, "ROOTS"),
        study="Parmagnani", tissue="ROOTS",
    )
    snap = proj.at(0)
    assert snap.values["CATALASE"].value == pytest.approx(proj.values["CATALASE"].points[0])
    assert "10 min" in snap.contrast


# ---------------------------------------------------------------------------
# rendering — the coordinate-space regression
# ---------------------------------------------------------------------------


def test_overlay_marks_are_placed_in_map_coordinates(parmagnani, qbm07, onto, tmp_path):
    """Regression: appended marks must carry the body group's transform.

    Without it every sparkline and value chip is offset by the header height and lands
    beside the wrong node — which is exactly what the first published OSD-38 overlay
    did. Asserting the transform is present is not enough on its own, so this also
    checks that a sparkline's own coordinates fall inside its node's box.
    """
    series, _ = parmagnani
    spec, nodes = qbm07
    proj = project.project_series(
        map_id=spec.id, nodes=nodes, series_by_locus=_log2_by_locus(series, "ROOTS"),
        study="coordtest", tissue="ROOTS",
    )
    maps.render_series_projection(spec, onto, proj, out_dir=ROOT / "results" / "_scratch")
    svg = (ROOT / "results" / "_scratch" / "svg" /
           "QBM-07__coordtest__ROOTS.svg").read_text()

    body_tf = render.body_transform(svg)
    # Every appended sparkline group sits in a sibling group with the SAME transform.
    spark_group = re.search(
        rf'<g transform="{re.escape(body_tf)}">(<g class="qbm-spark".*?)</g></svg>',
        svg, re.S,
    )
    assert spark_group, "sparklines are not wrapped in the body transform"

    # And the geometry actually lands on the nodes.
    # Same reservation the renderer used: it sizes the strip for the widest per-locus
    # heatmap on the map, which can exceed a sparkline's. Re-laying out with the
    # sparkline constant would compare the drawn marks against different boxes.
    reserve = render.heatmap_reserve(proj.values, min_reserve=render.SPARK_RESERVE)
    laid, _, _ = maps.layout_map(spec, onto, reserve_bottom=reserve)
    boxes = {n.id: n.box for n in laid}
    for m in re.finditer(
        r'<g class="qbm-spark" data-spark-for="([^"]+)"><rect class="qbm-unit" '
        r'x="([\d.-]+)" y="([\d.-]+)" width="([\d.-]+)" height="([\d.-]+)"',
        svg,
    ):
        nid, x, y, w, h = m.group(1), *map(float, m.groups()[1:])
        box = boxes[nid]
        assert box.x <= x and x + w <= box.x2 + 0.5, f"{nid} sparkline is outside its node"
        assert box.y <= y and y + h <= box.y2 + 0.5, f"{nid} sparkline is outside its node"


def test_sparkline_collision_check_is_not_vacuous():
    """Prove the overlap assertion can fail, by handing it overlapping boxes.

    A check that cannot fail is worse than no check: the compartment-band overlap
    shipped because nothing asserted on it.
    """
    class FakeSeries:
        points = (0.5, -0.5)
        timepoints = ("a", "b")
        def extreme(self):
            return 0.5

    a = layout.Box(0, 0, 200, 60)
    b = layout.Box(10, 10, 200, 60)          # deliberately on top of a
    _, collisions = render.sparkline_svg({"A": a, "B": b},
                                         {"A": FakeSeries(), "B": FakeSeries()}, 1.0)
    assert collisions, "overlapping node boxes produced no collision report"

    far = layout.Box(0, 0, 200, 60)
    away = layout.Box(600, 600, 200, 60)
    _, none = render.sparkline_svg({"A": far, "B": away},
                                   {"A": FakeSeries(), "B": FakeSeries()}, 1.0)
    assert not none, "well-separated boxes should not collide"


def test_reserving_space_moves_the_label_up_rather_than_only_growing_the_box(onto):
    """Otherwise the trace lands on the node's own identifiers."""
    spec = maps.load_spec(ROOT / "maps" / "src" / "QBM-07_ros_redox.yaml")
    plain, _, _ = maps.layout_map(spec, onto)
    reserved, _, _ = maps.layout_map(spec, onto, reserve_bottom=render.SPARK_RESERVE)
    p, r = plain[0], reserved[0]
    assert r.box.h == pytest.approx(p.box.h + render.SPARK_RESERVE)
    assert r.reserve_bottom == pytest.approx(render.SPARK_RESERVE)
    # The text centre must NOT be the box centre once space is reserved.
    text_cy = r.box.y + (r.box.h - r.reserve_bottom) / 2.0
    assert text_cy < r.box.cy


def test_base_maps_are_unaffected_by_the_series_capability(onto):
    """Adding a reservation parameter must not change any existing figure."""
    spec = maps.load_spec(ROOT / "maps" / "src" / "QBM-07_ros_redox.yaml")
    a, _, _ = maps.layout_map(spec, onto)
    b, _, _ = maps.layout_map(spec, onto)
    assert [n.box.h for n in a] == [n.box.h for n in b]
    assert all(n.reserve_bottom == 0.0 for n in a)
