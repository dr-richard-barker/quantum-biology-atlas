"""Orthology, OSDR ingestion and data projection.

The assertions that matter most here are the REFUSALS. An empty join that renders as
a blank map, or a 3%-coverage overlay presented as a figure, are worse failures than
a crash — they look like results. Each refusal is tested by constructing the failing
condition deliberately.
"""
from __future__ import annotations

import pathlib

import pytest

from qbio import ortho, project
from qbio.osdr import ExpressionTable, OsdrError, parse_expression


# ---------------------------------------------------------------------------
# OSDR parsing — offline, on fixtures
# ---------------------------------------------------------------------------
def _de_table(gene_col: str = "TAIR", extra_contrast: bool = False) -> str:
    rows = [
        f"{gene_col},SYMBOL,GENENAME,Log2fc_(FLT)v(GC),Adj.p.value_(FLT)v(GC)"
        + (",Log2fc_(FLT)v(LN2)" if extra_contrast else ""),
        "AT4G35830,ACO1,aconitase 1,-0.81,0.004" + (",0.22" if extra_contrast else ""),
        "AT5G66760,SDH1-1,succinate dehydrogenase,0.42,0.031" + (",-0.10" if extra_contrast else ""),
        "AT1G22840,CYTC-1,cytochrome c-1,0.55,0.500" + (",0.05" if extra_contrast else ""),
    ]
    return "\n".join(rows)


def test_gene_column_is_chosen_by_content_not_name():
    """GENENAME holds free-text descriptions in OSDR's Arabidopsis tables. Choosing it
    on a name hint produced 5,788 rows keyed on prose; scoring by content gives loci."""
    text = _de_table().replace(
        "aconitase 1", "ENCODES AN ACONITASE. MUTATIONS CAUSE EMBRYO LETHALITY."
    )
    t = parse_expression(text, source="fixture")
    assert t.gene_column == "TAIR"
    assert set(t.values) == {"AT4G35830", "AT5G66760", "AT1G22840"}


def test_ambiguous_contrast_raises_rather_than_picking_one():
    """Silently taking the first of several contrasts attaches the wrong comparison
    to a figure, and is close to undetectable downstream."""
    with pytest.raises(OsdrError, match="none was chosen"):
        parse_expression(_de_table(extra_contrast=True), source="fixture")


def test_named_contrast_is_selected():
    t = parse_expression(_de_table(extra_contrast=True), source="fixture", contrast="(FLT)v(LN2)")
    assert t.contrast == "Log2fc_(FLT)v(LN2)"
    assert t.values["AT4G35830"] == pytest.approx(0.22)


def test_zero_usable_rows_raises():
    text = "TAIR,Log2fc_(A)v(B)\nAT1G01010,not-a-number\n"
    with pytest.raises(OsdrError, match="0 usable rows"):
        parse_expression(text, source="fixture")


def test_missing_lfc_column_raises():
    with pytest.raises(OsdrError, match="no log2-fold-change column"):
        parse_expression("TAIR,SYMBOL\nAT1G01010,X\n", source="fixture")


def test_significance_filter_refuses_without_a_padj_column():
    """Reporting 'significant at p<=0.05' when no p-value was present would be a
    fabricated claim, so the filter raises instead of silently passing everything."""
    text = "TAIR,Log2fc_(A)v(B)\nAT4G35830,-0.8\nAT5G66760,0.4\n"
    t = parse_expression(text, source="fixture")
    with pytest.raises(OsdrError, match="no adjusted p-value"):
        t.significant()


# ---------------------------------------------------------------------------
# projection — offline
# ---------------------------------------------------------------------------
def _entities(onto, ids):
    return [(i.split(":")[1], onto[i]) for i in ids]


def test_projection_joins_and_reports_coverage(onto):
    table = parse_expression(_de_table(), source="fixture", organism="Arabidopsis")
    nodes = _entities(onto, ["QBO:ACONITASE", "QBO:COMPLEX_II", "QBO:CYTOCHROME_C", "QBO:O2"])
    p = project.project_expression(map_id="TEST", nodes=nodes, table=table)

    assert p.nodes_with_data == 3
    assert "O2" in p.nodes_without_loci          # a metabolite cannot receive data
    assert p.fraction_covered == 1.0
    assert "fixture" in p.provenance()
    assert "aggregated by mean" in p.provenance()


