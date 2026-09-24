#!/usr/bin/env python3
"""
Precompute `catalog/orthologs.json`: every QBO Arabidopsis locus projected onto the
model species, with the method and any method disagreement baked in.

Two consumers need this:

  * `docs/explore.html` — the browser GUI does its join client-side and has no way to
    call Ensembl, so the mapping has to travel with the catalogue.
  * `scripts/build_osd27_showcase.py` — avoids re-querying Ensembl for every rebuild.

The file records, per locus and species, which backbone supplied each ortholog and
whether the two agreed. That matters because the committed OrthoDB matrix is
**human-anchored**: for fly, worm and yeast, Ensembl `pan_homology` is carrying the
projection alone, and a consumer should be able to see that rather than infer
two-method corroboration that never happened.

Unmapped loci are listed explicitly. A locus with no ortholog in a species is a real
finding — the alternative oxidases have no human counterpart because humans do not have
one — and it must not look the same as a locus nobody asked about.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from qbio import ontology, ortho  # noqa: E402

#: The species the review and OSDR_X-species_V2 both care about, plus fly for OSD-27.
TARGETS = {
    "homo_sapiens": "human",
    "mus_musculus": "mouse",
    "drosophila_melanogaster": "fly",
    "caenorhabditis_elegans": "worm",
    "saccharomyces_cerevisiae": "yeast",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=pathlib.Path, default=ROOT / "catalog" / "orthologs.json")
    ap.add_argument(
        "--species", action="append", default=[],
        help="restrict to these Ensembl production names (default: all five)",
    )
    ap.add_argument("--merge", action="store_true",
                    help="keep species already present in the output file")
    args = ap.parse_args()

    onto = ontology.load()
    loci = sorted(onto.index_by_agi())
    targets = {s: TARGETS[s] for s in (args.species or TARGETS)} if args.species else TARGETS
    print(f"{len(loci)} QBO loci -> {len(targets)} species")

    existing = {}
    if args.merge and args.out.exists():
        existing = json.loads(args.out.read_text()).get("species", {})
        print(f"  merging with {len(existing)} species already computed")

    out_species = dict(existing)
    for sp, common in targets.items():
        t0 = time.time()
        try:
            by_locus, cov = ortho.project(loci, sp, allow_empty=True)
        except ortho.OrthologyError as e:
            print(f"  {common:<6} FAILED: {e}", file=sys.stderr)
            continue

        mapping = {}
        for locus, orths in by_locus.items():
            if not orths:
                continue
            methods = sorted({o.method for o in orths})
            mapping[locus] = {
                "targets": sorted({o.target_id for o in orths}),
                "methods": methods,
                "one_to_one": any(o.is_one_to_one for o in orths),
                # Explicit, because a single-method call should not read as corroborated.
                "corroborated": len(methods) > 1,
            }

        out_species[sp] = {
            "common_name": common,
            "mapped": len(mapping),
            "requested": cov.requested,
            "fraction_mapped": round(cov.fraction_mapped, 4),
            "unmapped": list(cov.unmapped),
            "methods_used": list(cov.methods_used),
            "method_disagreements": [
                {"locus": l, "ensembl": list(e), "orthodb": list(o)} for l, e, o in cov.disagreed
            ],
            "orthologs": mapping,
        }
        print(f"  {common:<6} {len(mapping):>3}/{cov.requested} mapped "
              f"({cov.fraction_mapped:.0%}) via {', '.join(cov.methods_used)} "
              f"[{time.time()-t0:.0f}s]")

    doc = {
        "description": (
            "QBO Arabidopsis loci projected onto model species. `methods` names the "
            "backbone(s) that supplied each call; `corroborated` is true only where two "
            "independent methods agreed. The committed OrthoDB matrix is human-anchored, "
            "so for fly, worm and yeast Ensembl pan_homology carries the projection alone."
        ),
        "source_species": "arabidopsis_thaliana",
        "qbo_version": onto.core.version,
        "loci": len(loci),
        "species": out_species,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, indent=2))
    size = args.out.stat().st_size / 1024
    print(f"\nwrote {args.out.relative_to(ROOT)} ({size:.0f} KB, {len(out_species)} species)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
