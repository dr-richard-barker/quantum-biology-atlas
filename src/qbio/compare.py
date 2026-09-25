"""
Comparing one perturbation against another.

Two questions the atlas could not previously ask, both of which need the *same* code to
run on both sides or the comparison is worthless:

**Does this locus set respond specially?** `specificity_test` permutes the background:
do the ontology's loci move more than the same number of loci drawn at random from the
same experiment? It lives here rather than in a build script because the OSD-8 page and
the OSD-782 page both report it, and two differently-computed numbers cannot be compared.

**Do two perturbations move the same nodes?** `overlap` cross-tabulates per node. That
is the question "does ionising radiation touch the same chemistry a magnetic field
does" reduced to something checkable.

Three disciplines this module enforces, each because the alternative produces a
plausible-looking number with nothing behind it:

  * **One threshold, both sides.** `responds()` is the single place that decides whether
    something moved. Two hand-tuned thresholds would let the overlap be dialled to any
    value.
  * **Direction, not magnitude.** Comparing a microarray ratio from one lab against an
    RNA-seq fold change from another on magnitude is not meaningful; agreeing on sign is.
  * **Refuse to test what cannot be tested.** `overlap_exceeds_chance` raises below a
    minimum n rather than returning a p-value computed on a handful of nodes. The
    NNMF arm of the radiation comparison is six nodes; a p-value on six rows would be a
    number with no evidence behind it.

Overlap is not shared mechanism. Catalase responds to almost every stress. This module
measures convergence and says how surprising it is; interpreting it is the page's job.
"""
from __future__ import annotations

import dataclasses
import random
import statistics
from typing import Iterable, Mapping, Sequence

#: A locus or node must move at least this far, in log2 fold change, to count as having
#: responded. 0.5 is one-and-a-half-fold. Chosen once and applied to every perturbation:
#: the point of a fixed threshold is that it cannot be tuned per dataset to produce a
#: more interesting overlap.
RESPONSE_THRESHOLD = 0.5

#: Below this many shared units, `overlap_exceeds_chance` refuses rather than returning
#: a p-value. Twenty is already generous for a permutation test on presence/absence.
MIN_N_FOR_CHANCE_TEST = 20

DEFAULT_PERMUTATIONS = 10_000
DEFAULT_SEED = 20260924


class ComparisonError(Exception):
    """Raised when a comparison would be misleading. Never downgraded to a warning."""


# ---------------------------------------------------------------------------
# did it respond?
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Response:
    """One unit's behaviour under one perturbation."""

    key: str
    perturbation: str
    value: float                     # the extreme log2 fold change observed
    responded: bool
    at: str = ""                     # the timepoint it peaked at, when there is one

    @property
    def direction(self) -> int:
        """+1, -1, or 0 when it did not respond. Zero is not a direction."""
        if not self.responded:
            return 0
        return 1 if self.value > 0 else -1


def responds(
    value_or_series: float | Sequence[float | None],
    *,
    threshold: float = RESPONSE_THRESHOLD,
) -> tuple[bool, float]:
    """Did it move? Returns (responded, the extreme value seen).

    A series is judged on its most extreme timepoint, not its mean: a gene that rises
    at 1 h and falls by 72 h averages to nothing, and calling that "no response" is the
    error the time-series machinery exists to avoid.
    """
    if isinstance(value_or_series, (int, float)):
        extreme = float(value_or_series)
    else:
        observed = [v for v in value_or_series if v is not None]
        if not observed:
            return (False, 0.0)
        extreme = max(observed, key=abs)
    return (abs(extreme) >= threshold, extreme)


def responses(
    values: Mapping[str, float | Sequence[float | None]],
    perturbation: str,
    *,
    threshold: float = RESPONSE_THRESHOLD,
    at: Mapping[str, str] | None = None,
) -> dict[str, Response]:
    out = {}
    for key, v in values.items():
        responded, extreme = responds(v, threshold=threshold)
        out[key] = Response(
            key=key, perturbation=perturbation, value=extreme,
            responded=responded, at=(at or {}).get(key, ""),
        )
    return out


# ---------------------------------------------------------------------------
# overlap
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class OverlapRow:
    key: str
    by_perturbation: dict[str, Response]

    @property
    def responded_in(self) -> list[str]:
        return sorted(p for p, r in self.by_perturbation.items() if r.responded)

    @property
    def measured_in(self) -> list[str]:
        return sorted(self.by_perturbation)

    @property
    def is_shared(self) -> bool:
        return len(self.responded_in) > 1

    def directions_agree(self) -> bool | None:
        """True/False among the perturbations that responded; None if fewer than two.

        A unit that responded to nothing is not "agreeing" — it has no direction to
        agree about, and counting it as agreement would inflate every overlap.
        """
        dirs = {self.by_perturbation[p].direction for p in self.responded_in}
        if len(self.responded_in) < 2:
            return None
        return len(dirs) == 1

    def verdict(self, primary: str) -> str:
        r = self.responded_in
        if not r:
            return "neither"
        if len(r) > 1:
            return "shared"
        return f"{r[0]}_only"


def overlap(
    by_perturbation: Mapping[str, Mapping[str, Response]],
    *,
    require_measured_in_all: bool = True,
) -> list[OverlapRow]:
    """Cross-tabulate responses across perturbations, one row per shared unit.

    By default only units **measured in every perturbation** are returned. A unit absent
    from one dataset is not evidence that it failed to respond there, and letting those
    through would score missing data as a non-response.
    """
    if len(by_perturbation) < 2:
        raise ComparisonError("overlap needs at least two perturbations")
    keysets = [set(v) for v in by_perturbation.values()]
    keys = set.intersection(*keysets) if require_measured_in_all else set.union(*keysets)
    if not keys:
        raise ComparisonError(
            "no unit is measured in every perturbation, so nothing can be compared. "
            f"Sizes: { {p: len(v) for p, v in by_perturbation.items()} }"
        )
    rows = [
        OverlapRow(
            key=k,
            by_perturbation={p: v[k] for p, v in by_perturbation.items() if k in v},
        )
        for k in sorted(keys)
    ]
    return rows


