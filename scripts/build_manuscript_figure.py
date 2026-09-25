#!/usr/bin/env python3
"""
Assemble `manuscript/figures/figure1.pdf` from generated artefacts.

Every panel is a file this repository produced, converted and placed --- nothing is
drawn for the figure. That is the rule the figures this atlas replaces broke: six panels
of bar charts whose "data" was a hand-written direction list and a set of literal
`1.0 vs 1.0 +/- 0.4` values.

Panel B is the one exception in kind, since a tier histogram has no existing rendering.
It is computed here from `catalog/manifest.json` at build time, not typed.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "manuscript" / "figures"

#: (panel letter, source path, what it is). Sources are checked to exist; a missing one
#: fails the build rather than producing a figure with a hole in it.
PANELS = [
    ("A", "maps/svg/QBM-01.svg", "the map with the evidence-tier border channel"),
    ("C", "maps/svg/QBM-07__Parmagnani-Mannino-Maffei__ROOTS.svg",
     "a near-null time course with sparklines"),
    ("D", "maps/svg/QBM-01__OSD-782-1-Gy__1-Gy.svg",
     "per-locus heatmaps on multi-locus nodes"),
]

OKABE = {"T1": "#000000", "T2": "#0072B2", "T3": "#D55E00", "T4": "#999999"}


def tier_panel(path: pathlib.Path) -> None:
    """Panel B: the tier distribution, computed from the catalogue."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    totals = json.loads((ROOT / "catalog" / "manifest.json").read_text())["totals"]
    tiers = totals["nodes_by_tier"]
    order = ["T1", "T2", "T3", "T4"]
    labels = {
        "T1": "T1\ndemonstrated", "T2": "T2\ninferred",
        "T3": "T3\nplausible", "T4": "T4\ncontext",
    }
    counts = [tiers.get(t, 0) for t in order]

    fig, ax = plt.subplots(figsize=(4.2, 2.6))
    bars = ax.bar(order, counts, color=[OKABE[t] for t in order], width=0.62)
    for b, c in zip(bars, counts):
        ax.text(b.get_x() + b.get_width() / 2, c + 0.8, str(c),
                ha="center", va="bottom", fontsize=9, fontweight="bold")
    ax.set_xticks(range(len(order)))
    ax.set_xticklabels([labels[t] for t in order], fontsize=8)
    ax.set_ylabel(f"nodes (of {totals['nodes']})", fontsize=9)
    ax.set_ylim(0, max(counts) * 1.22)
    ax.spines[["top", "right"]].set_visible(False)
    ax.tick_params(labelsize=8)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    print(f"  B  tier distribution {dict(zip(order, counts))}")


def svg_to_pdf(src: pathlib.Path, dst: pathlib.Path) -> bool:
    """Rasterise via qlmanage. No rsvg/cairosvg/inkscape on this machine.

    Forces the LIGHT theme first. The maps follow `prefers-color-scheme`, and the
    renderer picks up the machine's appearance — which produced a figure with three
    dark panels beside one light one. The maps already guard their dark rule with
    `:root:not([data-theme="light"])`, so setting that attribute on the root uses the
    mechanism that is already there rather than stripping the stylesheet.
    """
    text = src.read_text(encoding="utf-8")
    if 'data-theme=' not in text.split(">", 1)[0]:
        text = text.replace("<svg ", '<svg data-theme="light" ', 1)
    light = dst.parent / f"_light_{src.name}"
    light.write_text(text, encoding="utf-8")

    tmp = dst.parent / (light.name + ".png")
    subprocess.run(["qlmanage", "-t", "-s", "2000", "-o", str(dst.parent), str(light)],
                   capture_output=True)
    light.unlink(missing_ok=True)
    if not tmp.exists():
        return False
    tmp.rename(dst.with_suffix(".png"))
    return True


def main() -> int:
    argparse.ArgumentParser().parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    missing = [p for _, p, _ in PANELS if not (ROOT / p).exists()]
    if missing:
        raise SystemExit(
            f"panel source(s) missing: {missing}. Build the maps before the figure — a "
            f"figure assembled around a hole is worse than no figure."
        )

    print("panels:")
    for letter, rel, what in PANELS:
        src = ROOT / rel
        if svg_to_pdf(src, OUT / f"panel{letter}"):
            print(f"  {letter}  {what}  <- {rel}")
        else:
            raise SystemExit(f"could not rasterise {rel}")

    tier_panel(OUT / "panelB.pdf")

    # There is deliberately no browser-tool panel. It would have to be a screenshot of
    # a live interactive page, and this script can only place artefacts the repository
    # generated. Mocking one up in a drawing program is exactly the practice the figure
    # this atlas replaces was guilty of, so the tool is described in the text and linked
    # instead of illustrated.

    print(f"\npanel files in {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
