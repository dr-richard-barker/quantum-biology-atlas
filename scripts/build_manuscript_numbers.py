#!/usr/bin/env python3
"""
Emit `manuscript/numbers.tex`: every quantity the manuscript states, as LaTeX macros.

The manuscript body contains **no literal numbers**. It writes `\\NMaps`, `\\OsdEightP`
and so on, and this script defines them from the generated artefacts. That is not
pedantry: the figures this atlas replaces had their values hard-coded, and a manuscript
is the place where a stale number does the most damage — it is the artefact that gets
cited.

A consequence worth stating: if an analysis is re-run and a number moves, the manuscript
moves with it on the next build. If an artefact is missing, the build fails here rather
than silently leaving an undefined macro to render as a blank.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

OUT = ROOT / "manuscript" / "numbers.tex"


def need(path: pathlib.Path) -> dict:
    if not path.exists():
        raise SystemExit(
            f"{path.relative_to(ROOT)} is missing. The manuscript's numbers come from "
            f"the artefacts; build them before building the manuscript."
        )
    return json.loads(path.read_text())



def _gene_symbol_only_coverage() -> int:
    """How many atlas loci the GPL9020 `GENE_SYMBOL` column alone would reach.

    Computed, not quoted. The manuscript uses this to say why the platform join reads
    `ACCESSION_STRING` instead, and a number asserted in prose about a parsing choice is
    exactly the kind that rots when the parser changes.
    """
    import re

    from qbio import ontology

    path = ROOT / "data" / "external" / "GPL9020.txt"
    if not path.exists():
        raise SystemExit(f"{path.name} is missing; it is needed for one manuscript number")
    agi = re.compile(r"^AT[1-5CM]G\d{5}$", re.I)
    rows, started = [], False
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if line.startswith("!platform_table_begin"):
                started = True
                continue
            if line.startswith("!platform_table_end"):
                break
            if started:
                rows.append(line.rstrip("\n").split("\t"))
    hdr = rows[0]
    i_sym, i_ctl = hdr.index("GENE_SYMBOL"), hdr.index("CONTROL_TYPE")
    symbols = {
        r[i_sym].strip().upper()
        for r in rows[1:]
        if len(r) > max(i_sym, i_ctl) and r[i_ctl].strip().upper() == "FALSE"
        and agi.match(r[i_sym].strip())
    }
    return len(symbols & set(ontology.load().index_by_agi()))


def main() -> int:
    argparse.ArgumentParser().parse_args()

    manifest = need(ROOT / "catalog" / "manifest.json")
    orth = need(ROOT / "catalog" / "orthologs.json")
    osd27 = need(ROOT / "results" / "osd27" / "record.json")
    osd8 = need(ROOT / "results" / "osd8" / "record.json")
    osd782 = need(ROOT / "results" / "osd782" / "record.json")
    overlap = need(ROOT / "results" / "overlap" / "record.json")
    prereg = need(ROOT / "results" / "preregistered_test.json")
    parmagnani = need(ROOT / "results" / "papers" / "Parmagnani2022" / "record.json")
    agliassa = need(ROOT / "results" / "papers" / "Agliassa2018a" / "record.json")

    t = manifest["totals"]
    tiers = t["nodes_by_tier"]
    primary = prereg["tests"][0]
    o8 = osd8["specificity"][osd8["primary_group"]]
    nl = overlap["nnmf_locus_arm"]
    la = overlap["locus_arm"]

    # Radiation specificity: the best (smallest) p across dose and time, so the
    # manuscript cannot be accused of quoting the most convenient one.
    rad_best = min(
        (s for bt in osd782["specificity"].values() for s in bt.values()),
        key=lambda s: s["p_value"],
    )
    rad_max_obs = max(s["observed_mean_abs_log2fc"]
                      for bt in osd782["specificity"].values() for s in bt.values())

    m: dict[str, object] = {
        # --- the corpus ---
        "NMaps": t["maps"],
        "NNodes": t["nodes"],
        "NEdges": t["edges"],
        "NLoci": t["distinct_agi_loci"],
        "NEntities": t["entities"],
        "NRefs": t["references"],
        "NTierOne": tiers.get("T1", 0),
        "NTierTwo": tiers.get("T2", 0),
        "NTierThree": tiers.get("T3", 0),
        "NTierFour": tiers.get("T4", 0),
        "PctTierThreeFour": round(
            100 * (tiers.get("T3", 0) + tiers.get("T4", 0)) / t["nodes"]
        ),
        "QboVersion": manifest["qbo_version"],
        # --- orthology ---
        "NSpecies": len(orth["species"]),
        "OrthHuman": orth["species"]["homo_sapiens"]["mapped"],
        "OrthFly": orth["species"]["drosophila_melanogaster"]["mapped"],
        "OrthHumanCorroborated": sum(
            1 for v in orth["species"]["homo_sapiens"]["orthologs"].values()
            if v["corroborated"]
        ),
        # --- the pre-registered test ---
        "PreregOR": f"{primary['odds_ratio']:.2f}",
        "PreregP": f"{primary['p']:.2f}",
        "PreregMDE": f"{prereg['power']['min_detectable_or_at_80pct_power']:.1f}",
        # --- OSD-27, the fly ---
        "OsdTwentySevenContrasts": len(osd27["contrasts"]),
        "OsdTwentySevenTesla": f"{osd27['field_tesla_nominal']:g}",
        "OsdTwentySevenOrth": osd27["orthology"]["mapped"],
        "OsdTwentySevenNodes": sum(
            len(v["consistency"]) for v in osd27["maps"].values() if "consistency" in v
        ),
        "OsdTwentySevenConsistent": sum(
            1 for v in osd27["maps"].values() if "consistency" in v
            for c in v["consistency"] if c["consistent_direction"] != "mixed"
        ),
        "CryFly": osd27["cry1"]["drosophila"][0],
        # --- OSD-8, the strong field and the specificity test ---
        "OsdEightTesla": f"{osd8['groups'][0]['field_tesla']:g}",
        "OsdEightLoci": osd8["platform_join"]["distinct_loci"],
        "OsdEightObs": f"{o8['observed_mean_abs_log2fc']:.4f}",
        "OsdEightBg": f"{o8['background_mean']:.4f}",
        "OsdEightP": f"{o8['p_value']:.3f}",
        "OsdEightPerms": f"{o8['permutations']:,}",
        "OsdEightSymbolOnly": _gene_symbol_only_coverage(),
        # --- OSD-782, radiation ---
        "RadDoses": len(osd782["doses_gy"]),
        "RadTimepoints": len(osd782["timepoints"]),
        "RadLoci": osd782["qbo_loci_measured"],
        "RadBestP": f"{rad_best['p_value']:.2f}",
        "RadMaxObs": f"{rad_max_obs:.3f}",
        "RadVsMagnetFold": f"{rad_max_obs / o8['observed_mean_abs_log2fc']:.1f}",
        # --- the overlap ---
        "OverlapThreshold": overlap["response_threshold_log2fc"],
        "OverlapNnmfN": nl["summary"]["units_compared"],
        "OverlapNnmfShared": nl["summary"]["responded_in_more_than_one"],
        "OverlapNnmfAgree": nl["summary"]["directions_agree"],
        "OverlapStrongN": la["summary"]["units_compared"],
        "OverlapStrongObs": la["chance"]["observed_overlap"],
        "OverlapStrongExp": f"{la['chance']['expected_overlap']:.1f}",
        "OverlapStrongP": f"{la['chance']['p_value']:.3f}",
        # --- published-results demonstrations ---
        "ParmLoci": parmagnani["loci_in_table"],
        "ParmCells": f"{parmagnani['cells_parsed']:,}",
        "ParmTimepoints": len(parmagnani["figures"][0]["timepoints"]),
        "AglLoci": agliassa["loci_in_table"],
        "AglCells": f"{agliassa['cells_parsed']:,}",
        "AglQbo": len(agliassa["qbo_loci_covered"]),
    }

    lines = [
        "% Generated by scripts/build_manuscript_numbers.py — do not edit.",
        "%",
        "% Every quantity the manuscript states is defined here from a build artefact.",
        "% The body contains no literal numbers, so a re-run that moves a result moves",
        "% the manuscript with it rather than leaving a stale figure in the text.",
        "",
    ]
    for k, v in m.items():
        lines.append(f"\\newcommand{{\\{k}}}{{{v}}}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n")

    print(f"wrote {OUT.relative_to(ROOT)} — {len(m)} macros")
    for k in ("NMaps", "NNodes", "OsdEightP", "OverlapNnmfAgree", "RadVsMagnetFold"):
        print(f"  \\{k} = {m[k]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
