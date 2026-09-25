"""
Project measured expression data onto a QBM map.

This is where the three layers meet: a map's QBO-annotated nodes carry AGI loci, an
OSDR study carries per-gene statistics, and — when the data is not Arabidopsis —
`qbio.ortho` bridges the two.

The base maps carry no numbers at all. Everything quantitative on a rendered figure
arrives through this module, from a named study and a named contrast, and the
provenance travels with it into the caption. That is deliberate: the figures this
atlas replaces had their "data" bars hard-coded (six panels, all `1.0` vs `1.0 ± 0.4`
from a hand-written direction list), and the only structural defence against that
recurring is to make measured values the sole path to a rendered number.

Reported, never hidden:
  * nodes with no locus at all — they cannot receive data by construction
  * nodes whose loci are in the ontology but absent from the study
  * nodes whose loci map to several genes, and how those were combined
  * for cross-species work, which orthology method supplied each mapping
"""
from __future__ import annotations

import dataclasses
import statistics
from typing import Callable, Iterable, Sequence

from .ontology import Entity, Ontology
from .osdr import ExpressionTable, OsdrError
from .ortho import Coverage, Ortholog, OrthologyError, project as project_orthologs


class ProjectionError(Exception):
    """Raised when a projection would be misleading. Never downgraded to a warning."""


#: How several loci on one node collapse to a single displayed value. `mean` is the
#: default; `extreme` (largest absolute change) is useful when one subunit of a
#: complex responds and the rest do not, which averaging would wash out.
AGGREGATORS: dict[str, Callable[[Sequence[float]], float]] = {
    "mean": lambda v: statistics.fmean(v),
    "median": lambda v: statistics.median(v),
    "extreme": lambda v: max(v, key=abs),
    "min": min,
    "max": max,
}


@dataclasses.dataclass
class NodeValue:
    node_id: str
    qbo_id: str | None
    value: float
    n_loci: int
    loci_used: tuple[str, ...]
    loci_missing: tuple[str, ...]
    aggregator: str
    evidence_tier: str
    significant: bool | None = None
    via_orthologs: tuple[str, ...] = ()


@dataclasses.dataclass
class Projection:
    """The result of projecting one contrast onto one map."""

    map_id: str
    study: str
    contrast: str
    organism: str | None
    aggregator: str
    values: dict[str, NodeValue]
    nodes_total: int
    nodes_without_loci: tuple[str, ...]
    nodes_unmatched: tuple[str, ...]
    ortholog_coverage: Coverage | None = None
    alpha: float | None = None

    @property
    def nodes_with_data(self) -> int:
        return len(self.values)

    @property
    def fraction_covered(self) -> float:
        addressable = self.nodes_total - len(self.nodes_without_loci)
        return self.nodes_with_data / addressable if addressable else 0.0

    def by_tier(self) -> dict[str, list[NodeValue]]:
        out: dict[str, list[NodeValue]] = {}
        for v in self.values.values():
            out.setdefault(v.evidence_tier, []).append(v)
        return out

    def provenance(self) -> str:
        """One paragraph, written into the figure caption. Never omitted."""
        bits = [
            f"Data: {self.study}, contrast {self.contrast}",
            f"organism {self.organism or 'not stated in the study record'}",
            f"{self.nodes_with_data} of {self.nodes_total - len(self.nodes_without_loci)} "
            f"identifier-bearing nodes received a value "
            f"({self.fraction_covered:.0%}); "
            f"{len(self.nodes_without_loci)} nodes carry no gene identifier and cannot",
            f"multi-locus nodes aggregated by {self.aggregator}",
        ]
        if self.alpha is not None:
            bits.append(f"significance at adjusted p ≤ {self.alpha}")
        if self.ortholog_coverage:
            c = self.ortholog_coverage
            bits.append(
                f"orthology {c.source_species} → {c.target_species} via "
                f"{', '.join(c.methods_used)} ({c.mapped}/{c.requested} loci, "
                f"{len(c.disagreed)} method disagreements)"
            )
        if self.nodes_unmatched:
            bits.append(
                f"no measurement found for: {', '.join(self.nodes_unmatched[:6])}"
                + ("…" if len(self.nodes_unmatched) > 6 else "")
            )
        return ". ".join(bits) + "."

    def summary(self) -> str:
        lines = [self.provenance(), ""]
        for tier in ("T1", "T2", "T3", "T4"):
            vals = self.by_tier().get(tier, [])
            if not vals:
                continue
            mean = statistics.fmean(v.value for v in vals)
            lines.append(f"  {tier}: n={len(vals):>3}  mean log2FC {mean:+.3f}")
        return "\n".join(lines)


