#!/usr/bin/env python3
"""
OSD-782: ionising radiation as a dose × time course on the quantum maps.

Two doses, four timepoints, *Arabidopsis*, GeneLab-processed differential expression
with real adjusted p-values. The radiation response is projected onto the maps as
trajectories using the same `project_series` machinery built for Parmagnani 2022.

**This is not a magnetic-field study and the page does not treat it as one.** It is here
because radiolysis makes radicals and ROS directly, so the question worth asking is
whether the nodes radiation moves are the nodes magnetic-field perturbation moves.
That overlap is computed separately by `build_overlap.py`; this script produces the
radiation side of it.

The specificity test is imported from `qbio.compare`, the same function the OSD-8 page
uses, with the same seed and permutation count — otherwise the two numbers could not be
placed side by side.
"""
from __future__ import annotations

import argparse
import csv
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from qbio import compare, maps, ontology, osd27, osd782, project  # noqa: E402
from qbio.papers import LOG2, Measurement, Series  # noqa: E402

SLICE = ROOT / "data" / "external" / "osd782_dose_contrasts.csv"
CONTRASTS = ROOT / "data" / "external" / "osd782_contrasts.csv"
RESULTS = ROOT / "results" / "osd782"
DOCS = ROOT / "docs"

#: Chosen by mechanism, not by what lights up: radiolysis makes ROS (QBM-07), the ETC is
#: the endogenous ROS source (QBM-01), and Fe-S clusters are radiation-labile (QBM-04).
MAP_TARGETS = ("QBM-07", "QBM-01", "QBM-04")

ALPHA = 0.05


def fetch_contrasts() -> list:
    if not CONTRASTS.exists():
        import urllib.request

        f = osd782.find_contrasts_file()
        CONTRASTS.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(
            f.url, headers={"User-Agent": "quantum-biology-atlas/0.1"}
        )
        with urllib.request.urlopen(req, timeout=120) as r:
            CONTRASTS.write_bytes(r.read())
        print(f"  fetched {f.file_name}")
    return osd27.parse_contrasts(CONTRASTS.read_text())


def ensure_slice(points) -> dict:
    """Stream-slice the ~255 MB DE table down to the 8 dose contrasts."""
    if SLICE.exists() and SLICE.stat().st_size > 0:
        print(f"  using cached slice {SLICE.name} "
              f"({SLICE.stat().st_size / 1024:.0f} KB)")
        return {"cached": True, "output": str(SLICE.relative_to(ROOT))}
    de = osd782.find_de_file()
    print(f"  streaming {de.file_name} ({de.size_bytes / 1e6:.0f} MB) …")
    return osd27.slice_contrasts(de, [p.contrast for p in points], SLICE)


def load_slice(points) -> dict[str, dict[str, dict]]:
    """contrast label -> {locus: {'log2fc': x, 'padj': y}}."""
    rows = list(csv.DictReader(SLICE.open()))
    if not rows:
        raise SystemExit(f"{SLICE.name}: no rows")
    out: dict[str, dict[str, dict]] = {}
    for p in points:
        label = p.contrast.label
        vals = {}
        for r in rows:
            gid = (r["gene_id"] or "").strip().upper()
            if not gid:
                continue
            try:
                v = float(r[f"log2fc__{label}"])
            except (TypeError, ValueError, KeyError):
                continue
            try:
                q = float(r[f"padj__{label}"])
            except (TypeError, ValueError, KeyError):
                q = None
            vals[gid] = {"log2fc": v, "padj": q}
        if not vals:
            raise SystemExit(f"contrast {label!r} parsed to 0 usable rows")
        out[label] = vals
    return out