def test_projection_refuses_an_empty_join(onto):
    """The single most dangerous silent failure: a blank map that looks like a result."""
    text = "gene_id,Log2fc_(A)v(B)\nENSG00000000003,-1.2\nENSG00000000005,0.4\n"
    table = parse_expression(text, source="fixture-human")
    nodes = _entities(onto, ["QBO:ACONITASE", "QBO:COMPLEX_II"])
    with pytest.raises(project.ProjectionError, match="Refusing to return an empty projection"):
        project.project_expression(map_id="TEST", nodes=nodes, table=table)


def test_projection_refuses_low_coverage_unless_asked(onto):
    text = "TAIR,Log2fc_(A)v(B)\nAT4G35830,-0.8\n"
    table = parse_expression(text, source="fixture")
    nodes = _entities(
        onto,
        ["QBO:ACONITASE", "QBO:COMPLEX_II", "QBO:CYTOCHROME_C", "QBO:COMPLEX_I",
         "QBO:RIESKE_FES", "QBO:AOX", "QBO:LIPOYL_SYNTHASE", "QBO:ALT_NADH_DH"],
    )
    with pytest.raises(project.ProjectionError, match="would mislead"):
        project.project_expression(map_id="TEST", nodes=nodes, table=table)

    p = project.project_expression(
        map_id="TEST", nodes=nodes, table=table, allow_low_coverage=True
    )
    assert p.fraction_covered < 0.25
    assert "12%" in p.provenance() or "13%" in p.provenance()   # coverage is stated


def test_unknown_aggregator_raises(onto):
    table = parse_expression(_de_table(), source="fixture")
    with pytest.raises(project.ProjectionError, match="unknown aggregator"):
        project.project_expression(
            map_id="TEST", nodes=_entities(onto, ["QBO:ACONITASE"]),
            table=table, aggregator="geometric-mean",
        )


def test_aggregators_differ_where_it_matters(onto):
    """`extreme` exists because averaging washes out one responding subunit of a
    complex whose others do not move."""
    text = ("TAIR,Log2fc_(A)v(B),Adj.p.value_(A)v(B)\n"
            "AT5G66760,2.0,0.01\nAT3G27380,0.0,0.9\nAT5G40650,0.0,0.9\n"
            "AT5G09600,0.0,0.9\nAT2G46505,0.0,0.9\n")
    table = parse_expression(text, source="fixture")
    nodes = _entities(onto, ["QBO:COMPLEX_II"])
    mean = project.project_expression(map_id="T", nodes=nodes, table=table, aggregator="mean")
    extreme = project.project_expression(map_id="T", nodes=nodes, table=table, aggregator="extreme")
    assert mean.values["COMPLEX_II"].value == pytest.approx(0.4)
    assert extreme.values["COMPLEX_II"].value == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# orthology
# ---------------------------------------------------------------------------
def test_same_species_projection_is_refused():
    with pytest.raises(ortho.OrthologyError, match="nothing to project"):
        ortho.project(["AT4G35830"], "arabidopsis_thaliana")


def test_orthodb_matrix_strips_version_suffixes():
    if ortho.find_orthodb_matrix() is None:
        pytest.skip("OrthoDB matrix not present in data/external/")
    hits = ortho.orthodb_orthologs(["AT4G35830"], "homo_sapiens")
    assert hits, "aconitase 1 should have a human ortholog in the committed matrix"
    assert all("." not in h.target_id for h in hits), "Ensembl version suffix not stripped"


@pytest.mark.network
def test_pan_homology_is_the_division_that_crosses_kingdoms():
    """`plants` does not reach animals; `pan_homology` does. The whole cross-kingdom
    capability rests on this, so it is checked rather than assumed."""
    divisions = ortho.available_divisions()
    assert "pan_homology" in divisions, f"pan_homology missing from {divisions}"

    fly = ortho.ensembl_orthologs(["AT4G08920"], "drosophila_melanogaster")
    assert fly, "AtCRY1 should return a Drosophila ortholog under pan_homology"

    plants_only = ortho.ensembl_orthologs(
        ["AT4G08920"], "drosophila_melanogaster", division="plants"
    )
    assert not plants_only, "the plants division should NOT reach Drosophila"


@pytest.mark.network
def test_projection_reports_coverage_and_never_silently_drops(onto):
    loci = sorted(onto.index_by_agi())[:12]
    by_locus, coverage = ortho.project(loci, "homo_sapiens", allow_empty=True)
    assert set(by_locus) == {l.upper() for l in loci}, "some loci vanished from the result"
    assert coverage.requested == len(loci)
    assert coverage.mapped + len(coverage.unmapped) == coverage.requested, (
        "coverage does not account for every requested locus"
    )
    assert coverage.methods_used, "no orthology method was recorded"