def project_expression(
    *,
    map_id: str,
    nodes: Sequence[tuple[str, Entity | None]],
    table: ExpressionTable,
    aggregator: str = "mean",
    alpha: float | None = 0.05,
    target_species: str | None = None,
    source_species: str = "arabidopsis_thaliana",
    allow_low_coverage: bool = False,
) -> Projection:
    """Join an expression table onto a map's nodes.

    `nodes` is (node_id, ontology entity or None) in map order. When `target_species`
    is given and differs from `source_species`, Arabidopsis loci are first projected
    through `qbio.ortho` and the resulting ids are matched against the table instead.
    """
    if aggregator not in AGGREGATORS:
        raise ProjectionError(
            f"unknown aggregator {aggregator!r} — choose from {sorted(AGGREGATORS)}"
        )
    combine = AGGREGATORS[aggregator]

    without_loci = tuple(nid for nid, ent in nodes if not (ent and ent.agi))
    addressable = [(nid, ent) for nid, ent in nodes if ent and ent.agi]
    if not addressable:
        raise ProjectionError(
            f"{map_id}: no node carries a gene identifier, so no data can be projected. "
            f"Bind AGI loci in the ontology before attempting an overlay."
        )

    # ---- cross-species bridge -------------------------------------------
    coverage: Coverage | None = None
    locus_to_query: dict[str, tuple[str, ...]] = {}
    all_loci = sorted({l for _, ent in addressable for l in ent.agi})

    if target_species and target_species != source_species:
        try:
            by_locus, coverage = project_orthologs(
                all_loci, target_species, source_species=source_species
            )
        except OrthologyError as e:
            raise ProjectionError(f"{map_id}: orthology projection failed — {e}") from None
        for locus, orths in by_locus.items():
            locus_to_query[locus] = tuple(dict.fromkeys(o.target_id for o in orths))
    else:
        locus_to_query = {l: (l,) for l in all_loci}

    # ---- join -------------------------------------------------------------
    values: dict[str, NodeValue] = {}
    unmatched: list[str] = []

    for nid, ent in addressable:
        hits: list[float] = []
        used: list[str] = []
        missing: list[str] = []
        via: list[str] = []
        sig_flags: list[bool] = []

        for locus in ent.agi:
            queries = locus_to_query.get(locus.upper(), ())
            found = False
            for q in queries:
                v = table.values.get(q.upper())
                if v is None:
                    continue
                hits.append(v)
                used.append(locus)
                if q.upper() != locus.upper():
                    via.append(f"{locus}→{q}")
                if table.padj and alpha is not None:
                    sig_flags.append(table.padj.get(q.upper(), 1.0) <= alpha)
                found = True
            if not found:
                missing.append(locus)

        if not hits:
            unmatched.append(nid)
            continue

        values[nid] = NodeValue(
            node_id=nid,
            qbo_id=ent.id,
            value=float(combine(hits)),
            n_loci=len(hits),
            loci_used=tuple(dict.fromkeys(used)),
            loci_missing=tuple(missing),
            aggregator=aggregator,
            evidence_tier=ent.evidence_tier,
            significant=(any(sig_flags) if sig_flags else None),
            via_orthologs=tuple(via),
        )

    projection = Projection(
        map_id=map_id,
        study=table.source,
        contrast=table.contrast,
        organism=table.organism,
        aggregator=aggregator,
        values=values,
        nodes_total=len(nodes),
        nodes_without_loci=without_loci,
        nodes_unmatched=tuple(unmatched),
        ortholog_coverage=coverage,
        alpha=alpha if table.padj else None,
    )

    if not values:
        raise ProjectionError(
            f"{map_id}: not one of {len(addressable)} identifier-bearing nodes matched "
            f"{table.source}. Refusing to return an empty projection — it would render "
            f"as a map with no data and look like a result.\n"
            f"  map loci sample : {all_loci[:5]}\n"
            f"  table key sample: {list(table.values)[:5]}\n"
            f"  Most likely the identifier namespaces differ (AGI vs Ensembl vs Entrez)."
        )
    if projection.fraction_covered < 0.25 and not allow_low_coverage:
        raise ProjectionError(
            f"{map_id}: only {projection.fraction_covered:.0%} of identifier-bearing "
            f"nodes matched {table.source}. That is low enough that the figure would "
            f"mislead. Pass allow_low_coverage=True to render it anyway — the coverage "
            f"is stated in the caption either way.\n{projection.provenance()}"
        )
    return projection


