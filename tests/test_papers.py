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


# ---------------------------------------------------------------------------
# signed fold change — the third scale
# ---------------------------------------------------------------------------


def test_signed_fold_converts_reciprocally():
    """-3.09 means 3.09-fold DOWN, not a log and not a ratio."""
    up = papers.Measurement(3.09, 0.1, papers.SIGNED_FOLD).to_log2()
    down = papers.Measurement(-3.09, 0.1, papers.SIGNED_FOLD).to_log2()
    assert up.value == pytest.approx(math.log2(3.09))
    assert down.value == pytest.approx(-math.log2(3.09))
    assert up.value == pytest.approx(-down.value)


def test_signed_fold_of_one_is_no_change_either_way():
    for v in (1.0, -1.0):
        assert papers.Measurement(v, 0, papers.SIGNED_FOLD).to_log2().value == pytest.approx(0.0)


def test_a_value_inside_minus_one_to_one_is_refused_on_the_signed_scale():
    """The tell that the scale was mislabelled. Guessing between 'wrong scale' and
    'misparsed cell' would silently change a direction."""
    with pytest.raises(papers.PaperError, match="strictly between"):
        papers.Measurement(0.5, 0, papers.SIGNED_FOLD).to_log2()


def test_reading_signed_fold_as_a_ratio_would_invert_the_papers_claim():
    """Why the scale is checked rather than assumed: Agliassa's central finding is that
    near-null fields DOWN-regulate flowering genes."""
    signed = papers.Measurement(-3.09, 0, papers.SIGNED_FOLD).to_log2().value
    assert signed < 0
    # The same number read as a ratio is not even convertible, which is the safe failure.
    with pytest.raises(papers.PaperError):
        papers.Measurement(-3.09, 0, papers.RATIO).to_log2()


def test_parse_signed_fold_handles_the_unicode_minus():
    """The XML uses U+2212, which a plain '-' match misses entirely."""
    assert papers.parse_signed_fold("−3.09 (±0.10)") == (-3.09, 0.10)
    assert papers.parse_signed_fold("1.14 (±0.02)") == (1.14, 0.02)
    assert papers.parse_signed_fold("not a value") is None


# ---------------------------------------------------------------------------
# main-text tables
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def agliassa():
    import zipfile

    src = ROOT / "data" / "external" / "papers" / "PMC6032911_suppl.zip"
    if not src.exists():
        pytest.skip("Agliassa 2018a supplementary not cached")
    xml_cache = ROOT / "data" / "external" / "papers" / "PMC6032911_fulltext.xml"
    if not xml_cache.exists():
        pytest.skip("Agliassa 2018a full text not cached")
    zf = zipfile.ZipFile(src)
    primer = papers.read_primer_map(
        zf.read(papers.find_member(zf, "SuppTable-S1"))
    )
    series, report = papers.read_maintext_timecourse(
        xml_cache.read_text(encoding="utf-8", errors="replace"),
        table_captions=("Time-Course Expression of Leaf Genes",
                        "Time-Course Expression of Floral Meristem Genes"),
        symbol_to_locus=primer, scale=papers.SIGNED_FOLD,
    )
    return series, report, primer


def test_every_gene_symbol_resolves_from_the_papers_own_primer_table(agliassa):
    """Resolving a symbol from memory is how the wrong gene reaches a map."""
    _, report, primer = agliassa
    assert not report["symbols_unresolved"], report["symbols_unresolved"]
    assert len(primer) >= 25


def test_a_symbol_with_a_stray_space_still_resolves(agliassa):
    """The XML renders SOC1 as 'SOC 1'; an exact lookup loses a central flowering gene."""
    series, _, _ = agliassa
    assert any(s.gene_code.replace(" ", "") == "SOC1" for s in series)


def test_tables_are_selected_by_caption_not_position(agliassa):
    with pytest.raises(papers.PaperError, match="no main-text table matched"):
        papers.read_maintext_timecourse(
            "<table-wrap><caption>Something else</caption></table-wrap>",
            table_captions=("Time-Course Expression of Leaf Genes",),
            symbol_to_locus={}, scale=papers.SIGNED_FOLD,
        )


def test_the_two_tissues_have_their_own_timebases(agliassa):
    """Leaves were sampled days 17-28, meristem days 21-30. Sharing a timebase would
    misdate every meristem value."""
    series, _, _ = agliassa
    bases = {s.tissue: s.timepoints for s in series}
    assert len(set(bases.values())) == 2


def test_the_direction_matches_the_papers_own_abstract(agliassa):
    """The abstract says NNMF causes 'an early downregulation of clock, photoperiod,
    gibberellin, and vernalization pathways'. The clock genes must come out negative."""
    series, _, _ = agliassa
    clock = [s for s in series if s.locus in
             {"AT2G46830", "AT1G01060", "AT5G61380", "AT1G22770"}]
    assert clock, "no circadian clock loci parsed"
    early = [s.to_log2().points[0].value for s in clock if s.points[0] is not None]
    assert sum(early) / len(early) < 0, (
        "the clock genes come out UP at the first timepoint, which contradicts the "
        "paper's abstract — the scale conversion is probably inverted"
    )


