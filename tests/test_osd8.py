"""OSD-8: the design, the platform join, and the specificity test.

Two of these guard traps that would have produced a wrong page that looked right:

  * **The platform join.** Reading AGI from `GENE_SYMBOL` — the obvious column, and the
    one the build plan named — reaches 17 of the atlas's 125 loci. The authoritative
    identifier is in `ACCESSION_STRING`, which reaches all 125. The wrong column yields
    a page whose thin coverage looks like a property of the data.
  * **Which group isolates the field.** The page's entire claim is that exactly one
    group holds gravity fixed while the field changes. That is derived from the design
    table rather than asserted, and asserted here so a mis-typed row cannot invent a
    second one.
"""
from __future__ import annotations

import json
import pathlib
import statistics

import pytest

from qbio import osd8

ROOT = pathlib.Path(__file__).resolve().parents[1]
PLATFORM = ROOT / "data" / "external" / "GPL9020.txt"
SAMPLES = ROOT / "data" / "external" / "osd8"
RECORD = ROOT / "results" / "osd8" / "record.json"


# ---------------------------------------------------------------------------
# design
# ---------------------------------------------------------------------------


def test_exactly_one_group_isolates_the_field():
    """The page's central claim. If a second group ever qualifies, the page is wrong."""
    iso = osd8.field_isolating_groups()
    assert [g.key for g in iso] == ["MAG_1g"]
    g = iso[0]
    assert g.gravity == g.reference_gravity == "1g"
    assert g.field_tesla == 16.5 and g.reference_field_tesla == 0.0


def test_the_gravity_controls_use_no_magnet():
    """RPM and LDC are what make the field contrast interpretable."""
    grav = osd8.gravity_only_groups()
    assert {g.key for g in grav} == {"RPM_mg", "LDC_2g"}
    for g in grav:
        assert g.field_tesla == g.reference_field_tesla == 0.0
        assert g.gravity != g.reference_gravity


def test_a_group_changing_both_isolates_neither():
    mag_mg = next(g for g in osd8.GROUPS if g.key == "MAG_mg")
    assert not mag_mg.isolates_field
    assert not mag_mg.isolates_gravity


def test_every_group_declares_its_arrays_and_none_are_shared():
    seen = set()
    for g in osd8.GROUPS:
        assert g.samples, f"{g.key} declares no arrays"
        assert not (seen & set(g.samples)), f"{g.key} reuses an array from another group"
        seen |= set(g.samples)
    assert len(seen) == 20, f"expected 20 arrays across all groups, got {len(seen)}"


# ---------------------------------------------------------------------------
# platform join
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def platform():
    if not PLATFORM.exists():
        pytest.skip("GPL9020 not cached")
    return osd8.parse_platform(PLATFORM)


def test_platform_join_reaches_every_atlas_locus(platform, onto):
    by_locus, _ = platform
    qbo = set(onto.index_by_agi())
    missing = sorted(qbo - set(by_locus))
    assert not missing, f"{len(missing)} atlas loci absent from the array: {missing[:8]}"


def test_reading_only_gene_symbol_would_lose_most_of_the_coverage(platform, onto):
    """The trap, asserted so nobody 'simplifies' the parser back into it."""
    import re

    by_locus, _ = platform
    rows, started = [], False
    with PLATFORM.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if line.startswith("!platform_table_begin"):
                started = True
                continue
            if line.startswith("!platform_table_end"):
                break
            if started:
                rows.append(line.rstrip("\n").split("\t"))
    hdr = rows[0]
    i_sym, i_ctl = hdr.index("GENE_SYMBOL"), hdr.index("CONTROL_TYPE")
    agi = re.compile(r"^AT[1-5CM]G\d{5}$", re.I)
    symbol_only = {
        r[i_sym].strip().upper()
        for r in rows[1:]
        if len(r) > max(i_sym, i_ctl) and r[i_ctl].strip().upper() == "FALSE"
        and agi.match(r[i_sym].strip())
    }
    qbo = set(onto.index_by_agi())
    assert len(qbo & symbol_only) < 30, (
        "GENE_SYMBOL now covers most atlas loci; this test encodes why the parser "
        "reads ACCESSION_STRING and should be revisited"
    )
    assert len(qbo & set(by_locus)) == len(qbo)


def test_control_spots_are_excluded(platform):
    _, rep = platform
    assert rep["control_spots"] > 0
    assert rep["probes"] + rep["control_spots"] == rep["rows"]


def test_an_empty_platform_map_raises(tmp_path):
    p = tmp_path / "empty.txt"
    p.write_text("!platform_table_begin\nID\tCONTROL_TYPE\tGENE_SYMBOL\tACCESSION_STRING\n"
                 "1\tFALSE\t\t\n!platform_table_end\n")
    with pytest.raises(osd8.Osd8Error, match="0 AGI loci"):
        osd8.parse_platform(p)


# ---------------------------------------------------------------------------
# sample values
# ---------------------------------------------------------------------------


def test_a_group_with_a_missing_array_raises(platform, tmp_path):
    """Silently averaging 2 arrays where the page says 3 would misstate n."""
    by_locus, _ = platform
    with pytest.raises(osd8.Osd8Error, match="missing"):
        osd8.group_values(osd8.GROUPS[0], tmp_path, by_locus)


@pytest.mark.skipif(not SAMPLES.exists(), reason="OSD-8 sample tables not cached")
def test_group_values_are_centred_near_zero(platform):
    """A normalized log ratio should have a median near 0. A median far from it would
    mean the orientation or the normalization is not what the value definition says."""
    by_locus, _ = platform
    v, rep = osd8.group_values(osd8.GROUPS[0], SAMPLES, by_locus)
    assert rep["n_arrays"] == 3
    assert abs(statistics.median(v.values())) < 0.1


# ---------------------------------------------------------------------------
# specificity
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def record():
    if not RECORD.exists():
        pytest.skip("OSD-8 record not built")
    return json.loads(RECORD.read_text())


def test_specificity_is_tested_against_a_real_background(record):
    s = record["specificity"][record["primary_group"]]
    assert s["n_selected_measured"] == 125
    assert s["n_background_loci"] > 20_000
    assert s["permutations"] >= 1_000


def test_the_permutation_p_value_can_never_be_zero(record):
    """A p of exactly 0 is not attainable from a permutation test and reporting one
    would overstate the evidence."""
    for s in record["specificity"].values():
        assert s["p_value"] > 0


def test_the_specificity_result_is_null_and_the_page_depends_on_it(record):
    """The page states the atlas's loci are not more responsive than random loci, in
    every group. Asserted so a change that reverses it forces the page to be rewritten
    rather than silently contradicting itself."""
    for key, s in record["specificity"].items():
        assert not s["significant_at_0.05"], (
            f"group {key} now shows the QBO loci responding significantly more than "
            f"background (p={s['p_value']}); the page's headline needs rewriting"
        )


def test_no_significance_is_claimed_anywhere(record):
    """These are normalized ratios with no model fitted, so there is no adjusted
    p-value to threshold and none may appear."""
    page = ROOT / "docs" / "osd8.html"
    if page.exists():
        assert "adjusted p" not in page.read_text() or "no adjusted p-value" in page.read_text()
    for m in record["maps"].values():
        for n in m["nodes"]:
            assert "significant" not in n


def test_full_coverage_is_real_not_a_reporting_artefact(record):
    for map_id, m in record["maps"].items():
        assert m["nodes_with_data"] == m["addressable"], map_id
        assert m["fraction"] == 1.0, map_id
        assert m["nodes"], f"{map_id} reports full coverage but lists no nodes"
