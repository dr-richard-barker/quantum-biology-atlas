"""Perturbation comparison: thresholds, overlap, divergence and the moved specificity test.

Two of these guard things that would quietly change a published conclusion:

  * `specificity_test` moved out of `build_osd8_showcase.py` so the radiation page could
    use the same function. The OSD-8 page is already live with its numbers, so the move
    has to be provably neutral.
  * The permutation pool is built in sorted key order. Without that a *seeded* test
    still gave a different p-value on every run, because an upstream parser iterated a
    `set` and Python randomises string hashing per process. The page claimed the
    p-values reproduced exactly; they did not.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from qbio import compare

ROOT = pathlib.Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# responding
# ---------------------------------------------------------------------------


def test_one_threshold_decides_for_every_perturbation():
    """Two hand-tuned thresholds would let the overlap be dialled to any value."""
    assert compare.responds(0.6)[0] is True
    assert compare.responds(-0.6)[0] is True
    assert compare.responds(0.4)[0] is False
    assert compare.RESPONSE_THRESHOLD == 0.5


def test_a_series_is_judged_on_its_extreme_not_its_mean():
    """A gene that rises then falls averages to nothing; calling that 'no response' is
    the error the time-series machinery exists to avoid."""
    rises_then_falls = [1.4, 0.2, -1.3]
    assert compare.responds(rises_then_falls) == (True, 1.4)
    assert abs(sum(rises_then_falls) / 3) < compare.RESPONSE_THRESHOLD


def test_an_all_missing_series_does_not_respond():
    assert compare.responds([None, None]) == (False, 0.0)


def test_direction_is_zero_when_it_did_not_respond():
    r = compare.Response("x", "p", 0.1, responded=False)
    assert r.direction == 0


# ---------------------------------------------------------------------------
# overlap
# ---------------------------------------------------------------------------


def _resp(values, perturbation):
    return compare.responses(values, perturbation)


def test_a_unit_that_moved_under_nothing_is_not_counted_as_agreeing():
    """Otherwise every unmeasured, unmoved locus inflates the agreement count."""
    a = _resp({"g": 0.1}, "a")
    b = _resp({"g": 0.1}, "b")
    row = compare.overlap({"a": a, "b": b})[0]
    assert row.responded_in == []
    assert row.directions_agree() is None
    assert row.is_shared is False


def test_direction_agreement_distinguishes_same_from_opposite():
    same = compare.overlap({"a": _resp({"g": 1.0}, "a"), "b": _resp({"g": 0.9}, "b")})[0]
    opposite = compare.overlap({"a": _resp({"g": 1.0}, "a"), "b": _resp({"g": -0.9}, "b")})[0]
    assert same.directions_agree() is True
    assert opposite.directions_agree() is False
    assert same.is_shared and opposite.is_shared


def test_only_units_measured_everywhere_are_compared():
    """A locus absent from one dataset is not evidence that it failed to respond there."""
    rows = compare.overlap({"a": _resp({"x": 1.0, "y": 1.0}, "a"), "b": _resp({"x": 1.0}, "b")})
    assert [r.key for r in rows] == ["x"]


def test_overlap_needs_two_perturbations():
    with pytest.raises(compare.ComparisonError):
        compare.overlap({"a": _resp({"g": 1.0}, "a")})


def test_overlap_with_no_shared_unit_raises():
    with pytest.raises(compare.ComparisonError, match="measured in every"):
        compare.overlap({"a": _resp({"x": 1.0}, "a"), "b": _resp({"y": 1.0}, "b")})


# ---------------------------------------------------------------------------
# chance
# ---------------------------------------------------------------------------


def _rows(n, a_responders, b_responders):
    a = {f"g{i}": compare.Response(f"g{i}", "a", 1.0 if i in a_responders else 0.0,
                                   i in a_responders) for i in range(n)}
    b = {f"g{i}": compare.Response(f"g{i}", "b", 1.0 if i in b_responders else 0.0,
                                   i in b_responders) for i in range(n)}
    return compare.overlap({"a": a, "b": b})


def test_chance_test_separates_perfect_overlap_from_none():
    """Non-vacuity: it must give different answers for the two extremes."""
    n = 100
    same = set(range(30))
    perfect = compare.overlap_exceeds_chance(_rows(n, same, same), ["a", "b"],
                                             permutations=2000)
    disjoint = compare.overlap_exceeds_chance(
        _rows(n, set(range(30)), set(range(30, 60))), ["a", "b"], permutations=2000)
    assert perfect["observed_overlap"] == 30
    assert disjoint["observed_overlap"] == 0
    assert perfect["p_value"] < 0.01
    assert disjoint["p_value"] > 0.5


def test_chance_test_refuses_below_a_minimum_n():
    """The six-node NNMF arm must never receive a p-value.

    A permutation p-value on a handful of units is not a weak result, it is an
    uninterpretable one, and printing it would lend it credibility it cannot have.
    """
    with pytest.raises(compare.ComparisonError, match="no permutation test"):
        compare.overlap_exceeds_chance(_rows(6, {0, 1}, {1, 2}), ["a", "b"])


def test_a_permutation_p_value_is_never_zero():
    r = compare.overlap_exceeds_chance(_rows(100, set(range(30)), set(range(30))),
                                       ["a", "b"], permutations=500)
    assert r["p_value"] > 0


def test_chance_test_compares_exactly_two():
    with pytest.raises(compare.ComparisonError, match="exactly two"):
        compare.overlap_exceeds_chance(_rows(30, {1}, {1}), ["a", "b", "c"])


# ---------------------------------------------------------------------------
# specificity — the moved function
# ---------------------------------------------------------------------------


def test_specificity_is_reproducible_across_calls():
    """The defect this guards: a seeded test that still moved between runs.

    `parse_platform` built its index by iterating a set, so the caller's dict key order
    differed every process, `random.sample` drew different background loci, and the
    p-value shifted while the page claimed it reproduced exactly.
    """
    values = {f"g{i}": (i % 17) / 10 - 0.8 for i in range(2000)}
    selected = {f"g{i}" for i in range(0, 2000, 13)}
    a = compare.specificity_test(values, selected, permutations=500)
    b = compare.specificity_test(values, selected, permutations=500)
    assert a == b


def test_specificity_is_independent_of_input_dict_order():
    """Stronger than the above: shuffling the caller's dict must not move the number."""
    import random as _r

    values = {f"g{i}": (i % 17) / 10 - 0.8 for i in range(2000)}
    selected = {f"g{i}" for i in range(0, 2000, 13)}
    keys = list(values)
    _r.Random(1).shuffle(keys)
    shuffled = {k: values[k] for k in keys}
    assert (compare.specificity_test(values, selected, permutations=500)
            == compare.specificity_test(shuffled, selected, permutations=500))


