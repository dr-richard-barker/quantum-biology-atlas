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
