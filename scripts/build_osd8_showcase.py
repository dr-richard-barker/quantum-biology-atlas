#!/usr/bin/env python3
"""
OSD-8: the cleanest field-isolating contrast in the atlas, and a specificity test.

The study declares `Magnetic Field` and `Altered Gravity` as separate factors and carries
gravity controls that use no magnet — a random-positioning machine for µg, a centrifuge
for 2g. One group holds gravity fixed and changes only the field:

    MAG 1g*  —  1g inside the magnet (16.5 T) vs 1g outside it (0 T)

In *Arabidopsis*, so no orthology is needed, and the platform join reaches all 125 atlas
loci. That combination is unique here, and it lets this page ask something the others
cannot.

**The specificity test.** Every other overlay in this atlas shows how far the QBO nodes
moved, with nothing to compare that against. With 29,327 loci on the array, the right
question is whether the nodes this ontology selected respond *more than loci chosen at
random*. If they do not, a coloured map is showing array noise arranged in a
biologically suggestive shape — which is exactly the failure this atlas exists to avoid.
So the test is run, and its answer is reported whichever way it comes out.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import random
import statistics
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from qbio import compare, maps, ontology, osd8, project  # noqa: E402
from qbio.osdr import ExpressionTable  # noqa: E402

PLATFORM_FILE = ROOT / "data" / "external" / "GPL9020.txt"
SAMPLE_DIR = ROOT / "data" / "external" / "osd8"
RESULTS = ROOT / "results" / "osd8"
DOCS = ROOT / "docs"

#: Maps to render. The field contrast reaches every map at full coverage, so the
#: selection is about what is worth showing, not what is possible.
MAP_TARGETS = ("QBM-01", "QBM-03", "QBM-07", "QBM-09")

#: Permutation count for the specificity test. 10,000 gives a resolution of 1e-4 on the
#: p-value, which is finer than any claim made from it.
N_PERMUTATIONS = 10_000
SEED = 20260924


def specificity_test(values, qbo_loci, *, n=N_PERMUTATIONS, seed=SEED):
    """Delegates to `qbio.compare.specificity_test`.

    Moved out of this script so the OSD-782 radiation page reports a number produced by
    the same function with the same seed and permutation count. Two differently-computed
    numbers are not a comparison, and the radiation page exists to compare.
    """
    return compare.specificity_test(
        values, qbo_loci, permutations=n, seed=seed
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-png", action="store_true")
    args = ap.parse_args()

    if not PLATFORM_FILE.exists():
        raise SystemExit(f"{PLATFORM_FILE} missing — fetch GPL9020 first")

    onto = ontology.load()
    by_locus, platform_report = osd8.parse_platform(PLATFORM_FILE)
    print(f"platform {platform_report['probes']:,} probes -> "
          f"{platform_report['distinct_loci']:,} loci "
          f"({platform_report['probes_without_agi']:,} probes carry no AGI)")

    groups, group_reports = {}, {}
    for g in osd8.GROUPS:
        v, rep = osd8.group_values(g, SAMPLE_DIR, by_locus)
        groups[g.key] = v
        group_reports[g.key] = rep
        kind = ("FIELD-ISOLATING" if g.isolates_field
                else "gravity only" if g.isolates_gravity else "field+gravity")
        print(f"  {g.key:<10} n={rep['n_arrays']}  {len(v):,} loci  [{kind}]")

    field_groups = osd8.field_isolating_groups()
    if len(field_groups) != 1:
        raise SystemExit(
            f"expected exactly one field-isolating group, found "
            f"{[g.key for g in field_groups]} — the page's central claim depends on it"
        )
    primary = field_groups[0]

    # ---- specificity ------------------------------------------------------
    qbo_loci = set(onto.index_by_agi())
    spec = {k: specificity_test(v, qbo_loci) for k, v in groups.items()}
    s = spec[primary.key]
    print(f"\nspecificity ({primary.key}): QBO mean|log2FC| {s['observed_mean_abs_log2fc']:.4f} "
          f"vs background {s['background_mean']:.4f} (p={s['p_value']:.4f})")

    # ---- projections ------------------------------------------------------
    figures, per_map = [], {}
    for map_id in MAP_TARGETS:
        src = next((ROOT / "maps" / "src").glob(f"{map_id}_*.yaml"))
        spec_map = maps.load_spec(src)
        nodes = [(n, onto.get(spec_map.nodes.get(n, {}).get("qbo", "")))
                 for n in spec_map.node_ids]

        by_group = {}
        for key, vals in groups.items():
            table = ExpressionTable(
                source="OSD-8", contrast=key, gene_column="agi_locus",
                values={g.upper(): v for g, v in vals.items()},
                organism="Arabidopsis thaliana",
            )
            # alpha=None: these are normalized ratios with no model fitted, so there is
            # no adjusted p-value and none is invented.
            proj = project.project_expression(
                map_id=map_id, nodes=nodes, table=table, alpha=None
            )
            by_group[key] = proj

        # One colour scale across every group so the panels are comparable.
        vmax = max(abs(nv.value) for p in by_group.values() for nv in p.values.values())
        rec = maps.render_projection(spec_map, onto, by_group[primary.key], vmax=vmax)
        rec["group"] = primary.key
        rec["group_label"] = primary.label
        figures.append(rec)

        per_map[map_id] = {
            "nodes_with_data": by_group[primary.key].nodes_with_data,
            "addressable": (by_group[primary.key].nodes_total
                            - len(by_group[primary.key].nodes_without_loci)),
            "fraction": round(by_group[primary.key].fraction_covered, 4),
            "vmax": round(vmax, 4),
            "nodes": sorted(
                (
                    {
                        "node_id": nid,
                        "qbo": nv.qbo_id,
                        "evidence_tier": nv.evidence_tier,
                        "loci": list(nv.loci_used),
                        "by_group": {
                            k: round(p.values[nid].value, 4)
                            for k, p in by_group.items() if nid in p.values
                        },
                    }
                    for nid, nv in by_group[primary.key].values.items()
                ),
                key=lambda d: -abs(d["by_group"].get(primary.key, 0.0)),
            ),
        }
        print(f"  {map_id}: {per_map[map_id]['nodes_with_data']}/"
              f"{per_map[map_id]['addressable']} nodes, vmax={vmax:.3f}")

    record = {
        "accession": "OSD-8",
        "title": ("Gravitational and magnetic field variations synergize to cause subtle "
                  "variations in the global transcriptional state of Arabidopsis in "
                  "vitro callus cultures"),
        "publication_doi": osd8.PUBLICATION_DOI,
        "geo_series": osd8.GEO_SERIES,
        "platform": osd8.PLATFORM,
        "provenance_class": "depositor_normalised",
        "organism": "Arabidopsis thaliana",
        "value_definition": osd8.VALUE_DEFINITION,
        "field_regime": "strong static field",
        "primary_group": primary.key,
        "groups": [
            {
                "key": g.key, "label": g.label, "test": g.test, "reference": g.reference,
                "n_arrays": group_reports[g.key]["n_arrays"],
                "arrays": list(g.samples),
                "field_tesla": g.field_tesla,
                "reference_field_tesla": g.reference_field_tesla,
                "gravity": g.gravity, "reference_gravity": g.reference_gravity,
                "isolates_field": g.isolates_field,
                "isolates_gravity": g.isolates_gravity,
                "loci_with_values": group_reports[g.key]["loci_with_values"],
            }
            for g in osd8.GROUPS
        ],
        "platform_join": platform_report,
        "specificity": spec,
        "maps": per_map,
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

    print(f"\nwrote results/osd8/record.json ({len(figures)} figures)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
