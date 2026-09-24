#!/usr/bin/env python3
"""
OSD-27: *Drosophila* in a 16.5 T diamagnetic levitation magnet.

This is the page that makes the cross-species machinery do real work. Everything else
in the atlas is *Arabidopsis*; here a plant-anchored quantum ontology is projected onto
the fly, and it lands somewhere worth seeing — AtCRY1 (AT4G08920) maps to *Drosophila*
`cry` (FBgn0025680), the canonical animal magnetoreceptor, in a dataset where flies sat
in a superconducting magnet.

Three things this script refuses to let the page gloss over:

**The field regime is the opposite end of the axis.** ~16.5 T against the ~50 µT
geomagnetic field. The review is about near-null fields. Both are in QBO's
`field_regimes` vocabulary, so the data is in scope, but nothing here may let a reader
treat the two as interchangeable.

**Levitation confounds field with gravity.** Inside the bore, position sets effective
gravity, so most of the study's 420 contrasts change field *and* gravity together.
Only 5 isolate the field, and only those are used.

**Five contrasts are five replications, not five results.** The evidence is whether a
node moves the same way across sexes and exposure durations. A node that moves in one
contrast and not the others is noise wearing the shape of a finding, so the consistency
table is computed and shown rather than left for the reader to assemble.
"""
from __future__ import annotations

import argparse
import csv
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from qbio import maps, ontology, osd27, ortho, project, render  # noqa: E402
from qbio.osdr import ExpressionTable  # noqa: E402

SLICE = ROOT / "data" / "external" / "osd27_field_contrasts.csv"
RESULTS = ROOT / "results" / "osd27"
DOCS = ROOT / "docs"

#: Maps worth overlaying, and whether a below-threshold coverage may still be published
#: (with the number stated). QBM-03 is the cryptochrome map — the reason this study is
#: here at all — so it is shown even if thin.
MAP_TARGETS = {"QBM-01": True, "QBM-03": True, "QBM-07": True}

ALPHA = 0.05


def parse_contrast_label(label: str) -> dict:
    """`(22 day & 1G by magnetic levitator & 19 degree Celsius & Male)v(...)` -> factors."""
    left = label.split(")v(")[0].lstrip("(")
    parts = [p.strip() for p in left.split("&")]
    out = {"duration": parts[0], "temperature": "", "sex": ""}
    for p in parts[1:]:
        if "degree" in p:
            out["temperature"] = p.replace(" degree Celsius", " °C")
        elif p in ("Male", "Female"):
            out["sex"] = p
    return out


def load_slice() -> tuple[list[str], dict[str, ExpressionTable]]:
    """One `ExpressionTable` per field-isolating contrast, from the cached slice."""
    if not SLICE.exists():
        raise SystemExit(
            f"{SLICE.relative_to(ROOT)} not found. Run the OSD-27 slice first — this "
            f"script will not fall back to anything else."
        )
    rows = list(csv.DictReader(SLICE.open()))
    if not rows:
        raise SystemExit(f"{SLICE.name}: no rows")
    labels = [c[len("log2fc__"):] for c in rows[0] if c.startswith("log2fc__")]

    tables: dict[str, ExpressionTable] = {}
    for label in labels:
        values, padj = {}, {}
        for r in rows:
            gid = (r["gene_id"] or "").strip().upper()
            try:
                v = float(r[f"log2fc__{label}"])
            except (TypeError, ValueError):
                continue
            values[gid] = v
            try:
                padj[gid] = float(r[f"padj__{label}"])
            except (TypeError, ValueError):
                pass
        if not values:
            raise SystemExit(f"contrast {label!r} parsed to 0 usable rows")
        tables[label] = ExpressionTable(
            source=f"OSD-27",
            contrast=label,
            gene_column="gene_id",
            values=values,
            padj=padj,
            organism="Drosophila melanogaster",
        )
    return labels, tables