def test_specificity_refuses_too_few_selected():
    with pytest.raises(compare.ComparisonError, match="not interpretable"):
        compare.specificity_test({f"g{i}": 0.1 for i in range(100)}, {"g0", "g1"})


def test_specificity_refuses_a_background_smaller_than_the_selection():
    vals = {f"g{i}": 0.1 for i in range(20)}
    with pytest.raises(compare.ComparisonError, match="nothing to compare"):
        compare.specificity_test(vals, set(list(vals)[:15]))


def test_both_build_scripts_route_through_qbio_compare():
    """The comparison the radiation page draws is only valid if one function made both
    numbers. Asserted on the source, because a second local copy of the test would look
    identical in the output and differ in the draws."""
    osd8 = (ROOT / "scripts" / "build_osd8_showcase.py").read_text()
    rad = (ROOT / "scripts" / "build_osd782_showcase.py").read_text()
    for name, src in (("build_osd8_showcase", osd8), ("build_osd782_showcase", rad)):
        assert "compare.specificity_test" in src, (
            f"{name} does not call qbio.compare.specificity_test, so its numbers are "
            f"not comparable with the other page's"
        )
        assert "def specificity_test" not in src.replace(
            "def specificity_test(values, qbo_loci, *, n=N_PERMUTATIONS, seed=SEED):", ""
        ), f"{name} defines its own specificity test again"


@pytest.mark.parametrize("record,key", [
    ("results/osd8/record.json", "specificity"),
    ("results/osd782/record.json", "specificity"),
])
def test_both_pages_report_the_same_permutation_settings(record, key):
    p = ROOT / record
    if not p.exists():
        pytest.skip(f"{record} not built")
    rec = json.loads(p.read_text())
    entries = []
    for v in rec[key].values():
        entries.extend(v.values() if "p_value" not in v else [v])
    assert entries, f"{record} reports no specificity result"
    for s in entries:
        assert s["permutations"] == compare.DEFAULT_PERMUTATIONS
        assert s["seed"] == compare.DEFAULT_SEED
