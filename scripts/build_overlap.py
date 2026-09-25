#!/usr/bin/env python3
"""
Where do ionising radiation and magnetic-field perturbation move the same things?

This is the question the radiation page exists to answer. Radiation is *not* a magnetic
field regime and nothing here says it is. But radiolysis makes radicals and ROS directly,
and the magnetic-field literature converges on the same redox machinery — so a node that
moves under both is a lead worth following, and a node that moves under only one marks
where the two stories separate.

Three perturbations, all *Arabidopsis*, all already in the atlas:

    radiation   OSD-782, cesium-137 gamma, 0.1 and 1.0 Gy, 1-72 h   (GeneLab DE)
    strong_MF   OSD-8 MAG 1g*, 16.5 T vs 0 T at matched 1g          (depositor ratios)
    NNMF        Parmagnani 2022, ~30 nT vs GMF, 10 min - 96 h       (published results)

**Two arms, because only one of them can carry a statistic.** The radiation × strong-field
comparison shares 123 loci and is permutation-tested. The NNMF arm shares **six nodes**,
because Parmagnani's supplementary table was filtered by its authors to oxidative-reaction
enzymes — six rows is a table to read, not a statistic, and `compare.overlap_exceeds_chance`
refuses it rather than returning a p-value that would look like evidence.

Direction, not magnitude. A microarray ratio from one lab and an RNA-seq fold change from
another are not comparable in size; agreeing on sign is a real comparison.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from qbio import compare, ontology, osd8  # noqa: E402

RESULTS = ROOT / "results" / "overlap"
RAD = ROOT / "results" / "osd782"
MF8 = ROOT / "results" / "osd8" / "record.json"
NNMF = ROOT / "results" / "papers" / "Parmagnani2022" / "record.json"

PLATFORM = ROOT / "data" / "external" / "GPL9020.txt"
SAMPLES = ROOT / "data" / "external" / "osd8"

#: Timepoints the radiation and NNMF courses genuinely share. Comparing 1 h to 10 min
#: would be a different experiment silently relabelled.
SHARED_TIMES = {"1 hour": "1 h", "24 hour": "24 h"}


def radiation_node_responses(rec: dict) -> dict[str, compare.Response]:
    """Per node, the most extreme response across both doses and all timepoints."""
    best: dict[str, tuple[float, str]] = {}
    for fig in rec["figures"]:
        for n in fig["per_node"]:
            v = n["peak"]
            cur = best.get(n["node_id"])
            if cur is None or abs(v) > abs(cur[0]):
                best[n["node_id"]] = (v, f"{fig['dose_gy']:g} Gy, {n['peak_timepoint']}")
    return {
        nid: compare.Response(
            key=nid, perturbation="radiation", value=v,
            responded=compare.responds(v)[0], at=at,
        )
        for nid, (v, at) in best.items()
    }


def strong_field_node_responses(rec: dict) -> dict[str, compare.Response]:
    primary = rec["primary_group"]
    out = {}
    for m in rec["maps"].values():
        for n in m["nodes"]:
            v = n["by_group"].get(primary)
            if v is None:
                continue
            out[n["node_id"]] = compare.Response(
                key=n["node_id"], perturbation="strong_MF", value=v,
                responded=compare.responds(v)[0], at="16.5 T vs 0 T",
            )
    return out


def nnmf_node_responses(rec: dict) -> dict[str, compare.Response]:
    """Parmagnani 2022, most extreme across tissues and timepoints."""
    best: dict[str, tuple[float, str]] = {}
    for fig in rec["figures"]:
        for n in fig["per_node"]:
            v = n["peak"]
            cur = best.get(n["node_id"])
            if cur is None or abs(v) > abs(cur[0]):
                best[n["node_id"]] = (v, f"{fig['tissue'].lower()}, {n['peak_timepoint']}")
    return {
        nid: compare.Response(
            key=nid, perturbation="NNMF", value=v,
            responded=compare.responds(v)[0], at=at,
        )
        for nid, (v, at) in best.items()
    }


def locus_arm() -> dict:
    """Radiation × strong field over the shared QBO loci — the arm that can be tested."""
    series = json.loads((RAD / "series.json").read_text())
    rad_extreme: dict[str, float] = {}
    for dose, by_locus in series.items():
        for locus, s in by_locus.items():
            obs = [v for v in s["log2"] if v is not None]
            if not obs:
                continue
            v = max(obs, key=abs)
            if locus not in rad_extreme or abs(v) > abs(rad_extreme[locus]):
                rad_extreme[locus] = v

    by_locus_platform, _ = osd8.parse_platform(PLATFORM)
    group = next(g for g in osd8.GROUPS if g.isolates_field)
    mf_values, _ = osd8.group_values(group, SAMPLES, by_locus_platform)

    qbo = set(ontology.load().index_by_agi())
    rad = compare.responses(
        {g: v for g, v in rad_extreme.items() if g in qbo}, "radiation")
    mf = compare.responses(
        {g: v for g, v in mf_values.items() if g in qbo}, "strong_MF")

    rows = compare.overlap({"radiation": rad, "strong_MF": mf})
    summary = compare.summarise(rows)
    try:
        chance = compare.overlap_exceeds_chance(rows, ["radiation", "strong_MF"])
        chance["tested"] = True
    except compare.ComparisonError as e:
        chance = {"tested": False, "reason": str(e)}
    return {
        "unit": "locus",
        "perturbations": ["radiation", "strong_MF"],
        "summary": summary,
        "chance": chance,
        "rows": [
            {
                "locus": r.key,
                "radiation": round(r.by_perturbation["radiation"].value, 4),
                "strong_MF": round(r.by_perturbation["strong_MF"].value, 4),
                "responded_in": r.responded_in,
                "directions_agree": r.directions_agree(),
            }
            for r in rows if r.is_shared
        ],
    }


def node_arm() -> dict:
    """All three perturbations, node level. Six nodes — a table, not a statistic."""
    rad = radiation_node_responses(json.loads((RAD / "record.json").read_text()))
    mf = strong_field_node_responses(json.loads(MF8.read_text()))
    nn = nnmf_node_responses(json.loads(NNMF.read_text()))

    rows = compare.overlap({"radiation": rad, "strong_MF": mf, "NNMF": nn})
    summary = compare.summarise(rows)
    try:
        chance = compare.overlap_exceeds_chance(rows, ["radiation", "NNMF"])
        chance["tested"] = True
    except compare.ComparisonError as e:
        # Expected, and the reason is published rather than the test quietly skipped.
        chance = {"tested": False, "reason": str(e)}
    return {
        "unit": "node",
        "perturbations": ["radiation", "strong_MF", "NNMF"],
        "summary": summary,
        "chance": chance,
        "rows": [
            {
                "node_id": r.key,
                "responded_in": r.responded_in,
                "directions_agree": r.directions_agree(),
                "verdict": r.verdict("radiation"),
                "by_perturbation": {
                    p: {"value": round(v.value, 4), "responded": v.responded, "at": v.at}
                    for p, v in r.by_perturbation.items()
                },
            }
            for r in rows
        ],
    }


def nnmf_locus_responses() -> dict[str, compare.Response]:
    """Parmagnani 2022 at locus level, most extreme across tissues and timepoints."""
    import zipfile

    from qbio import papers

    src = ROOT / "data" / "external" / "papers" / "PMC9775259_suppl.zip"
    zf = papers.open_nested_zip(zipfile.ZipFile(src), "biomolecules-12-01824-s001.zip")
    series, _ = papers.read_banded_timecourse(
        zf.read(papers.find_member(zf, "Table S2.xlsx")),
        locus_column="Gene", band_row=2, header_row=3,
        tissues=("ROOTS", "SHOOTS"), scale=papers.RATIO,
    )
    best: dict[str, tuple[float, str]] = {}
    for s in series:
        log2 = s.to_log2()
        v = log2.extreme()
        if v is None:
            continue
        i = max(range(len(log2.points)),
                key=lambda j: abs(log2.points[j].value) if log2.points[j] else -1)
        cur = best.get(s.locus)
        if cur is None or abs(v) > abs(cur[0]):
            best[s.locus] = (v, f"{s.tissue.lower()}, {s.timepoints[i]}")
    return {
        g: compare.Response(key=g, perturbation="NNMF", value=v,
                            responded=compare.responds(v)[0], at=at)
        for g, (v, at) in best.items()
    }


def radiation_locus_responses() -> dict[str, compare.Response]:
    series = json.loads((RAD / "series.json").read_text())
    best: dict[str, tuple[float, str]] = {}
    for dose, by_locus in series.items():
        for locus, s in by_locus.items():
            obs = [(v, s["timepoints"][i]) for i, v in enumerate(s["log2"]) if v is not None]
            if not obs:
                continue
            v, t = max(obs, key=lambda vt: abs(vt[0]))
            cur = best.get(locus)
            if cur is None or abs(v) > abs(cur[0]):
                best[locus] = (v, f"{dose}, {t}")
    return {
        g: compare.Response(key=g, perturbation="radiation", value=v,
                            responded=compare.responds(v)[0], at=at)
        for g, (v, at) in best.items()
    }


def nnmf_locus_arm() -> dict:
    """Radiation × near-null field at LOCUS level — the honest version of the node arm.

    Node level said AOX responds to both and the directions agree. Locus level says
    radiation moves AOX1D while near-null field moves AOX2 — different members of one
    family, and AOX2 goes *down* under radiation. The node-level agreement was an
    artefact of collapsing a divergent family into one number.
    """
    qbo = set(ontology.load().index_by_agi())
    rad = {g: r for g, r in radiation_locus_responses().items() if g in qbo}
    nn = {g: r for g, r in nnmf_locus_responses().items() if g in qbo}
    rows = compare.overlap({"radiation": rad, "NNMF": nn})
    try:
        chance = compare.overlap_exceeds_chance(rows, ["radiation", "NNMF"])
        chance["tested"] = True
    except compare.ComparisonError as e:
        chance = {"tested": False, "reason": str(e)}
    return {
        "unit": "locus",
        "perturbations": ["radiation", "NNMF"],
        "summary": compare.summarise(rows),
        "chance": chance,
        "rows": [
            {
                "locus": r.key,
                "radiation": round(r.by_perturbation["radiation"].value, 4),
                "radiation_at": r.by_perturbation["radiation"].at,
                "NNMF": round(r.by_perturbation["NNMF"].value, 4),
                "NNMF_at": r.by_perturbation["NNMF"].at,
                "responded_in": r.responded_in,
                "directions_agree": r.directions_agree(),
            }
            for r in rows
        ],
    }


def divergence_example() -> dict:
    """The AOX family, locus by locus, as the worked case for why nodes can mislead."""
    fam = ["AT3G22370", "AT3G27620", "AT1G32350", "AT5G64210"]
    rad = radiation_locus_responses()
    nn = nnmf_locus_responses()
    return {
        "node_id": "AOX",
        "why": (
            "At node level AOX appears to respond to both radiation and near-null field "
            "in the same direction, which reads as one clean shared response. At locus "
            "level it is two stories. AOX1D (AT1G32350) rises under both and genuinely "
            "agrees. AOX2 (AT5G64210) also responds to both, but FALLS under radiation "
            "while rising under near-null field. The two family members move in opposite "
            "directions under radiation, so the node's single trace is the aggregator "
            "choosing a different gene at each timepoint - it swung from -2.43 at 24 h "
            "to +3.96 at 72 h for that reason, not because anything reversed. A gene "
            "family is not a unit of response, and the node-level agreement here is "
            "partly real (AOX1D) and partly an artefact (AOX2 cancelling into it)."
        ),
        "loci": [
            {
                "locus": g,
                "radiation": round(rad[g].value, 4) if g in rad else None,
                "radiation_at": rad[g].at if g in rad else None,
                "NNMF": round(nn[g].value, 4) if g in nn else None,
                "NNMF_at": nn[g].at if g in nn else None,
            }
            for g in fam
        ],
    }


def main() -> int:
    argparse.ArgumentParser().parse_args()
    loci = locus_arm()
    nodes = node_arm()
    nnmf_loci = nnmf_locus_arm()
    divergence = divergence_example()

    record = {
        "question": (
            "Do ionising radiation and magnetic-field perturbation move the same "
            "quantum-biology nodes? Overlap is a lead, not a shared mechanism."
        ),
        "response_threshold_log2fc": compare.RESPONSE_THRESHOLD,
        "caveats": [
            "Ionising radiation is not a magnetic field regime; QBO's field_regimes "
            "vocabulary is not used for it and is not extended.",
            "Different labs, growth systems (callus vs seedling) and platforms "
            "(microarray ratio vs RNA-seq DE). Direction agreement is the robust "
            "comparison; magnitude is not.",
            "Overlap is not shared mechanism. Catalase responds to almost every "
            "stress, so its presence in two lists means little on its own.",
        ],
        "locus_arm": loci,
        "nnmf_locus_arm": nnmf_loci,
        "node_arm": nodes,
        "divergence_example": divergence,
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "record.json").write_text(json.dumps(record, indent=2))

    s = loci["summary"]
    print(f"locus arm : {s['units_compared']} loci compared, "
          f"{s['responded_in_more_than_one']} responded to both, "
          f"{s['directions_agree']} agreeing in direction")
    c = loci["chance"]
    if c.get("tested"):
        print(f"            observed overlap {c['observed_overlap']} vs expected "
              f"{c['expected_overlap']} (p={c['p_value']:.4f})")
    n = nodes["summary"]
    print(f"node arm  : {n['units_compared']} nodes compared, "
          f"{n['responded_in_more_than_one']} shared — "
          f"{'tested' if nodes['chance'].get('tested') else 'NOT tested (too few)'}")
    for r in nodes["rows"]:
        marks = "".join(
            ("+" if r["by_perturbation"][p]["responded"] and r["by_perturbation"][p]["value"] > 0
             else "-" if r["by_perturbation"][p]["responded"] else ".")
            for p in ("radiation", "strong_MF", "NNMF")
        )
        print(f"    {r['node_id']:<24} rad/MF/NNMF {marks}  {r['verdict']}")
    nl = nnmf_loci["summary"]
    print(f"\nradiation x NNMF at LOCUS level: {nl['units_compared']} loci, "
          f"{nl['responded_in_more_than_one']} shared, "
          f"{nl['directions_agree']} agreeing — "
          f"{'tested' if nnmf_loci['chance'].get('tested') else 'NOT tested (too few)'}")
    for r in nnmf_loci["rows"]:
        if r["responded_in"]:
            print(f"    {r['locus']}  rad {r['radiation']:+.2f} ({r['radiation_at']})  "
                  f"NNMF {r['NNMF']:+.2f} ({r['NNMF_at']})  in={r['responded_in']} "
                  f"agree={r['directions_agree']}")
    print(f"\nwrote results/overlap/record.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