# ---------------------------------------------------------------------------
# time series
# ---------------------------------------------------------------------------
#
# Everything above projects ONE contrast: a single number per node, a single snapshot.
# A time course is a different object, and flattening it to a mean before it reaches the
# map would destroy the thing that makes it worth drawing — a gene that rises at 10 min
# and falls by 96 h averages to "no response", which is the opposite of what happened.
#
# So a series is carried intact to the renderer, and the collapse to a single colour
# happens at the last possible moment, explicitly, by `extreme` rather than `mean`.


@dataclasses.dataclass
class NodeSeries:
    """One node's measurements across the whole time course."""

    node_id: str
    qbo_id: str | None
    timepoints: tuple[str, ...]
    points: tuple[float | None, ...]
    sds: tuple[float | None, ...]
    n_loci: int
    loci_used: tuple[str, ...]
    loci_missing: tuple[str, ...]
    aggregator: str
    evidence_tier: str
    #: locus -> its own trace, kept alongside the aggregate so a node standing for a
    #: gene family can be drawn per locus. The aggregate alone cannot show a family
    #: splitting, and under a strong perturbation families do split.
    per_locus: dict[str, tuple[float | None, ...]] = dataclasses.field(default_factory=dict)
    #: Per timepoint: did the contributing loci disagree in SIGN at that timepoint?
    #:
    #: A node standing for a gene family can hide a real split. The alternative oxidases
    #: are the case that forced this: under radiation AOX1D rises steadily while AOX2
    #: falls at 24 h, and `extreme` then picks a different gene at each timepoint, so
    #: the node's trace swung from -2.43 to +3.96 and looked like a dramatic reversal.
    #: It is not the biology, it is the aggregator switching lanes. A node with
    #: divergence cannot be honestly summarised by one number, and the figure has to
    #: say so rather than draw the swing.
    diverged: tuple[bool, ...] = ()

    @property
    def observed(self) -> list[float]:
        return [p for p in self.points if p is not None]

    @property
    def loci_diverge(self) -> bool:
        """True if the contributing loci disagreed in sign at any timepoint."""
        return any(self.diverged)

    @property
    def n_diverging_timepoints(self) -> int:
        return sum(1 for d in self.diverged if d)

    def extreme(self) -> float:
        """The timepoint furthest from no-change, in either direction."""
        return max(self.observed, key=abs)

    def peak_timepoint(self) -> str:
        i = max(
            (i for i, p in enumerate(self.points) if p is not None),
            key=lambda i: abs(self.points[i]),
        )
        return self.timepoints[i]

    def crosses_zero(self) -> bool:
        """True when the node changes direction during the course.

        Worth surfacing on its own: it is precisely the behaviour a single-contrast
        overlay cannot represent, and the reason this module exists.
        """
        obs = self.observed
        return any(a * b < 0 for a, b in zip(obs, obs[1:]))