def build_series(points, sliced) -> dict[str, Series]:
    """One `Series` per locus, already on a log2 scale — GeneLab reports log2 directly.

    No `to_log2` conversion here, and that is not an oversight: unlike the published
    supplementary tables, a GeneLab DE table is already log2 fold change. Converting
    again would take the log of a log.
    """
    timepoints = tuple(p.time_label for p in points)
    loci = set.intersection(*(set(sliced[p.contrast.label]) for p in points))
    out = {}
    for locus in loci:
        pts = []
        for p in points:
            cell = sliced[p.contrast.label].get(locus)
            pts.append(None if cell is None
                       else Measurement(cell["log2fc"], 0.0, LOG2))
        out[locus] = Series(
            locus=locus, tissue=f"{points[0].dose_gy:g} Gy",
            timepoints=timepoints, points=tuple(pts),
        )
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-png", action="store_true")
    args = ap.parse_args()

    onto = ontology.load()
    contrasts = fetch_contrasts()
    print(f"{len(contrasts)} contrasts in the study")

    points = osd782.dose_points(contrasts)
    series_by_dose = osd782.dose_series(contrasts)
    print(f"  {len(points)} dose-isolating, {len(series_by_dose)} doses × "
          f"{len(next(iter(series_by_dose.values())))} timepoints")
    for c in points:
        if c.contrast.is_single_factor:
            raise SystemExit(
                "a dose contrast differs in one factor only, which contradicts this "
                "study's design — dose and radiation source are coupled"
            )

    slice_report = ensure_slice(points)
    sliced = load_slice(points)
    print(f"  {len(next(iter(sliced.values()))):,} loci in the slice")

    qbo_loci = set(onto.index_by_agi())
    spec, figures, per_map, series_records = {}, [], {}, {}

    for dose, pts in sorted(series_by_dose.items()):
        label = f"{dose:g} Gy"
        series = build_series(pts, sliced)
        series_records[label] = series

        # Specificity, per timepoint, from the SAME function the OSD-8 page uses.
        spec[label] = {}
        for p in pts:
            vals = {g: c["log2fc"] for g, c in sliced[p.contrast.label].items()}
            spec[label][p.time_label] = compare.specificity_test(vals, qbo_loci)
        best = min(spec[label].items(), key=lambda kv: kv[1]["p_value"])
        print(f"  {label}: best specificity p={best[1]['p_value']:.4f} at {best[0]} "
              f"(QBO {best[1]['observed_mean_abs_log2fc']:.4f} vs "
              f"{best[1]['background_mean']:.4f})")

        for map_id in MAP_TARGETS:
            src = next((ROOT / "maps" / "src").glob(f"{map_id}_*.yaml"))
            spec_map = maps.load_spec(src)
            nodes = [(n, onto.get(spec_map.nodes.get(n, {}).get("qbo", "")))
                     for n in spec_map.node_ids]
            proj = project.project_series(
                map_id=map_id, nodes=nodes, series_by_locus=series,
                study=f"OSD-782 — {label}", tissue=label,
                organism="Arabidopsis thaliana",
                source_provenance=(
                    f"NASA OSDR OSD-782 / {osd782.GLDS}, GeneLab-processed differential "
                    f"expression. {osd782.PERTURBATION['source']} at {label} against "
                    f"non-irradiated controls at matched time"
                ),
                scale_note="GeneLab reports log2 fold change directly; no conversion applied",
            )
            rec = maps.render_series_projection(spec_map, onto, proj, out_dir=ROOT / "maps")
            rec["dose_gy"] = dose
            rec["per_node"] = [
                {
                    "node_id": nid, "qbo": ns.qbo_id, "loci": list(ns.loci_used),
                    "timepoints": list(ns.timepoints),
                    "log2": [None if v is None else round(v, 4) for v in ns.points],
                    "peak": round(ns.extreme(), 4),
                    "peak_timepoint": ns.peak_timepoint(),
                    "reverses_direction": ns.crosses_zero(),
                    "loci_diverge": ns.loci_diverge,
                    "diverging_timepoints": ns.n_diverging_timepoints,
                    "evidence_tier": ns.evidence_tier,
                }
                for nid, ns in proj.values.items()
            ]
            figures.append(rec)
            per_map.setdefault(map_id, {})[label] = {
                "nodes_with_data": proj.nodes_with_data,
                "addressable": proj.nodes_total - len(proj.nodes_without_loci),
                "fraction": round(proj.fraction_covered, 4),
            }

    record = {
        "accession": "OSD-782",
        "glds": osd782.GLDS,
        "title": osd782.TITLE,
        "provenance_class": "genelab_processed",
        "organism": "Arabidopsis thaliana",
        "perturbation": osd782.PERTURBATION,
        "factors": ["Ionizing Radiation", "Absorbed Radiation Dose",
                    "Time of Sample Collection After Treatment"],
        "timepoints": [p.time_label for p in series_by_dose[min(series_by_dose)]],
        "doses_gy": sorted(series_by_dose),
        "contrasts": [
            {"label": p.contrast.label, "dose_gy": p.dose_gy,
             "time": p.time_label, "hours": p.hours,
             "is_single_factor": p.contrast.is_single_factor}
            for p in points
        ],
        "alpha": ALPHA,
        "slice": slice_report,
        "qbo_loci_measured": len(qbo_loci & set(next(iter(series_records.values())))),
        "specificity": spec,
        "maps": per_map,
        "figures": figures,
        "related_work": (
            "OSD-782 is the held-out validation set of the Plant Ionizing-Radiation "
            "Kinetic Landscape pipeline (Barker 2026), so this projection does not "
            "duplicate that analysis."
        ),
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "record.json").write_text(json.dumps(record, indent=2))

    # Per-locus series, for build_overlap.py. Kept out of record.json, which is served.
    (RESULTS / "series.json").write_text(json.dumps({
        dose: {
            locus: {
                "timepoints": list(s.timepoints),
                "log2": [None if p is None else round(p.value, 5) for p in s.points],
            }
            for locus, s in series.items() if locus in qbo_loci
        }
        for dose, series in series_records.items()
    }, indent=2))

    if not args.no_png:
        from qbio import render
        out = DOCS / "maps" / "png"
        out.mkdir(parents=True, exist_ok=True)
        for f in figures:
            svg = ROOT / f["svg"]
            render.rasterize_svg_full(svg, out / f"{svg.stem}.png", max_dim=1800)

    print(f"\nwrote results/osd782/record.json ({len(figures)} figures)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
