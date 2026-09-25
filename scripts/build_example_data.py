#!/usr/bin/env python3
"""
Generate the example table shipped with `docs/explore.html`.

A demo file is published content, so it obeys the same rule as every other number on
this site: it has to come from a script, not from a hand-edited spreadsheet. This one
regenerates byte-identically from the OSD-8 source, so a reader can check that the
example is real data rather than something shaped to look good.

**It is real, and deliberately not flattering.** The values are the OSD-8
field-isolating contrast — 1g inside a 16.5 T magnet against 1g outside it — which is
the same contrast whose permutation test found the atlas's loci respond no more than
random loci. A demo dataset chosen to make the tool look impressive would be the exact
failure this repository exists to avoid.

The background loci are sampled with a fixed seed so coverage is not artificially 100%:
a file containing only atlas loci would make every map look fully covered and would
teach a user nothing about what partial coverage looks like.
"""
from __future__ import annotations

import argparse
import csv
import pathlib
import random
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from qbio import ontology, osd8  # noqa: E402

PLATFORM = ROOT / "data" / "external" / "GPL9020.txt"
SAMPLES = ROOT / "data" / "external" / "osd8"
OUT = ROOT / "docs" / "example-data" / "OSD-8_MAG-1g_field-contrast.csv"

#: Background loci to include alongside the atlas's own, so the example shows realistic
#: partial coverage rather than a map where everything happens to be filled.
N_BACKGROUND = 2000
SEED = 7


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=pathlib.Path, default=OUT)
    args = ap.parse_args()

    if not PLATFORM.exists():
        raise SystemExit(f"{PLATFORM} missing — fetch GPL9020 first")

    by_locus, _ = osd8.parse_platform(PLATFORM)
    group = next(g for g in osd8.GROUPS if g.isolates_field)
    values, report = osd8.group_values(group, SAMPLES, by_locus)

    qbo = set(ontology.load().index_by_agi())
    rng = random.Random(SEED)
    background = rng.sample(sorted(set(values) - qbo), N_BACKGROUND)
    loci = sorted(qbo | set(background))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["locus", "log2FoldChange"])
        for locus in loci:
            w.writerow([locus, f"{values[locus]:.5f}"])

    print(f"wrote {args.out.relative_to(ROOT)}")
    print(f"  group     : {group.key} ({group.label})")
    print(f"  arrays    : {report['n_arrays']} — {', '.join(group.samples)}")
    print(f"  loci      : {len(loci):,} "
          f"({len(qbo & set(loci))} atlas + {len(background):,} background, seed {SEED})")
    print(f"  size      : {args.out.stat().st_size / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
