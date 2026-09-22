#!/usr/bin/env python3
"""
Pre-registered test: is conserved spaceflight suppression associated with
spin-bearing cofactor chemistry?

===========================================================================
PRE-REGISTRATION — written before the test was run, and not edited after.
===========================================================================

HYPOTHESIS (H1)
    Among human orthologs whose spaceflight transcriptional response was tested
    for cross-species conservation, genes whose proteins carry a spin-bearing
    cofactor — an iron-sulfur cluster, a flavin, or a heme — are over-represented
    among those showing conserved DOWN-regulation, relative to those showing
    conserved UP-regulation.

NULL (H0)
    Spin-bearing-cofactor genes are represented equally among conserved-down and
    conserved-up genes.

DATA
    Hit/background : Table_S8_organelle_conservation_final.csv from
                     dr-richard-barker/OSDR_X-species_V2 — human-anchored
                     cross-species conservation of spaceflight DEGs over 22 NASA
                     OSDR datasets and six species, with a direction call per gene.
    Annotation     : UniProt/Swiss-Prot reviewed human proteins carrying
                     KW-0411 (iron-sulfur), KW-0285 (flavoprotein), KW-0349 (heme).
                     Chosen over the KEGG-derived cofactor table in the same repo
                     because that table contains ZERO iron-sulfur entries despite
                     listing Fe-S in its source script — see FINDINGS below.

TEST
    Two-sided Fisher exact on the 2x2 of (conserved direction: down | up) x
    (carries a spin-bearing cofactor: yes | no). Odds ratio reported with a
    conditional 95% interval. Alpha = 0.05.

    Secondary, pre-specified: the same test per cofactor class, and stratified by
    subcellular compartment wherever a stratum has at least 20 genes. Strata below
    that threshold are reported as underpowered rather than tested.

CONFOUNDS — stated in advance, because each of them limits what a positive
result could mean.

  1. Spaceflight is not a magnetic-field experiment. It bundles microgravity,
     ionising radiation and a hypomagnetic environment. NOTHING in this analysis
     can attribute an association to the magnetic component. A positive result is
     *consistent with* the review's hypothesis; it does not test it.

  2. Spin-bearing cofactors are concentrated in the electron transport chain, and
     the source dataset's headline finding is that mitochondrial and ETC genes are
     suppressed in spaceflight. A positive result is therefore substantially
     EXPECTED from pathway membership alone, independent of any spin chemistry.
     The stratified analysis is the attempt to separate the two; where a stratum
     is too small, that is reported, not glossed.

  3. Because of (2), a NEGATIVE result is the more informative outcome here. It
     would argue against the review's emphasis on cofactor chemistry even under
     conditions maximally favourable to finding an association.

The result of this script is reported whichever way it comes out.
===========================================================================
"""
from __future__ import annotations

import argparse
import csv
import json
import pathlib
import sys
import urllib.parse
import urllib.request
from collections import Counter, defaultdict

ROOT = pathlib.Path(__file__).resolve().parent.parent
UNIPROT = "https://rest.uniprot.org/uniprotkb/search"
UA = "quantum-biology-atlas/0.1 (mailto:dr.richard.barker@gmail.com)"
CACHE = ROOT / ".uniprot_cache"

#: Spin-bearing cofactor keywords — the exposure variable.
SPIN_KEYWORDS = {
    "KW-0411": "iron-sulfur",
    "KW-0285": "flavoprotein",
    "KW-0349": "heme",
}
#: Context keywords used only for stratification, never as exposure.
CONTEXT_KEYWORDS = {
    "KW-0496": "mitochondrion",
    "KW-0249": "electron transport",
}
MIN_STRATUM = 20
ALPHA = 0.05


