"""OSD-27: contrast selection, the fly bridge, and the collapse analysis.

The contrast filter IS the scientific claim of the OSD-27 page. The study has 420
contrasts and almost all of them change magnetic field and effective gravity together,
because diamagnetic levitation sets gravity by position inside the bore. If the filter
silently admitted one of those, the page would attribute a gravity effect to a magnetic
field and nothing about the figure would look wrong.

So the filter is tested against the real contrasts file, not a fixture: a fixture would
only prove the code agrees with what I believed the file contained.
"""
from __future__ import annotations

import csv
import json
import pathlib

import pytest

from qbio import osd27

ROOT = pathlib.Path(__file__).resolve().parents[1]
SLICE = ROOT / "data" / "external" / "osd27_field_contrasts.csv"
RECORD = ROOT / "results" / "osd27" / "record.json"


# ---------------------------------------------------------------------------
# contrast parsing and selection
# ---------------------------------------------------------------------------


def test_parse_contrast_splits_both_sides():
    c = osd27.parse_contrasts(
        'x,"(26 hour & 1G by magnetic levitator & 14 degree Celsius & Female)'
        'v(26 hour & 1G on Earth & 14 degree Celsius & Female)"\n'
    )[0]
    assert c.left == ("26 hour", osd27.MAGNET_1G, "14 degree Celsius", "Female")
    assert c.right == ("26 hour", osd27.EARTH_1G, "14 degree Celsius", "Female")
    assert c.is_single_factor
    assert c.isolates_field


def test_a_contrast_changing_two_factors_does_not_isolate_the_field():
    """The failure this guards: field and gravity moving together, which is most of
    the study and would be attributed entirely to the magnet."""
    c = osd27.parse_contrasts(
        'x,"(26 hour & 1G by magnetic levitator & 14 degree Celsius & Male)'
        'v(26 hour & 1G on Earth & 14 degree Celsius & Female)"\n'
    )[0]
    assert len(c.differing) == 2
    assert not c.is_single_factor
    assert not c.isolates_field


def test_a_single_factor_change_that_is_not_the_field_is_not_selected():
    c = osd27.parse_contrasts(
        'x,"(26 hour & 1G on Earth & 14 degree Celsius & Male)'
        'v(26 hour & 1G on Earth & 14 degree Celsius & Female)"\n'
    )[0]
    assert c.is_single_factor
    assert not c.isolates_field


def test_a_file_with_no_parseable_contrast_raises():
    with pytest.raises(osd27.OsdrError):
        osd27.parse_contrasts("just,some,columns\n")


def test_both_orientations_deduplicate_to_magnet_first():
    """The file lists A-v-B and B-v-A. Keeping both would double-count the evidence,
    and keeping the wrong one would invert the sign of every fold change."""
    text = (
        'x,"(5 day & 1G by magnetic levitator & 24 degree Celsius & Male)'
        'v(5 day & 1G on Earth & 24 degree Celsius & Male)",'
        '"(5 day & 1G on Earth & 24 degree Celsius & Male)'
        'v(5 day & 1G by magnetic levitator & 24 degree Celsius & Male)"\n'
    )
    kept = osd27.field_isolating_contrasts(osd27.parse_contrasts(text))
    assert len(kept) == 1
    assert kept[0].left[1] == osd27.MAGNET_1G, (
        "the magnet-first orientation must win, so a positive log2 fold change means "
        "'higher in the magnet'"
    )


# ---------------------------------------------------------------------------
# the sliced table
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def sliced():
    if not SLICE.exists():
        pytest.skip("OSD-27 slice not cached")
    rows = list(csv.DictReader(SLICE.open()))
    return rows


def test_the_slice_carries_exactly_five_field_isolating_contrasts(sliced):
    labels = [c[len("log2fc__"):] for c in sliced[0] if c.startswith("log2fc__")]
    assert len(labels) == 5, f"expected 5 field-isolating contrasts, got {len(labels)}"
    parsed = osd27.parse_contrasts(
        "gene," + ",".join(f'"{l}"' for l in labels) + "\n"
    )
    assert all(c.isolates_field for c in parsed), (
        "a contrast in the slice does not isolate the field — it changes gravity too"
    )


