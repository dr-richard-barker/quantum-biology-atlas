"""OSD-782: dose-contrast selection, orientation, and the divergence check it forced.

The contrast filter is this page's scientific claim, and it needed a *different* rule
from the OSD-27 one: radiation source and dose are coupled by construction, so the
single-factor test that isolates a magnetic field rejects every dose comparison here.
That reasoning is asserted rather than left in a docstring.

The divergence test guards a finding this dataset produced: under radiation almost every
multi-locus node has loci that disagree in sign, so `extreme` picks a different gene at
each timepoint and the node's trace swings for reasons that are not biological.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from qbio import compare, osd782, project

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONTRASTS = ROOT / "data" / "external" / "osd782_contrasts.csv"
RECORD = ROOT / "results" / "osd782" / "record.json"
OVERLAP = ROOT / "results" / "overlap" / "record.json"


@pytest.fixture(scope="module")
def contrasts():
    if not CONTRASTS.exists():
        pytest.skip("OSD-782 contrasts not cached")
    return osd782.parse_contrasts(CONTRASTS.read_text())


# ---------------------------------------------------------------------------
# the predicate that had to be different
# ---------------------------------------------------------------------------


def test_dose_contrasts_are_not_single_factor(contrasts):
    """The reason `isolates_dose` exists, encoded.

    Dose and radiation source move together — there is no cesium-137 at 0 cGy — so the
    OSD-27 rule would reject the entire set.
    """
    iso = [c for c in contrasts if osd782.isolates_dose(c)]
    assert iso, "no dose-isolating contrast found"
    assert not any(c.is_single_factor for c in iso), (
        "a dose contrast now differs in one factor only, which contradicts the study "
        "design; if that is real, isolates_dose needs revisiting"
    )


def test_exactly_two_doses_by_four_timepoints(contrasts):
    points = osd782.dose_points(contrasts)
    assert len(points) == 8
    series = osd782.dose_series(contrasts)
    assert sorted(series) == [0.1, 1.0]
    for dose, pts in series.items():
        assert [p.time_label for p in pts] == list(osd782.TIME_ORDER)


def test_both_orientations_deduplicate_to_irradiated_first(contrasts):
    """Keeping the control-first orientation would invert every fold change, so a
    positive value would mean 'higher WITHOUT irradiation'."""
    raw = [c for c in contrasts if osd782.isolates_dose(c)]
    assert len(raw) == 16, "expected both orientations in the source file"
    for p in osd782.dose_points(contrasts):
        assert p.contrast.left[0] == osd782.IRRADIATED


def test_a_time_mismatched_contrast_does_not_isolate_dose(contrasts):
    """Dose and time changing together would confound the two."""
    mismatched = [
        c for c in contrasts
        if {osd782.IRRADIATED, osd782.CONTROL} == set(
            next((p for p in c.differing if set(p) == {osd782.IRRADIATED, osd782.CONTROL}),
                 ("", ""))
        )
        and len(c.differing) > 2
    ]
    assert not any(osd782.isolates_dose(c) for c in mismatched)


def test_dose_vocabulary_converts_centigray_to_gray():
    assert osd782.DOSE_GY["10 centigray"] == 0.1
    assert osd782.DOSE_GY["100 centigray"] == 1.0
    assert osd782.DOSE_GY["0 centigray"] == 0.0


def test_time_ordering_is_not_lexicographic():
    """'24 hour' sorts before '3 hour' as a string; a time course must not."""
    assert [osd782.hours(t) for t in osd782.TIME_ORDER] == [1.0, 3.0, 24.0, 72.0]
    assert sorted(osd782.TIME_ORDER) != list(osd782.TIME_ORDER)


def test_radiation_is_not_recorded_as_a_field_regime():
    """The one thing this module must never do."""
    assert osd782.PERTURBATION["kind"] == "ionising_radiation"
    assert "field_regime" not in osd782.PERTURBATION
    from qbio import ontology

    core = ontology.load().core
    regimes = {r["id"] for r in core.raw["field_regimes"]} if hasattr(core, "raw") else set()
    assert not any("radia" in r.lower() for r in regimes), (
        "a radiation term has appeared in QBO's field_regimes vocabulary; radiation is "
        "a different perturbation axis, not a point on the field-strength axis"
    )


# ---------------------------------------------------------------------------
# divergence
# ---------------------------------------------------------------------------


def test_node_series_records_sign_divergence_between_its_loci():
    from qbio.papers import LOG2, Measurement, Series

    # Two loci moving in opposite directions at the same timepoint.
    up = Series("AT1G00001", "x", ("t1", "t2"),
                (Measurement(1.0, 0, LOG2), Measurement(1.0, 0, LOG2)))
    down = Series("AT1G00002", "x", ("t1", "t2"),
                  (Measurement(-1.0, 0, LOG2), Measurement(1.0, 0, LOG2)))

    class Ent:
        id = "QBO:X"
        agi = ("AT1G00001", "AT1G00002")
        evidence_tier = "T3"

    proj = project.project_series(
        map_id="TEST", nodes=[("N", Ent())],
        series_by_locus={"AT1G00001": up, "AT1G00002": down},
        study="t", tissue="t",
    )
    ns = proj.values["N"]
    assert ns.diverged == (True, False)
    assert ns.loci_diverge is True
    assert ns.n_diverging_timepoints == 1
    assert "disagree in direction" in proj.provenance()


def test_agreeing_loci_are_not_flagged_as_divergent():
    """Non-vacuity: the flag must be able to stay off."""
    from qbio.papers import LOG2, Measurement, Series

    a = Series("AT1G00001", "x", ("t1",), (Measurement(1.0, 0, LOG2),))
    b = Series("AT1G00002", "x", ("t1",), (Measurement(0.5, 0, LOG2),))

    class Ent:
        id = "QBO:X"
        agi = ("AT1G00001", "AT1G00002")
        evidence_tier = "T3"

    proj = project.project_series(
        map_id="TEST", nodes=[("N", Ent())],
        series_by_locus={"AT1G00001": a, "AT1G00002": b}, study="t", tissue="t",
    )
    assert proj.values["N"].loci_diverge is False
    assert "disagree in direction" not in proj.provenance()


# ---------------------------------------------------------------------------
# the built record
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def record():
    if not RECORD.exists():
        pytest.skip("OSD-782 record not built")
    return json.loads(RECORD.read_text())


def test_the_record_declares_its_provenance_and_perturbation(record):
    assert record["provenance_class"] == "genelab_processed"
    assert record["perturbation"]["kind"] == "ionising_radiation"
    assert record["qbo_loci_measured"] >= 120


def test_every_recorded_contrast_is_multi_factor(record):
    assert all(not c["is_single_factor"] for c in record["contrasts"])
    assert len(record["contrasts"]) == 8


def test_divergence_is_recorded_on_the_figures(record):
    """This dataset's methodological finding, asserted so it cannot silently vanish."""
    flagged = [
        n for f in record["figures"] for n in f["per_node"] if n["loci_diverge"]
    ]
    assert flagged, (
        "no node reports diverging loci under radiation, which contradicts the page's "
        "central warning — either the data or the detector changed"
    )
    multi = [n for f in record["figures"] for n in f["per_node"] if len(n["loci"]) > 1]
    assert len(flagged) / len(multi) > 0.5, (
        "the page states that almost every multi-locus node diverges; it no longer does"
    )