def consistency(per_contrast: dict[str, dict]) -> list[dict]:
    """Per node: how many of the five contrasts move it, and in which direction.

    This is the page's actual evidence. One contrast showing a change is a single
    microarray comparison; the same change in five, across both sexes and three
    exposure durations, is a pattern.
    """
    nodes: dict[str, dict] = {}
    for label, values in per_contrast.items():
        for nid, nv in values.items():
            e = nodes.setdefault(nid, {
                "node_id": nid, "qbo": nv.qbo_id, "evidence_tier": nv.evidence_tier,
                "loci": list(nv.loci_used), "via": list(nv.via_orthologs),
                "by_contrast": {}, "n_up": 0, "n_down": 0, "n_significant": 0,
            })
            e["by_contrast"][label] = {
                "log2fc": round(nv.value, 4), "significant": bool(nv.significant)
            }
            if nv.value > 0:
                e["n_up"] += 1
            elif nv.value < 0:
                e["n_down"] += 1
            if nv.significant:
                e["n_significant"] += 1
    out = []
    for e in nodes.values():
        n = len(e["by_contrast"])
        e["n_contrasts"] = n
        # "Consistent" means every contrast that measured this node agreed on the sign.
        e["consistent_direction"] = (
            "up" if e["n_up"] == n else "down" if e["n_down"] == n else "mixed"
        )
        e["mean_log2fc"] = round(
            sum(c["log2fc"] for c in e["by_contrast"].values()) / n, 4
        )
        # How many DISTINCT fly genes this node's value is an average over. A node
        # standing for 40 genes is not measuring the same kind of thing as one standing
        # for a single gene, and the figure gives no sign of the difference.
        targets = {v.split("\u2192")[1] for v in e["via"] if "\u2192" in v}
        e["n_target_genes"] = len(targets)
        e["target_genes"] = sorted(targets)
        out.append(e)
    return sorted(out, key=lambda e: -abs(e["mean_log2fc"]))