@dataclasses.dataclass
class SeriesProjection:
    """The result of projecting a whole time course onto one map, for one tissue."""

    map_id: str
    study: str
    tissue: str
    organism: str | None
    aggregator: str
    timepoints: tuple[str, ...]
    values: dict[str, NodeSeries]
    nodes_total: int
    nodes_without_loci: tuple[str, ...]
    nodes_unmatched: tuple[str, ...]
    source_provenance: str = ""
    scale_note: str = ""

    @property
    def nodes_with_data(self) -> int:
        return len(self.values)

    @property
    def fraction_covered(self) -> float:
        addressable = self.nodes_total - len(self.nodes_without_loci)
        return self.nodes_with_data / addressable if addressable else 0.0

    def vmax(self) -> float:
        vals = [abs(p) for ns in self.values.values() for p in ns.observed]
        return max(vals) if vals else 0.0

    def at(self, index: int) -> Projection:
        """One timepoint as an ordinary `Projection`, for the existing renderer.

        This is what makes small multiples cost nothing: each panel is a normal
        single-contrast projection and goes through exactly the same code path as an
        OSDR overlay, so a time-course panel and a spaceflight map are directly
        comparable rather than merely similar.
        """
        tp = self.timepoints[index]
        values = {
            nid: NodeValue(
                node_id=nid,
                qbo_id=ns.qbo_id,
                value=ns.points[index],
                n_loci=ns.n_loci,
                loci_used=ns.loci_used,
                loci_missing=ns.loci_missing,
                aggregator=ns.aggregator,
                evidence_tier=ns.evidence_tier,
                significant=None,
            )
            for nid, ns in self.values.items()
            if ns.points[index] is not None
        }
        return Projection(
            map_id=self.map_id,
            study=f"{self.study} — {self.tissue.lower()}, {tp}",
            contrast=f"{self.tissue.lower()} at {tp}",
            organism=self.organism,
            aggregator=self.aggregator,
            values=values,
            nodes_total=self.nodes_total,
            nodes_without_loci=self.nodes_without_loci,
            nodes_unmatched=self.nodes_unmatched,
            alpha=None,
        )

    def provenance(self) -> str:
        bits = [self.source_provenance] if self.source_provenance else []
        bits.append(
            f"{self.tissue.lower()}, {len(self.timepoints)} timepoints "
            f"({', '.join(self.timepoints)})"
        )
        bits.append(
            f"{self.nodes_with_data} of "
            f"{self.nodes_total - len(self.nodes_without_loci)} identifier-bearing nodes "
            f"received a series ({self.fraction_covered:.0%}); "
            f"{len(self.nodes_without_loci)} nodes carry no gene identifier and cannot"
        )
        bits.append(f"multi-locus nodes aggregated by {self.aggregator} at each timepoint")
        if self.scale_note:
            bits.append(self.scale_note)
        split = [n for n, ns in self.values.items() if ns.loci_diverge]
        if split:
            bits.append(
                f"{len(split)} node(s) have loci that disagree in direction at the same "
                f"timepoint ({', '.join(split[:4])}{'…' if len(split) > 4 else ''}), so "
                f"their single trace is the aggregator choosing between genes that are "
                f"doing different things — read those per locus, not as a node"
            )
        reversing = [n for n, ns in self.values.items() if ns.crosses_zero()]
        if reversing:
            bits.append(
                f"{len(reversing)} node(s) reverse direction during the course "
                f"({', '.join(reversing[:4])}{'…' if len(reversing) > 4 else ''}), "
                f"which no single-contrast overlay can show"
            )
        return ". ".join(b.rstrip(".") for b in bits if b) + "."