# ---------------------------------------------------------------------------
# the overlap
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def overlap():
    if not OVERLAP.exists():
        pytest.skip("overlap record not built")
    return json.loads(OVERLAP.read_text())


def test_the_nnmf_arm_is_reported_but_not_tested(overlap):
    """Eleven loci must never receive a p-value."""
    arm = overlap["nnmf_locus_arm"]
    assert arm["chance"]["tested"] is False
    assert "p_value" not in arm["chance"]
    assert arm["summary"]["units_compared"] < compare.MIN_N_FOR_CHANCE_TEST


def test_the_strong_field_arm_is_large_enough_to_test(overlap):
    arm = overlap["locus_arm"]
    assert arm["chance"]["tested"] is True
    assert arm["summary"]["units_compared"] >= compare.MIN_N_FOR_CHANCE_TEST
    assert arm["chance"]["p_value"] > 0


def test_the_headline_overlap_holds(overlap):
    """If a rebuild changes which loci are shared, the page's headline must fail loudly
    rather than silently contradict itself."""
    s = overlap["nnmf_locus_arm"]["summary"]
    assert s["directions_agree"] == 2
    assert set(s["agreeing_keys"]) == {"AT1G20630", "AT1G32350"}


def test_the_aox_divergence_example_is_real(overlap):
    """The worked case: two family members moving opposite ways under radiation."""
    loci = {l["locus"]: l for l in overlap["divergence_example"]["loci"]}
    assert loci["AT1G32350"]["radiation"] > 0, "AOX1D should rise under radiation"
    assert loci["AT5G64210"]["radiation"] < 0, "AOX2 should fall under radiation"
    assert loci["AT5G64210"]["NNMF"] > 0, "AOX2 should rise under near-null field"


