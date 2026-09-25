#!/usr/bin/env python3
"""
Build a demonstration page from a paper's published supplementary tables.

Every other showcase in this atlas rests on a repository: OSD-38 and OSD-27 on NASA's
own processed differential expression, OSD-8 on the depositors' normalised ratios. This
one rests on a PDF's worth of supplementary spreadsheets, because the group that
produced most of the atlas's T1/T2 evidence deposited no raw data anywhere public.

That is a weaker provenance and the page says so in those words. It is still worth
building: these are the only published time courses in the near-null-field literature,
and a time course is the one thing a static pathway diagram cannot show.

Driven by a registry so a second paper is a data entry, not a second script. Each entry
names where the file is, how to parse it, and — crucially — what scale its numbers are
on, because a fold-change table fed to a log2 renderer produces a figure that looks
entirely normal and is exactly wrong.

Run:
    PYTHONPATH=src python3 scripts/build_paper_showcase.py --paper Parmagnani2022
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import pathlib
import subprocess
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from qbio import maps, ontology, papers, project, render  # noqa: E402

CACHE = ROOT / "data" / "external" / "papers"
RESULTS = ROOT / "results" / "papers"
DOCS = ROOT / "docs"
EPMC_SUPPL = "https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/supplementaryFiles"


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class PaperSpec:
    paper: papers.Paper
    #: Nested-zip member holding the tables, or None when they sit in the outer zip.
    inner_zip: str | None
    table: str | None
    locus_column: str
    band_row: int
    header_row: int
    tissues: tuple[str, ...]
    #: Map id -> whether a below-threshold coverage is acceptable for that map. A map
    #: listed with True is published WITH its coverage stated, not quietly.
    map_targets: dict[str, bool]
    extra_columns: dict[str, str]
    title: str
    lede: str
    #: "xlsx" reads a banded spreadsheet; "maintext" reads EuropePMC's full-text XML
    #: with a symbol->locus key taken from the paper's own primer table. Not every
    #: paper puts its data in the supplement — Agliassa 2018's supplementary PDFs are
    #: a primer list, a phenology table and ANOVA output, while the gene expression
    #: time course is Tables 1 and 2 of the main text.
    source: str = "xlsx"
    table_captions: tuple[str, ...] = ()
    primer_table: str = ""
    #: Caption key -> a short label for the page. The caption itself is the reliable
    #: selector but a poor column heading.
    tissue_labels: dict[str, str] = dataclasses.field(default_factory=dict)


REGISTRY: dict[str, PaperSpec] = {
    "Parmagnani2022": PaperSpec(
        paper=papers.Paper(
            key="Parmagnani2022",
            citation=(
                "Parmagnani, Mannino & Maffei (2022), Biomolecules 12(12):1824"
            ),
            doi="10.3390/biom12121824",
            pmcid="PMC9775259",
            # Verbatim from the article's Data Availability Statement. Quoted rather
            # than summarised because "they deposited no raw data" is a claim about
            # someone else's work and a reader should be able to check it.
            availability=(
                "Data are available as supplementary tables and further data can be "
                "provided upon request"
            ),
            organism="Arabidopsis thaliana",
            field_regime=(
                "near-null magnetic field (~30 nT) against the local geomagnetic field "
                "(20–60 µT), generated in a triaxial Helmholtz coil system and monitored "
                "with a three-axis magnetometer"
            ),
            comparison="NNMF-grown plants relative to GMF-grown controls",
            scale=papers.RATIO,
            threshold_note=(
                "the authors treat a gene as regulated only outside their own thresholds "
                "of ≥2 and ≤0.5, which this page preserves rather than re-thresholding"
            ),
        ),
        inner_zip="s001.zip",
        table="Table S2.xlsx",
        locus_column="Gene",
        band_row=2,
        header_row=3,
        tissues=("ROOTS", "SHOOTS"),
        map_targets={"QBM-07": False, "QBM-01": True},
        extra_columns={
            "gene_code": "Gene code",
            "gene_function": "Gene function",
            "subcellular": "Subcellular prediction",
        },
        title="A near-null field time course on the ROS map",
        lede=(
            "Seven timepoints from 10 minutes to 96 hours, in roots and shoots, "
            "projected onto the redox map as trajectories rather than snapshots."
        ),
    ),
    "Agliassa2018a": PaperSpec(
        paper=papers.Paper(
            key="Agliassa2018a",
            citation=(
                "Agliassa, Narayana, Bertea, Rodgers & Maffei (2018), "
                "Bioelectromagnetics 39(5):361-374"
            ),
            doi="10.1002/bem.22123",
            pmcid="PMC6032911",
            # Verbatim: this article carries no Data Availability Statement, which is
            # itself the fact worth recording rather than paraphrasing one in.
            availability=(
                "no Data Availability Statement is present in the article; the "
                "quantitative data appear only as main-text tables"
            ),
            organism="Arabidopsis thaliana",
            field_regime=(
                "near-null magnetic field against the local geomagnetic field, in a "
                "triaxial Helmholtz coil system"
            ),
            comparison=(
                "NNMF-grown plants relative to GMF controls at the equivalent timepoint"
            ),
            scale=papers.SIGNED_FOLD,
            threshold_note=(
                "values are signed fold change \u2014 never reported strictly between "
                "-1 and +1 \u2014 so a negative number is a reciprocal, not a log"
            ),
        ),
        inner_zip=None,
        table=None,
        source="maintext",
        table_captions=(
            "Time-Course Expression of Leaf Genes",
            "Time-Course Expression of Floral Meristem Genes",
        ),
        primer_table="SuppTable-S1",
        locus_column="", band_row=0, header_row=0,
        tissues=("leaves", "floral meristem"),
        tissue_labels={
            "time-course expression of leaf genes": "leaves",
            "time-course expression of floral meristem genes": "floral meristem",
        },
        map_targets={"QBM-10": False, "QBM-08": True},
        extra_columns={},
        title="Near-null fields delay flowering, gene by gene",
        lede=(
            "The paper whose title is the review's own claim, put on the flowering "
            "map: a six-point time course through the floral transition."
        ),
    ),
    "Mannino2026": PaperSpec(
        paper=papers.Paper(
            key="Mannino2026",
            citation=(
                "Mannino, Caldo & Maffei (2026), "
                "Journal of Plant Physiology 326:154872"
            ),
            doi="10.1016/j.jplph.2026.154872",
            pmcid="DOI:10.1016/j.jplph.2026.154872",
            availability="Data will be made available on request",
            organism="Ocimum basilicum",
            field_regime=(
                "near-null magnetic field (<40 nT) against the local geomagnetic field "
                "(~44.4 µT), generated in a triaxial Helmholtz coil system and monitored "
                "with a three-axis Bartington Mag-03 magnetometer"
            ),
            comparison="hMF-grown plants relative to GMF controls after 4 weeks exposure",
            scale=papers.LOG2,
            threshold_note=(
                "values are published directly as log2 fold change (hMF/GMF) ± SD from qRT-PCR; "
                "no conversion needed"
            ),
        ),
        inner_zip=None,
        table="gene_expression.tsv",
        source="curated_tsv",
        locus_column="locus",
        band_row=0,
        header_row=0,
        tissues=("leaves",),
        tissue_labels={"leaves": "leaves"},
        map_targets={"QBM-07": False},
        extra_columns={
            "gene_code": "symbol",
            "gene_function": "name",
        },
        title="Hypomagnetic field remodels secondary metabolism and ROS homeostasis in sweet basil",
        lede=(
            "The first aromatic crop under true near-null magnetic field (<40 nT): "
            "showing marked gene-metabolite decoupling in phenylpropanoid biosynthesis, "
            "isoform-divergent SOD regulation, and altered PSII photochemistry."
        ),
    ),
}


# ---------------------------------------------------------------------------
# retrieval
# ---------------------------------------------------------------------------


def fetch_supplementary(pmcid: str) -> pathlib.Path:
    """Download the article's supplementary archive, cached.

    EuropePMC serves these for open-access articles; the paywalled Elsevier titles in
    the same series are not here and are not silently substituted for.
    """
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{pmcid}_suppl.zip"
    if path.exists() and path.stat().st_size > 0:
        return path
    url = EPMC_SUPPL.format(pmcid=pmcid)
    req = urllib.request.Request(url, headers={"User-Agent": "quantum-biology-atlas/0.1"})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = r.read()
    if len(data) < 1024:
        raise papers.PaperError(
            f"{pmcid}: supplementary archive was {len(data)} bytes — too small to be "
            f"real. Refusing to cache it."
        )
    path.write_bytes(data)
    return path


def load_series(spec: PaperSpec) -> tuple[list[papers.Series], dict]:
    import zipfile

    if spec.source == "curated_tsv":
        tsv_path = ROOT / "data" / "external" / "papers" / spec.paper.key / (spec.table or "gene_expression.tsv")
        series, report = papers.read_curated_table(
            tsv_path,
            tissue=spec.tissues[0] if spec.tissues else "leaves",
            timepoint="4w",
            scale=spec.paper.scale,
        )
        report["symbol_key"] = {
            "source": "Supplementary Table S1",
            "pairs": len(series),
            "note": (
                "Gene symbols are resolved from the paper's own primer table "
                "(Supplementary Table S1) to canonical Arabidopsis AGI orthologs."
            ),
        }
        report["loci"] = sorted({s.locus for s in series})
        report.setdefault("rows_no_locus", 0)
        report.setdefault("cells_blank", 0)
        report.setdefault("tissues", {k: v["rows"] for k, v in report["tables"].items()})
        return series, report

    if spec.source == "maintext":
        zf = zipfile.ZipFile(fetch_supplementary(spec.paper.pmcid))
        if spec.inner_zip:
            zf = papers.open_nested_zip(zf, papers.find_member(zf, spec.inner_zip))
        primer = papers.read_primer_map(
            zf.read(papers.find_member(zf, spec.primer_table))
        )
        xml = papers.fetch_fulltext_xml(spec.paper.pmcid, cache_dir=CACHE)
        series, report = papers.read_maintext_timecourse(
            xml, table_captions=spec.table_captions,
            symbol_to_locus=primer, scale=spec.paper.scale,
        )
        report["symbol_key"] = {
            "source": spec.primer_table,
            "pairs": len(primer),
            "note": (
                "Gene symbols are resolved from the paper's own primer table, not from "
                "memory: authoring this ontology turned up five symbol collisions that "
                "would each have put the wrong gene on a map."
            ),
        }
        if spec.tissue_labels:
            series = [
                dataclasses.replace(x, tissue=spec.tissue_labels.get(x.tissue, x.tissue))
                for x in series
            ]
            report["tables"] = {
                spec.tissue_labels.get(k, k): v for k, v in report["tables"].items()
            }
        report["loci"] = sorted({s.locus for s in series})
        report.setdefault("rows_no_locus", len(report["symbols_unresolved"]))
        report.setdefault("cells_blank", report.get("cells_skipped", 0))
        report.setdefault("tissues", {k: v["rows"] for k, v in report["tables"].items()})
        return series, report

    zf = zipfile.ZipFile(fetch_supplementary(spec.paper.pmcid))
    if spec.inner_zip:
        zf = papers.open_nested_zip(zf, papers.find_member(zf, spec.inner_zip))
    data = zf.read(papers.find_member(zf, spec.table))
    return papers.read_banded_timecourse(
        data,
        locus_column=spec.locus_column,
        band_row=spec.band_row,
        header_row=spec.header_row,
        tissues=spec.tissues,
        scale=spec.paper.scale,
        extra_columns=spec.extra_columns,
    )


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------


def build(key: str) -> dict:
    spec = REGISTRY[key]
    onto = ontology.load()
    series, parse_report = load_series(spec)
    index = papers.series_index(series)

    scale_note = (
        "values were published as fold change and converted to log2 for display; the "
        "reported SD is carried through the same transform"
        if spec.paper.scale == papers.RATIO
        else ""
    )

    out_dir = RESULTS / key
    out_dir.mkdir(parents=True, exist_ok=True)
    figures: list[dict] = []

    for map_id, allow_low in spec.map_targets.items():
        src = next((ROOT / "maps" / "src").glob(f"{map_id}_*.yaml"))
        mspec = maps.load_spec(src)
        nodes = [
            (n, onto.get(mspec.nodes.get(n, {}).get("qbo", "")))
            for n in mspec.node_ids
        ]
        for tissue in spec.tissues:
            by_locus = {
                locus: s.to_log2() for (locus, t), s in index.items() if t == tissue
            }
            proj = project.project_series(
                map_id=map_id,
                nodes=nodes,
                series_by_locus=by_locus,
                study=spec.paper.citation.split(" (")[0],
                tissue=tissue,
                organism=spec.paper.organism,
                source_provenance=spec.paper.provenance(),
                scale_note=scale_note,
                allow_low_coverage=allow_low,
            )
            rec = maps.render_series_projection(mspec, onto, proj, out_dir=ROOT / "maps")
            rec["low_coverage_published"] = allow_low
            rec["per_node"] = [
                {
                    "node_id": nid,
                    "qbo": ns.qbo_id,
                    "loci": list(ns.loci_used),
                    "timepoints": list(ns.timepoints),
                    "log2": [None if p is None else round(p, 4) for p in ns.points],
                    "sd": [None if s is None else round(s, 4) for s in ns.sds],
                    "peak": round(ns.extreme(), 4),
                    "peak_timepoint": ns.peak_timepoint(),
                    "reverses_direction": ns.crosses_zero(),
                    "evidence_tier": ns.evidence_tier,
                    "per_locus": {
                        l: [None if v is None else round(v, 4) for v in vals]
                        for l, vals in ns.per_locus.items()
                    },
                    "loci_diverge": ns.loci_diverge,
                }
                for nid, ns in proj.values.items()
            ]
            figures.append(rec)

    qbo_loci = set(onto.index_by_agi())
    covered = sorted(qbo_loci & {locus for locus, _ in index})
    record = {
        "key": key,
        "citation": spec.paper.citation,
        "doi": spec.paper.doi,
        "pmcid": spec.paper.pmcid,
        "provenance_class": "published_results",
        "data_availability_verbatim": spec.paper.availability,
        "organism": spec.paper.organism,
        "field_regime": spec.paper.field_regime,
        "source_table": spec.table,
        "loci_in_table": len(parse_report["loci"]),
        "qbo_loci_covered": covered,
        "cells_parsed": parse_report["cells_parsed"],
        "cells_blank": parse_report["cells_blank"],
        "rows_without_locus": parse_report["rows_no_locus"],
        "tissues": list(spec.tissues),
        "figures": figures,
    }
    if key == "Mannino2026":
        from qbio.decoupling import render_decoupling_svg
        submap_rel = "maps/svg/submap__phenylpropanoid_volatilome__Mannino2026.svg"
        submap_path = ROOT / submap_rel
        render_decoupling_svg(submap_path)
        record["submap_svg"] = submap_rel
        docs_submap = DOCS / submap_rel
        docs_submap.parent.mkdir(parents=True, exist_ok=True)
        docs_submap.write_text(submap_path.read_text(encoding="utf-8"), encoding="utf-8")

    for f in figures:
        svg_src = ROOT / f["svg"]
        svg_dst = DOCS / f["svg"]
        svg_dst.parent.mkdir(parents=True, exist_ok=True)
        if svg_src.exists():
            svg_dst.write_text(svg_src.read_text(encoding="utf-8"), encoding="utf-8")

    (out_dir / "record.json").write_text(json.dumps(record, indent=2))
    docs_rec_dir = DOCS / "results" / "papers" / key
    docs_rec_dir.mkdir(parents=True, exist_ok=True)
    (docs_rec_dir / "record.json").write_text(json.dumps(record, indent=2))
    return record


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--paper", default="Parmagnani2022", choices=sorted(REGISTRY))
    ap.add_argument("--no-png", action="store_true")
    args = ap.parse_args()

    rec = build(args.paper)
    print(f"{rec['key']}: {rec['loci_in_table']} loci, {rec['cells_parsed']} cells, "
          f"{len(rec['qbo_loci_covered'])} QBO loci covered")
    for f in rec["figures"]:
        flag = "  (low coverage, published with it stated)" if f["low_coverage_published"] else ""
        print(f"  {f['id']} {f['tissue']:<7} {f['nodes_with_data']} nodes "
              f"{f['fraction_covered']:.0%}  reversing={len(f['nodes_reversing_direction'])}{flag}")

    if not args.no_png:
        all_svgs = [ROOT / f["svg"] for f in rec["figures"]]
        if "submap_svg" in rec:
            all_svgs.append(ROOT / rec["submap_svg"])
        render_pngs(all_svgs)
    print(f"\nwrote results/papers/{rec['key']}/record.json")
    return 0


def render_pngs(svgs: list[pathlib.Path]) -> None:
    """Rasterise for the page without square-thumbnail bottom cropping."""
    out = DOCS / "maps" / "png"
    out.mkdir(parents=True, exist_ok=True)
    for svg in svgs:
        render.rasterize_svg_full(svg, out / f"{svg.stem}.png", max_dim=1800)


if __name__ == "__main__":
    raise SystemExit(main())