def project_series(
    *,
    map_id: str,
    nodes: Sequence[tuple[str, Entity | None]],
    series_by_locus: dict[str, "object"],
    study: str,
    tissue: str,
    organism: str | None = None,
    aggregator: str = "extreme",
    source_provenance: str = "",
    scale_note: str = "",
    allow_low_coverage: bool = False,
) -> SeriesProjection:
    """Join a per-locus time course onto a map's nodes.

    `series_by_locus` maps an AGI locus to a `qbio.papers.Series` already converted to
    log2 — this function refuses anything still on a ratio scale, because a ratio fed to
    the renderer colours every unchanged gene as strongly upregulated and the figure
    looks entirely normal while being exactly wrong.

    The default aggregator is `extreme`, not `mean`: averaging the subunits of a complex
    where one responds and the rest do not reports that nothing happened.
    """
    if aggregator not in AGGREGATORS:
        raise ProjectionError(
            f"unknown aggregator {aggregator!r} — choose from {sorted(AGGREGATORS)}"
        )
    combine = AGGREGATORS[aggregator]

    from .papers import LOG2

    bad_scale = [l for l, s in series_by_locus.items() if getattr(s, "scale", LOG2) != LOG2]
    if bad_scale:
        raise ProjectionError(
            f"{map_id}: {len(bad_scale)} series are on a ratio scale, not log2 "
            f"(e.g. {bad_scale[:3]}). Convert with Series.to_log2() first. A ratio "
            f"renders 1.0 — no change — as a strong upregulation, and the figure gives "
            f"no sign that anything is wrong."
        )

    timepoints: tuple[str, ...] | None = None
    for s in series_by_locus.values():
        if timepoints is None:
            timepoints = tuple(s.timepoints)
        elif tuple(s.timepoints) != timepoints:
            raise ProjectionError(
                f"{map_id}: series do not share a timebase — {timepoints} vs "
                f"{tuple(s.timepoints)}. Plotting them on one axis would misdate values."
            )
    if not timepoints:
        raise ProjectionError(f"{map_id}: no series supplied")

    without_loci = tuple(nid for nid, ent in nodes if not (ent and ent.agi))
    addressable = [(nid, ent) for nid, ent in nodes if ent and ent.agi]
    if not addressable:
        raise ProjectionError(f"{map_id}: no node carries a gene identifier")

    values: dict[str, NodeSeries] = {}
    unmatched: list[str] = []

    for nid, ent in addressable:
        found = [(l, series_by_locus[l.upper()]) for l in ent.agi if l.upper() in series_by_locus]
        if not found:
            unmatched.append(nid)
            continue
        points: list[float | None] = []
        sds: list[float | None] = []
        diverged: list[bool] = []
        per_locus: dict[str, list[float | None]] = {l: [] for l, _ in found}
        for i in range(len(timepoints)):
            for locus, s in found:
                m = s.points[i]
                per_locus[locus].append(None if m is None else float(m.value))
            at_t = [s.points[i] for _, s in found if s.points[i] is not None]
            if not at_t:
                points.append(None)
                sds.append(None)
                diverged.append(False)
                continue
            signs = {1 if m.value > 0 else -1 if m.value < 0 else 0 for m in at_t}
            diverged.append(1 in signs and -1 in signs)
            points.append(float(combine([m.value for m in at_t])))
            # The dispersion shown is the largest reported, not a pooled estimate:
            # these are published summary statistics with no access to the underlying
            # replicates, so pooling them would invent a precision nobody measured.
            sds.append(max(m.sd for m in at_t))
        values[nid] = NodeSeries(
            node_id=nid,
            qbo_id=ent.id,
            timepoints=timepoints,
            points=tuple(points),
            sds=tuple(sds),
            n_loci=len(found),
            loci_used=tuple(l for l, _ in found),
            loci_missing=tuple(l for l in ent.agi if l.upper() not in series_by_locus),
            aggregator=aggregator,
            evidence_tier=ent.evidence_tier,
            diverged=tuple(diverged),
            per_locus={l: tuple(v) for l, v in per_locus.items()},
        )

    proj = SeriesProjection(
        map_id=map_id, study=study, tissue=tissue, organism=organism,
        aggregator=aggregator, timepoints=timepoints, values=values,
        nodes_total=len(nodes), nodes_without_loci=without_loci,
        nodes_unmatched=tuple(unmatched),
        source_provenance=source_provenance, scale_note=scale_note,
    )

    if not values:
        raise ProjectionError(
            f"{map_id}: not one of {len(addressable)} identifier-bearing nodes matched "
            f"{study}. Refusing to return an empty projection.\n"
            f"  map loci sample   : {[l for _, e in addressable for l in e.agi][:5]}\n"
            f"  series key sample : {list(series_by_locus)[:5]}"
        )
    if proj.fraction_covered < 0.25 and not allow_low_coverage:
        raise ProjectionError(
            f"{map_id}: only {proj.fraction_covered:.0%} of identifier-bearing nodes "
            f"matched {study}. Pass allow_low_coverage=True to render it anyway — the "
            f"coverage is stated in the caption either way.\n{proj.provenance()}"
        )
    return proj