def projection_collapses(consistency_by_map: dict) -> dict:
    """Where the cross-species projection destroyed the map's own distinctions.

    Two failure modes, both invisible on a finished figure and both real here:

      * **Many source nodes onto one target gene.** On QBM-03, CRY1, CRY2 and the
        Trp-triad node all project onto *Drosophila* `cry`. Three nodes then carry the
        identical number and a reader sees agreement between three independent
        measurements that are one measurement drawn three times.
      * **One node onto very many target genes.** AT1G19570 reaches ~40 fly glutathione
        S-transferases; a mean over that set is not a measurement of anything specific.

    Neither is an error in the orthology — both are true statements about how plant and
    fly gene families correspond. They are errors only if left unsaid.
    """
    fanout: list[dict] = []
    collisions: list[dict] = []
    for map_id, cons in consistency_by_map.items():
        # Collisions are counted WITHIN a map. The same node appearing on two maps
        # naturally shares its target genes with itself, and counting that as a collapse
        # would bury the one case that matters in noise.
        shared: dict[str, set[str]] = {}
        for e in cons:
            for g in e.get("target_genes", []):
                shared.setdefault(g, set()).add(e["node_id"])
            if e.get("n_target_genes", 0) >= 10:
                fanout.append({
                    "map": map_id, "node_id": e["node_id"],
                    "n_target_genes": e["n_target_genes"],
                    "loci": e["loci"],
                })
        by_group: dict[tuple, list[str]] = {}
        for g, nodes_ in shared.items():
            if len(nodes_) > 1:
                by_group.setdefault(tuple(sorted(nodes_)), []).append(g)
        for group, genes in by_group.items():
            collisions.append({
                "map": map_id, "nodes": list(group),
                "target_genes": sorted(genes), "n_target_genes": len(genes),
            })
    return {
        "nodes_sharing_a_target_gene": sorted(collisions, key=lambda c: -len(c["nodes"])),
        "nodes_averaging_many_genes": sorted(fanout, key=lambda f: -f["n_target_genes"]),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-png", action="store_true")
    args = ap.parse_args()

    onto = ontology.load()
    labels, tables = load_slice()
    print(f"{len(labels)} field-isolating contrasts, "
          f"{len(next(iter(tables.values())).values):,} genes")

    # ---- orthology, once, reported in full --------------------------------
    loci = sorted(onto.index_by_agi())
    by_locus, cov = ortho.project(loci, "drosophila_melanogaster", allow_empty=True)
    print(f"orthology {cov.mapped}/{cov.requested} ({cov.fraction_mapped:.0%}) "
          f"via {', '.join(cov.methods_used)}")

    figures, coverage_by_map = [], {}
    for map_id, allow_low in MAP_TARGETS.items():
        src = next((ROOT / "maps" / "src").glob(f"{map_id}_*.yaml"))
        spec = maps.load_spec(src)
        nodes = [(n, onto.get(spec.nodes.get(n, {}).get("qbo", ""))) for n in spec.node_ids]

        per_contrast = {}
        for label in labels:
            try:
                proj = project.project_expression(
                    map_id=map_id, nodes=nodes, table=tables[label],
                    target_species="drosophila_melanogaster",
                    alpha=ALPHA, allow_low_coverage=allow_low,
                )
            except project.ProjectionError as e:
                print(f"  {map_id} {label[:34]:<34} skipped: {str(e).splitlines()[0][:70]}")
                continue
            per_contrast[label] = proj.values
            coverage_by_map[map_id] = {
                "nodes_with_data": proj.nodes_with_data,
                "addressable": proj.nodes_total - len(proj.nodes_without_loci),
                "fraction": round(proj.fraction_covered, 4),
                "unmatched": list(proj.nodes_unmatched),
                "without_loci": list(proj.nodes_without_loci),
            }

        if not per_contrast:
            print(f"  {map_id}: no contrast projected — omitted from the page")
            continue

        # Render the FIRST contrast as the map figure, on a scale fixed across all
        # five so the panels are comparable rather than each self-normalised.
        vmax = max(abs(nv.value) for vals in per_contrast.values() for nv in vals.values())
        for label in labels:
            if label not in per_contrast:
                continue
            proj = project.project_expression(
                map_id=map_id, nodes=nodes, table=tables[label],
                target_species="drosophila_melanogaster",
                alpha=ALPHA, allow_low_coverage=allow_low,
            )
            f = parse_contrast_label(label)
            rec = maps.render_projection(spec, onto, proj, vmax=vmax)
            rec["factors"] = f
            rec["contrast_label"] = label
            rec["low_coverage_published"] = allow_low and proj.fraction_covered < 0.25
            figures.append(rec)
            break                       # one map panel per map; the rest is the table

        cons = consistency(per_contrast)
        coverage_by_map[map_id]["consistency"] = cons
        agree = sum(1 for c in cons if c["consistent_direction"] != "mixed")
        print(f"  {map_id}: {len(cons)} nodes, {agree} consistent across "
              f"{len(per_contrast)} contrasts, vmax={vmax:.2f}")

    record = {
        "accession": "OSD-27",
        "title": ("Transcription profiling of Drosophila exposed to a levitation magnet "
                  "for different lengths of time"),
        "publication_doi": osd27.PUBLICATION_DOI,
        "provenance_class": "genelab_processed",
        "organism": "Drosophila melanogaster",
        "field_tesla_nominal": osd27.FIELD_TESLA_NOMINAL,
        "field_regime": "strong static field",
        "source_species": "arabidopsis_thaliana",
        "target_species": "drosophila_melanogaster",
        "contrasts": [
            dict(label=l, **parse_contrast_label(l)) for l in labels
        ],
        "orthology": {
            "mapped": cov.mapped, "requested": cov.requested,
            "fraction": round(cov.fraction_mapped, 4),
            "methods_used": list(cov.methods_used),
            "disagreements": len(cov.disagreed),
            "unmapped": list(cov.unmapped),
            "one_to_one": cov.one_to_one,
        },
        "cry1": {
            "arabidopsis": "AT4G08920",
            "drosophila": [o.target_id for o in by_locus.get("AT4G08920", [])],
        },
        "alpha": ALPHA,
        "maps": coverage_by_map,
        "projection_collapses": projection_collapses(
            {m: c["consistency"] for m, c in coverage_by_map.items() if "consistency" in c}
        ),
        "figures": figures,
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "record.json").write_text(json.dumps(record, indent=2))

    if not args.no_png:
        out = DOCS / "maps" / "png"
        out.mkdir(parents=True, exist_ok=True)
        for f in figures:
            svg = ROOT / f["svg"]
            subprocess.run(["qlmanage", "-t", "-s", "1400", "-o", str(out), str(svg)],
                           capture_output=True)
            produced = out / (svg.name + ".png")
            if produced.exists():
                produced.rename(out / (svg.stem + ".png"))

    print(f"\nwrote results/osd27/record.json ({len(figures)} figures)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