def uniprot_ensg(keyword: str, timeout: int = 120) -> set[str]:
    """Reviewed human proteins with `keyword`, as unversioned Ensembl gene ids."""
    CACHE.mkdir(exist_ok=True)
    cache = CACHE / f"{keyword}.json"
    if cache.exists():
        return set(json.loads(cache.read_text()))

    q = f"organism_id:9606 AND reviewed:true AND keyword:{keyword}"
    url = (
        f"{UNIPROT}?query={urllib.parse.quote(q)}"
        f"&fields=accession,gene_primary,xref_ensembl&format=json&size=500"
    )
    genes: set[str] = set()
    while url:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            link = r.headers.get("Link", "")
            payload = json.load(r)
        for entry in payload.get("results", []):
            for xr in entry.get("uniProtKBCrossReferences", []):
                if xr.get("database") != "Ensembl":
                    continue
                for prop in xr.get("properties", []):
                    if prop.get("key") == "GeneId":
                        genes.add(prop["value"].split(".")[0])
        nxt = None
        if 'rel="next"' in link:
            nxt = link.split("<", 1)[1].split(">", 1)[0]
        url = nxt
    if not genes:
        raise SystemExit(f"UniProt returned no Ensembl gene ids for {keyword} — refusing to continue")
    cache.write_text(json.dumps(sorted(genes)))
    return genes


def fisher_2x2(a: int, b: int, c: int, d: int) -> tuple[float, float]:
    """Two-sided Fisher exact. Returns (odds_ratio, p). Table is [[a,b],[c,d]]."""
    from scipy.stats import fisher_exact

    res = fisher_exact([[a, b], [c, d]], alternative="two-sided")
    return float(res[0]), float(res[1])