def test_a_pdf_with_no_symbol_pairs_raises():
    """A VALID pdf carrying no primer table, not a corrupt one — a corrupt file already
    fails loudly inside pdfplumber, and returning an empty key silently would make every
    downstream symbol fail to resolve."""
    import io
    import zipfile

    src = ROOT / "data" / "external" / "papers" / "PMC9917513_suppl.zip"
    if not src.exists():
        pytest.skip("Parmagnani 2023 supplementary not cached")
    outer = zipfile.ZipFile(src)
    inner = papers.open_nested_zip(
        outer, next(n for n in outer.namelist() if n.lower().endswith(".zip"))
    )
    # Its Table S2 is an HPLC gradient: a real table, with no gene symbols in it.
    data = inner.read(papers.find_member(inner, "Table S2"))
    with pytest.raises(papers.PaperError, match="no gene-symbol"):
        papers.read_primer_map(data)


# ---------------------------------------------------------------------------
# Mannino 2026: sweet basil under near-null magnetic field
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def mannino():
    tsv = ROOT / "data" / "external" / "papers" / "Mannino2026" / "gene_expression.tsv"
    if not tsv.exists():
        pytest.skip("Mannino 2026 curated TSV not found")
    series, report = papers.read_curated_table(tsv, tissue="leaves", timepoint="4w", scale=papers.LOG2)
    return series, report


def test_mannino2026_curated_table_parses_cleanly(mannino):
    series, report = mannino
    assert len(series) >= 20
    assert report["rows_no_locus"] == 0
    assert report["cells_blank"] == 0
    assert "AT1G08830" in report["loci"]  # CSD1 (ObCSD)
    assert "AT4G25100" in report["loci"]  # FSD1 (ObFSD1)


def test_mannino2026_scale_preserves_log2_directly(mannino):
    """Values are published as log2 fold change and must NOT undergo a second log2."""
    series, _ = mannino
    csd = next(s for s in series if s.locus == "AT1G08830")
    assert csd.scale == papers.LOG2
    assert csd.points[0].value == pytest.approx(-1.45)
    # to_log2 is an idempotent no-op for LOG2 scale
    assert csd.to_log2().points[0].value == pytest.approx(-1.45)


def test_mannino2026_sod_isoforms_diverge_into_2row_heatmap(mannino, onto):
    """Cu/Zn-SOD (ObCSD) falls while Fe-SOD (ObFSD1) rises: averaging would hide both."""
    series, _ = mannino
    spec = maps.load_spec(ROOT / "maps" / "src" / "QBM-07_ros_redox.yaml")
    nodes = [(n, onto.get(spec.nodes.get(n, {}).get("qbo", ""))) for n in spec.node_ids]
    by_locus = {s.locus: s.to_log2() for s in series}

    proj = project.project_series(
        map_id="QBM-07",
        nodes=nodes,
        series_by_locus=by_locus,
        study="Mannino, Caldo & Maffei",
        tissue="leaves",
        organism="Ocimum basilicum",
    )
    assert "SUPEROXIDE_DISMUTASES" in proj.values
    sod_ns = proj.values["SUPEROXIDE_DISMUTASES"]
    assert sod_ns.n_loci == 2
    assert sod_ns.loci_diverge is True
    # The two rows must have opposing signs
    per_loc = sod_ns.per_locus
    assert "AT1G08830" in per_loc and "AT4G25100" in per_loc
    assert per_loc["AT1G08830"][0] < 0
    assert per_loc["AT4G25100"][0] > 0


def test_mannino2026_all_phenylpropanoid_transcripts_are_downregulated(mannino):
    """The decoupling finding: every phenylpropanoid biosynthetic transcript is down."""
    series, _ = mannino
    phenyl_genes = {"ObPAL", "ObCOMT", "ObEGS", "ObEOMT", "Ob4CL", "ObCHS", "ObCHI", "ObCHIL"}
    found_genes = [s for s in series if s.gene_code in phenyl_genes]
    assert len(found_genes) == 8
    for s in found_genes:
        assert s.points[0].value < 0, f"{s.gene_code} expected downregulated, got {s.points[0].value}"


def test_mannino2026_decoupling_submap_renders(root):
    from qbio.decoupling import render_decoupling_svg
    svg = render_decoupling_svg()
    assert "THE GENE-METABOLITE DECOUPLING PARADOX" in svg
    assert "EUGENOL" in svg
    assert "METHYL EUGENOL" in svg
    assert "ObPAL" in svg
    assert "ObEOMT" in svg