def test_every_sliced_contrast_matches_on_duration_temperature_and_sex(sliced):
    labels = [c[len("log2fc__"):] for c in sliced[0] if c.startswith("log2fc__")]
    for c in osd27.parse_contrasts("g," + ",".join(f'"{l}"' for l in labels) + "\n"):
        assert len(c.differing) == 1
        assert set(c.differing[0]) == {osd27.MAGNET_1G, osd27.EARTH_1G}


def test_the_slice_is_not_empty_and_is_keyed_on_flybase_ids(sliced):
    assert len(sliced) > 10_000
    ids = [r["gene_id"] for r in sliced[:500]]
    flybase = sum(1 for i in ids if i.upper().startswith("FBGN"))
    assert flybase / len(ids) > 0.9, f"only {flybase}/{len(ids)} look like FlyBase ids"


# ---------------------------------------------------------------------------
# the fly bridge
# ---------------------------------------------------------------------------


@pytest.mark.network
def test_atcry1_reaches_drosophila_cry():
    """The single most load-bearing ortholog call in the atlas.

    A plant-anchored quantum ontology reaching the fly's own cryptochrome is the reason
    the OSD-27 page exists, so it is checked against Ensembl rather than asserted.
    """
    from qbio import ortho

    orths = ortho.ensembl_orthologs(["AT4G08920"], "drosophila_melanogaster")
    targets = {o.target_id for o in orths}
    assert "FBgn0025680" in targets, f"AtCRY1 did not reach fly cry; got {targets}"


# ---------------------------------------------------------------------------
# the collapse analysis
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def record():
    if not RECORD.exists():
        pytest.skip("OSD-27 record not built")
    return json.loads(RECORD.read_text())


def test_the_record_reports_which_nodes_collapse_onto_one_gene(record):
    """Three distinct cryptochrome nodes land on a single fly gene.

    Left unreported, a reader sees three nodes agreeing and reads corroboration into
    one number drawn three times. The page must be able to say so, which means the
    record must carry it.
    """
    collapses = record["projection_collapses"]["nodes_sharing_a_target_gene"]
    qbm03 = [c for c in collapses if c["map"] == "QBM-03"]
    assert qbm03, "the QBM-03 collapse onto a single fly gene is not reported"
    group = qbm03[0]
    assert set(group["nodes"]) == {"CRY1", "CRY2", "TRP_TRIAD"}
    assert group["target_genes"] == ["FBgn0025680"]


def test_collapsed_nodes_really_do_carry_identical_values(record):
    """If they did not, the collapse report would be describing something else."""
    cons = {c["node_id"]: c for c in record["maps"]["QBM-03"]["consistency"]}
    series = [
        tuple(v["log2fc"] for v in cons[n]["by_contrast"].values())
        for n in ("CRY1", "CRY2", "TRP_TRIAD")
    ]
    assert len(set(series)) == 1, (
        "nodes reported as collapsing onto one gene carry different values, so the "
        "collapse report is wrong about something"
    )


def test_a_node_averaging_many_genes_is_flagged(record):
    fanout = record["projection_collapses"]["nodes_averaging_many_genes"]
    assert any(f["node_id"] == "ASC_GSH_CYCLE" for f in fanout), (
        "a node averaging ~40 fly genes is not flagged; its value reads as a "
        "measurement of one pathway when it is a mean over a gene family"
    )


def test_single_method_projection_is_not_reported_as_corroborated(record):
    """OrthoDB's committed matrix is human-anchored and cannot reach the fly."""
    methods = record["orthology"]["methods_used"]
    assert methods == ["ensembl_pan_homology"], (
        f"fly projection claims {methods}; only Ensembl can reach Drosophila here, and "
        f"listing OrthoDB would read as two-method agreement that never happened"
    )


def test_the_null_result_is_computed_not_assumed(record):
    """Every node should be 'mixed' — asserted so a future change that produces
    consistency is noticed rather than quietly contradicting the page's headline."""
    verdicts = [
        c["consistent_direction"]
        for m in record["maps"].values() if "consistency" in m
        for c in m["consistency"]
    ]
    assert verdicts, "no consistency verdicts were recorded"
    assert all(v in ("up", "down", "mixed") for v in verdicts)
    assert all(v == "mixed" for v in verdicts), (
        "a node now moves consistently across all five contrasts — the OSD-27 page "
        "states that none does, so the page's headline needs rewriting"
    )