def summarise(rows: Sequence[OverlapRow]) -> dict:
    shared = [r for r in rows if r.is_shared]
    agree = [r for r in shared if r.directions_agree() is True]
    return {
        "units_compared": len(rows),
        "responded_in_more_than_one": len(shared),
        "directions_agree": len(agree),
        "directions_disagree": len(shared) - len(agree),
        "shared_keys": [r.key for r in shared],
        "agreeing_keys": [r.key for r in agree],
    }


def overlap_exceeds_chance(
    rows: Sequence[OverlapRow],
    perturbations: Sequence[str],
    *,
    permutations: int = DEFAULT_PERMUTATIONS,
    seed: int = DEFAULT_SEED,
    min_n: int = MIN_N_FOR_CHANCE_TEST,
) -> dict:
    """Is the observed co-response more than two independent response sets would give?

    Keeps each perturbation's number of responders fixed and reshuffles *which* units
    responded. That is the right null: the question is not whether these perturbations
    move genes, but whether they move the *same* genes.

    Raises below `min_n`. A permutation p-value on a handful of units is not a weak
    result, it is an uninterpretable one, and reporting it would lend the number a
    credibility it cannot have.
    """
    if len(perturbations) != 2:
        raise ComparisonError("the chance test compares exactly two perturbations")
    n = len(rows)
    if n < min_n:
        raise ComparisonError(
            f"only {n} units are shared between {perturbations[0]} and "
            f"{perturbations[1]}; below {min_n} no permutation test is interpretable. "
            f"Report the overlap as a table and say that it is not tested."
        )
    a, b = perturbations
    ra = [i for i, r in enumerate(rows) if r.by_perturbation[a].responded]
    rb = [i for i, r in enumerate(rows) if r.by_perturbation[b].responded]
    observed = len(set(ra) & set(rb))

    rng = random.Random(seed)
    idx = list(range(n))
    ge = 0
    draws = []
    for _ in range(permutations):
        s = len(set(rng.sample(idx, len(ra))) & set(rng.sample(idx, len(rb))))
        draws.append(s)
        if s >= observed:
            ge += 1
    # +1 top and bottom: an exactly-zero permutation p-value is not attainable and
    # reporting one would overstate the evidence.
    p = (ge + 1) / (permutations + 1)
    return {
        "perturbations": [a, b],
        "units_compared": n,
        f"responders_{a}": len(ra),
        f"responders_{b}": len(rb),
        "observed_overlap": observed,
        "expected_overlap": round(statistics.fmean(draws), 3),
        "background_sd": round(statistics.pstdev(draws), 3),
        "p_value": round(p, 5),
        "permutations": permutations,
        "seed": seed,
        "one_sided": "observed co-response exceeds chance",
        "significant_at_0.05": p <= 0.05,
    }


# ---------------------------------------------------------------------------
# specificity — moved here from scripts/build_osd8_showcase.py
# ---------------------------------------------------------------------------


def specificity_test(
    values: Mapping[str, float],
    selected: Iterable[str],
    *,
    permutations: int = DEFAULT_PERMUTATIONS,
    seed: int = DEFAULT_SEED,
    min_n: int = 10,
) -> dict:
    """Do the selected loci respond more than the same number of random loci?

    A one-sided permutation test on mean |log2 fold change|. The null is that the
    selected set is an arbitrary subset of the experiment; the alternative is that
    selecting for quantum chemistry selects for responsiveness.

    Lives in this module, not in a build script, because the OSD-8 page and the OSD-782
    page both report it and the two numbers are only comparable if one function with one
    seed and one permutation count produced them.

    Reported whichever way it comes out. A null does not invalidate an ontology that
    selects for mechanism rather than for observed response — it constrains what a
    coloured map may be said to show.
    """
    selected = set(selected)
    measured = {g: v for g, v in values.items() if g in selected}
    if len(measured) < min_n:
        raise ComparisonError(
            f"only {len(measured)} selected loci are measured; below {min_n} the test "
            f"is not interpretable"
        )
    observed = statistics.fmean(abs(v) for v in measured.values())
    # Pool built in SORTED key order, so the draw depends only on the seed and not on
    # however the caller's dict happened to be built. Without this a seeded test is
    # still irreproducible whenever any upstream step iterated a set.
    pool = [values[g] for g in sorted(values) if g not in selected]
    if len(pool) < len(measured):
        raise ComparisonError(
            f"background pool ({len(pool)}) is smaller than the selected set "
            f"({len(measured)}); there is nothing to compare against"
        )

    rng = random.Random(seed)
    k = len(measured)
    ge = 0
    draws = []
    for _ in range(permutations):
        s = statistics.fmean(abs(v) for v in rng.sample(pool, k))
        draws.append(s)
        if s >= observed:
            ge += 1
    p = (ge + 1) / (permutations + 1)
    return {
        "n_selected_measured": k,
        "n_background_loci": len(pool),
        "observed_mean_abs_log2fc": round(observed, 5),
        "background_mean": round(statistics.fmean(draws), 5),
        "background_sd": round(statistics.pstdev(draws), 5),
        "p_value": round(p, 5),
        "permutations": permutations,
        "seed": seed,
        "one_sided": "selected loci respond MORE than random loci",
        "significant_at_0.05": p <= 0.05,
    }
