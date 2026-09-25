#!/usr/bin/env python3
"""
Emit `manuscript/references.bib` — generated, never hand-edited.

Two sources, both verified rather than typed:

  * **`evidence/references.yaml`** — the atlas's own evidence base. Every entry there was
    already resolved against CrossRef and title-matched when it was built, so the
    bibliographic detail is carried straight through.
  * **`METHODS`** below — the software and database citations an Applications Note
    needs. These are NOT in the review's bibliography, so each one is resolved against
    CrossRef *at build time* and the build fails if a DOI does not resolve or its title
    does not match what this file claims it is.

That second check is the point. Three DOIs guessed from memory while drafting this
resolved to a paper on HIV RNA methylation, one on metagenomics and one on sequencing
error models. None of them would have looked wrong in a reference list.

**The companion review gets `@unpublished{}` with no DOI, volume or pages.** A
plausible-looking placeholder is how a fabricated citation enters a bibliography and
stays there; this repository's own history contains exactly that.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "manuscript" / "references.bib"
UA = "quantum-biology-atlas/0.1 (mailto:dr.richard.barker@gmail.com)"

#: Method and database citations, with the title this file believes each DOI to be.
#: The claim is checked against CrossRef; a mismatch fails the build.
METHODS = [
    ("Ge2020", "10.1093/bioinformatics/btz931",
     "ShinyGO: a graphical gene-set enrichment tool"),
    ("LeNovere2009", "10.1038/nbt.1558",
     "The Systems Biology Graphical Notation"),
    ("Cunningham2022", "10.1093/nar/gkab1049",
     "Ensembl 2022"),
    ("Kuznetsov2022", "10.1093/nar/gkac998",
     "OrthoDB v11: annotation of orthologs"),
    ("Berrios2021", "10.1093/nar/gkaa887",
     "NASA GeneLab: interfaces for the exploration of space omics data"),
]

#: The companion review. No DOI is asserted and none is invented.
REVIEW = """@unpublished{PorterfieldBarker,
  author  = {Porterfield, D. Marshall and Barker, Richard},
  title   = {{Plant Responses to Near-Null Magnetic Fields: Geomagnetism,
              Bioenergetics, and Primary Metabolism in Arabidopsis and Brassica}},
  note    = {Manuscript in preparation. No DOI has been issued; none is recorded here,
             deliberately},
  year    = {2026}
}
"""


def tokens(s: str) -> set[str]:
    return set(re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).split())


def overlap(a: str, b: str) -> float:
    ta, tb = tokens(a), tokens(b)
    return len(ta & tb) / max(1, len(ta | tb))


def crossref(doi: str) -> dict:
    req = urllib.request.Request(
        "https://api.crossref.org/works/" + urllib.parse.quote(doi, safe="/().-_"),
        headers={"User-Agent": UA},
    )
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=45) as fh:
                return json.load(fh)["message"]
        except urllib.error.HTTPError as e:
            raise SystemExit(f"{doi}: does not resolve at CrossRef (HTTP {e.code})")
        except Exception:
            time.sleep(1 + attempt * 2)
    raise SystemExit(f"{doi}: CrossRef did not answer after 4 attempts")


def clean(s: str) -> str:
    """Strip the markup CrossRef embeds in titles, and brace what BibTeX would lowercase."""
    s = re.sub(r"<[^>]+>", "", s or "").replace(" ", " ")
    return re.sub(r"\s+", " ", s).strip()


def authors_bibtex(names: list[str]) -> str:
    out = []
    for n in names:
        n = n.strip()
        if "," in n:
            out.append(n)
        else:
            parts = n.split()
            out.append(f"{parts[-1]}, {' '.join(parts[:-1])}" if len(parts) > 1 else n)
    return " and ".join(out)


def entry_from_evidence(r: dict) -> str:
    fields = [
        f"  author  = {{{authors_bibtex(r.get('authors', []))}}}",
        f"  title   = {{{{{clean(r['title'])}}}}}",  # double-braced: no recasing
        f"  journal = {{{clean(r.get('container', ''))}}}",
        f"  year    = {{{r.get('year', '')}}}",
    ]
    for key, name in (("volume", "volume"), ("issue", "number"), ("page", "pages")):
        if r.get(key):
            fields.append(f"  {name:<7} = {{{r[key]}}}")
    fields.append(f"  doi     = {{{r['doi']}}}")
    return "@article{" + r["key"] + ",\n" + ",\n".join(fields) + "\n}\n"


def entry_from_crossref(key: str, doi: str, m: dict) -> str:
    names = [
        f"{a.get('family', '')}, {a.get('given', '')}".strip(", ")
        for a in m.get("author", [])
    ]
    fields = [
        f"  author  = {{{' and '.join(names)}}}",
        f"  title   = {{{{{clean((m.get('title') or [''])[0])}}}}}",
        f"  journal = {{{clean((m.get('container-title') or [''])[0])}}}",
        f"  year    = {{{m['issued']['date-parts'][0][0]}}}",
    ]
    for src, name in (("volume", "volume"), ("issue", "number"), ("page", "pages")):
        if m.get(src):
            fields.append(f"  {name:<7} = {{{m[src]}}}")
    fields.append(f"  doi     = {{{doi}}}")
    return "@article{" + key + ",\n" + ",\n".join(fields) + "\n}\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true",
                    help="skip the CrossRef re-check of METHODS (not for a real build)")
    args = ap.parse_args()

    ev = yaml.safe_load((ROOT / "evidence" / "references.yaml").read_text())
    refs = ev["references"]

    out = [
        "% Generated by scripts/build_manuscript_bib.py — do not edit.",
        "%",
        "% Entries from the atlas's evidence base were CrossRef-resolved and",
        "% title-matched when that base was built. The method citations below are",
        "% re-resolved against CrossRef on every build, and the build fails if a DOI",
        "% does not resolve or resolves to a different paper.",
        "%",
        "% The companion review is @unpublished with no doi/volume/pages. A plausible",
        "% placeholder is how a fabricated citation enters a bibliography and stays.",
        "",
        REVIEW,
    ]

    checked = 0
    for key, doi, expect in METHODS:
        if args.offline:
            raise SystemExit(
                "--offline would emit method citations that have not been verified. "
                "Refusing: an unverified reference is the failure this script exists "
                "to prevent."
            )
        m = crossref(doi)
        title = (m.get("title") or [""])[0]
        score = overlap(re.sub(r"<[^>]+>", "", title), expect)
        if score < 0.3:
            raise SystemExit(
                f"{key} ({doi}) resolves to a DIFFERENT paper.\n"
                f"  expected : {expect}\n"
                f"  CrossRef : {re.sub(r'<[^>]+>', '', title)[:90]}\n"
                f"  overlap  : {score:.2f}"
            )
        out.append(entry_from_crossref(key, doi, m))
        checked += 1
        print(f"  verified {key:<16} {doi:<32} overlap {score:.2f}")
        time.sleep(0.15)

    for r in sorted(refs, key=lambda x: x["key"]):
        out.append(entry_from_evidence(r))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(out))
    print(f"\nwrote {OUT.relative_to(ROOT)}: {checked} method citations re-verified, "
          f"{len(refs)} from the evidence base, 1 unpublished with no DOI")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