def odds_ratio_ci(a: int, b: int, c: int, d: int) -> tuple[float, float]:
    """Woolf 95% CI for the odds ratio, with a Haldane-Anscombe 0.5 correction."""
    import math

    a_, b_, c_, d_ = a + 0.5, b + 0.5, c + 0.5, d + 0.5
    lor = math.log((a_ * d_) / (b_ * c_))
    se = math.sqrt(1 / a_ + 1 / b_ + 1 / c_ + 1 / d_)
    return math.exp(lor - 1.96 * se), math.exp(lor + 1.96 * se)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--conservation",
        type=pathlib.Path,
        default=ROOT / "data" / "external" / "Table_S8_organelle_conservation_final.csv",
    )
    ap.add_argument("--out", type=pathlib.Path, default=ROOT / "results" / "preregistered_test.json")
    args = ap.parse_args()

    if not args.conservation.exists():
        sys.exit(
            f"{args.conservation} not found. Fetch it from OSDR_X-species_V2 first:\n"
            f"  gh api repos/dr-richard-barker/OSDR_X-species_V2/contents/"
            f"supplementary_tables/Table_S8_organelle_conservation_final.csv --jq .download_url"
        )

    rows = list(csv.DictReader(args.conservation.open()))
    if not rows:
        sys.exit("conservation table is empty — refusing to report a result")

    # One direction call per gene. A gene appearing under several organelles with
    # conflicting directions is dropped rather than arbitrarily assigned.
    per_gene: dict[str, set[str]] = defaultdict(set)
    gene_organelles: dict[str, set[str]] = defaultdict(set)
    for r in rows:
        g = r["human_ensembl"].split(".")[0]
        per_gene[g].add(r["direction_conserved"])
        gene_organelles[g].add(r["organelle"])

    down = {g for g, d in per_gene.items() if d == {"down"}}
    up = {g for g, d in per_gene.items() if d == {"up"}}
    dropped_conflicting = sum(1 for d in per_gene.values() if len(d) > 1 or d == {"mixed"})

    print(f"Conservation table : {len(rows)} rows, {len(per_gene)} distinct genes")
    print(f"  conserved down   : {len(down)}")
    print(f"  conserved up     : {len(up)}")
    print(f"  dropped (mixed or conflicting across organelles): {dropped_conflicting}")

    print("\nFetching UniProt annotation…")
    spin_sets = {name: uniprot_ensg(kw) for kw, name in SPIN_KEYWORDS.items()}
    context_sets = {name: uniprot_ensg(kw) for kw, name in CONTEXT_KEYWORDS.items()}
    for name, s in {**spin_sets, **context_sets}.items():
        print(f"  {name:20s} {len(s):>5} human genes")

    spin_all = set().union(*spin_sets.values())
    universe = down | up
    if not universe:
        sys.exit("no genes with an unambiguous direction — refusing to report a result")

    def table(hit_set: set[str], ref_set: set[str], exposure: set[str]):
        a = len(hit_set & exposure)
        b = len(hit_set - exposure)
        c = len(ref_set & exposure)
        d = len(ref_set - exposure)
        return a, b, c, d

    results: dict = {
        "preregistration": __doc__.split("===========================================================================")[1].strip(),
        "inputs": {
            "conservation_table": str(args.conservation.relative_to(ROOT)),
            "conservation_rows": len(rows),
            "distinct_genes": len(per_gene),
            "conserved_down": len(down),
            "conserved_up": len(up),
            "dropped_mixed_or_conflicting": dropped_conflicting,
            "uniprot_set_sizes": {k: len(v) for k, v in {**spin_sets, **context_sets}.items()},
        },
        "tests": [],
    }

    # ---- primary ---------------------------------------------------------
    a, b, c, d = table(down, up, spin_all)
    orv, p = fisher_2x2(a, b, c, d)
    lo, hi = odds_ratio_ci(a, b, c, d)
    primary = {
        "name": "primary: any spin-bearing cofactor, conserved-down vs conserved-up",
        "down_with": a, "down_without": b, "up_with": c, "up_without": d,
        "odds_ratio": round(orv, 3), "ci95": [round(lo, 3), round(hi, 3)],
        "p": p, "significant": p < ALPHA,
    }
    results["tests"].append(primary)

    print("\n" + "=" * 74)
    print("PRIMARY TEST — any spin-bearing cofactor (Fe-S, flavin or heme)")
    print("=" * 74)
    print(f"  conserved DOWN : {a:>4} with cofactor / {b:>4} without "
          f"({a/(a+b)*100:.1f}% carry one)" if (a + b) else "  no down genes")
    print(f"  conserved UP   : {c:>4} with cofactor / {d:>4} without "
          f"({c/(c+d)*100:.1f}% carry one)" if (c + d) else "  no up genes")
    print(f"  odds ratio     : {orv:.3f}  (95% CI {lo:.3f}–{hi:.3f})")
    print(f"  Fisher exact p : {p:.4g}   -> {'REJECT H0' if p < ALPHA else 'FAIL TO REJECT H0'}")

    # ---- per cofactor class ----------------------------------------------
    print("\nPer cofactor class:")
    for name, s in spin_sets.items():
        a, b, c, d = table(down, up, s)
        if a + c < 5:
            print(f"  {name:18s} n={a+c:>3} in universe — UNDERPOWERED, not tested")
            results["tests"].append({"name": f"class: {name}", "underpowered": True,
                                     "down_with": a, "up_with": c})
            continue
        orv, p = fisher_2x2(a, b, c, d)
        lo, hi = odds_ratio_ci(a, b, c, d)
        flag = "*" if p < ALPHA else " "
        print(f"  {name:18s} down {a:>3}/{a+b:<4} up {c:>3}/{c+d:<4} "
              f"OR={orv:>6.3f} [{lo:.2f}–{hi:.2f}] p={p:.4g} {flag}")
        results["tests"].append({"name": f"class: {name}", "down_with": a, "down_without": b,
                                 "up_with": c, "up_without": d, "odds_ratio": round(orv, 3),
                                 "ci95": [round(lo, 3), round(hi, 3)], "p": p,
                                 "significant": p < ALPHA})

    # ---- stratified by compartment ---------------------------------------
    print(f"\nStratified by compartment (strata with >= {MIN_STRATUM} genes):")
    strata: dict[str, set[str]] = defaultdict(set)
    for g, orgs in gene_organelles.items():
        for o in orgs:
            strata[o].add(g)
    any_tested = False
    for org, members in sorted(strata.items(), key=lambda kv: -len(kv[1])):
        sd, su = down & members, up & members
        if len(sd) + len(su) < MIN_STRATUM:
            results["tests"].append({"name": f"stratum: {org}", "underpowered": True,
                                     "n": len(sd) + len(su)})
            continue
        a, b, c, d = table(sd, su, spin_all)
        if min(a + b, c + d) == 0:
            print(f"  {org:34s} n={len(sd)+len(su):>4} — one direction empty, not tested")
            continue
        any_tested = True
        orv, p = fisher_2x2(a, b, c, d)
        lo, hi = odds_ratio_ci(a, b, c, d)
        flag = "*" if p < ALPHA else " "
        print(f"  {org:34s} down {a:>3}/{a+b:<4} up {c:>3}/{c+d:<4} "
              f"OR={orv:>6.3f} p={p:.4g} {flag}")
        results["tests"].append({"name": f"stratum: {org}", "down_with": a, "down_without": b,
                                 "up_with": c, "up_without": d, "odds_ratio": round(orv, 3),
                                 "ci95": [round(lo, 3), round(hi, 3)], "p": p,
                                 "significant": p < ALPHA})
    under = [t for t in results["tests"] if t.get("underpowered") and t["name"].startswith("stratum")]
    print(f"  ({len(under)} strata below the {MIN_STRATUM}-gene threshold were not tested)")

    # ---- the confound check ----------------------------------------------
    # Is the exposure simply a proxy for being mitochondrial / ETC?
    print("\nConfound check — how far is 'spin cofactor' a proxy for 'mitochondrial'?")
    for name, cset in context_sets.items():
        both = len(spin_all & cset & universe)
        spin_in = len(spin_all & universe)
        print(f"  of {spin_in} spin-cofactor genes in the universe, "
              f"{both} ({both/spin_in*100:.0f}%) are also annotated {name}")
        results.setdefault("confound", {})[name] = {
            "spin_genes_in_universe": spin_in, "also_in_context": both,
            "fraction": round(both / spin_in, 4) if spin_in else None,
        }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, indent=2))
    print(f"\nWrote {args.out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def minimum_detectable_or(
    n_down: int, n_up: int, baseline_rate: float, n_sim: int = 4000, alpha: float = 0.05
) -> dict:
    """What odds ratio would this design have detected 80% of the time?

    Reported because "p = 0.48, not significant" is uninterpretable on its own: it
    could mean the effect is absent, or that the design could never have seen it.
    This simulates the observed marginals at a range of true odds ratios and finds
    where power reaches 80%. It is a prospective calculation on the realised design,
    not post-hoc power on the observed effect, which would be circular.
    """
    import random
    from scipy.stats import fisher_exact

    rng = random.Random(20260922)
    out = []
    for true_or in (1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 7.0, 10.0):
        # Odds in the 'up' (reference) arm from the observed baseline rate.
        odds_ref = baseline_rate / (1 - baseline_rate)
        p_down = (odds_ref * true_or) / (1 + odds_ref * true_or)
        hits = 0
        for _ in range(n_sim):
            a = sum(rng.random() < p_down for _ in range(n_down))
            c = sum(rng.random() < baseline_rate for _ in range(n_up))
            _, p = fisher_exact([[a, n_down - a], [c, n_up - c]], alternative="two-sided")
            hits += p < alpha
        power = hits / n_sim
        out.append({"true_odds_ratio": true_or, "power": round(power, 3)})
        if power >= 0.80:
            break
    detectable = next((r["true_odds_ratio"] for r in out if r["power"] >= 0.80), None)
    return {"curve": out, "min_detectable_or_at_80pct_power": detectable}