# ---------------------------------------------------------------------------
# per-locus heatmaps
# ---------------------------------------------------------------------------


def test_multi_locus_nodes_get_a_heatmap_and_single_locus_nodes_a_sparkline(record):
    """The visual answer to divergence: an aggregate cannot show a family splitting."""
    for fig in record["figures"]:
        heat = set(fig["nodes_with_heatmap"])
        multi = {n["node_id"] for n in fig["per_node"] if len(n["loci"]) > 1}
        single = {n["node_id"] for n in fig["per_node"] if len(n["loci"]) == 1}
        assert heat == multi, f"{fig['id']}: heatmap set does not match multi-locus set"
        assert not (heat & single), "a single-locus node was given a heatmap"


def test_the_heatmap_is_drawn_and_fits_inside_its_node():
    from qbio import render
    from qbio.layout import Box

    class NS:
        timepoints = ("t1", "t2", "t3", "t4")
        per_locus = {
            "AT1G32350": (1.0, 1.0, 1.0, 1.0),
            "AT5G64210": (0.0, 1.0, -1.0, -1.0),
        }

    w, h = render.heatmap_size(2, 4)
    box = Box(0, 0, w + 40, h + 40)
    svg, collisions = render.locus_heatmap_svg({"N": box}, {"N": NS()}, 1.0)
    assert not collisions
    assert svg.count("qbm-heat-cell") == 8
    assert "1g32350" in svg and "5g64210" in svg


def test_a_heatmap_too_big_for_its_node_is_reported_not_drawn():
    """Non-vacuity, and the refusal that matters: a clipped heatmap would be unreadable
    while still looking like data."""
    from qbio import render
    from qbio.layout import Box

    class NS:
        timepoints = tuple(f"t{i}" for i in range(12))
        per_locus = {f"AT1G0{i:04d}": tuple([1.0] * 12) for i in range(8)}

    svg, collisions = render.locus_heatmap_svg({"N": Box(0, 0, 60, 30)}, {"N": NS()}, 1.0)
    assert collisions and "does not fit" in collisions[0]
    assert "qbm-heat-cell" not in svg


def test_the_reservation_grows_for_the_widest_heatmap():
    from qbio import render

    class NS:
        timepoints = ("t1", "t2", "t3", "t4")
        per_locus = {f"AT1G0{i:04d}": (1.0,) * 4 for i in range(6)}

    reserve = render.heatmap_reserve({"N": NS()}, min_reserve=render.SPARK_RESERVE)
    assert reserve > render.SPARK_RESERVE
    assert reserve >= render.heatmap_size(6, 4)[1]


def test_a_single_locus_node_does_not_grow_the_reservation():
    from qbio import render

    class NS:
        timepoints = ("t1",)
        per_locus = {"AT1G00001": (1.0,)}

    assert render.heatmap_reserve({"N": NS()}, min_reserve=render.SPARK_RESERVE) \
        == render.SPARK_RESERVE
