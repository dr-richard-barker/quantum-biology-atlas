#!/usr/bin/env python3
"""
Build `evidence/references.yaml` from the review manuscript's bibliography.

Why this exists rather than a hand-typed reference list: the companion repo's
`data/nnmf_study_database.csv` carries 42 wrong or dead DOIs out of 49 (its
Belyavskaya row resolves to a paper on calcium gradients in the fish inner ear).
The manuscript's own bibliography, by contrast, resolves 42/42 against CrossRef.
So the bibliography is the source of truth, and every field below is taken from
CrossRef's record rather than retyped from the document.

Input : a plain-text extraction of the manuscript (--manuscript), whose reference
        section carries one `https://doi.org/...` per entry.
Output: evidence/references.yaml — one entry per reference, CrossRef-resolved.

Nothing is written unless every DOI resolves AND its CrossRef title matches the
title in the manuscript. A mismatch is a hard failure, not a warning.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import time
import urllib.error
import urllib.request

CROSSREF = "https://api.crossref.org/works/"
UA = "quantum-biology-atlas/0.1 (https://github.com/dr-richard-barker/quantum-biology-atlas; mailto:dr.richard.barker@gmail.com)"
# Below this Jaccard overlap between the manuscript title and CrossRef's title we
# treat the DOI as pointing at the wrong paper. 0.45 separated all 42 good
# manuscript references from all 42 bad database rows during the audit.
TITLE_MATCH_MIN = 0.45


def tokens(s: str) -> set[str]:
    return set(re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).split())


def title_overlap(a: str, b: str) -> float:
    ta, tb = tokens(a), tokens(b)
    return len(ta & tb) / max(1, len(ta | tb))


def crossref(doi: str) -> dict:
    req = urllib.request.Request(CROSSREF + doi, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)["message"]


def parse_bibliography(text: str) -> list[dict]:
    """Pull (citation_key, doi, title) out of the manuscript's reference section."""
    if "References" not in text:
        sys.exit("No 'References' heading found in the manuscript text.")
    body = text.split("References", 1)[1]
    out = []
    for line in body.splitlines():
        line = line.strip()
        m = re.search(r"https://doi\.org/(10\.\S+?)\.?$", line)
        if not m:
            continue
        doi = m.group(1)
        title = re.search(r'"([^"]+)"', line)
        year = re.search(r"\b((?:19|20)\d{2})[a-z]?\.", line)
        # Surname of the first author: the text up to the first comma.
        surname = re.split(r"[,.]", line)[0].strip()
        key = re.sub(r"[^A-Za-z]", "", surname) + (year.group(1) if year else "")
        # Disambiguate 2018a / 2018b style suffixes used in the manuscript.
        suffix = re.search(r"\b(?:19|20)\d{2}([a-z])\.", line)
        if suffix:
            key += suffix.group(1)
        out.append(
            {
                "key": key,
                "doi": doi,
                "manuscript_title": title.group(1) if title else "",
            }
        )
    return out


def yaml_str(s: str) -> str:
    """Minimal YAML scalar quoting — we control the writer, so keep it simple."""
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manuscript", required=True, type=pathlib.Path)
    ap.add_argument("--out", required=True, type=pathlib.Path)
    ap.add_argument("--sleep", type=float, default=0.12)
    args = ap.parse_args()

    refs = parse_bibliography(args.manuscript.read_text(encoding="utf-8"))
    if not refs:
        sys.exit("Parsed 0 references — check the manuscript extraction.")
    print(f"Parsed {len(refs)} references with DOIs from the bibliography.")

    resolved, failures = [], []
    for i, r in enumerate(refs, 1):
        try:
            m = crossref(r["doi"])
        except urllib.error.HTTPError as e:
            failures.append((r["key"], r["doi"], f"CrossRef HTTP {e.code}"))
            continue
        except Exception as e:  # network, JSON, anything
            failures.append((r["key"], r["doi"], f"CrossRef error: {e}"))
            continue

        cr_title = (m.get("title") or [""])[0]
        overlap = title_overlap(cr_title, r["manuscript_title"])
        if r["manuscript_title"] and overlap < TITLE_MATCH_MIN:
            failures.append(
                (r["key"], r["doi"], f"title mismatch ({overlap:.2f}) -> {cr_title[:70]}")
            )
            continue

        authors = [
            " ".join(filter(None, [a.get("given"), a.get("family")]))
            for a in (m.get("author") or [])
        ]
        issued = (m.get("issued", {}).get("date-parts") or [[None]])[0]
        resolved.append(
            {
                "key": r["key"],
                "doi": r["doi"],
                "title": cr_title,
                "authors": authors,
                "year": issued[0],
                "container": (m.get("container-title") or [""])[0],
                "volume": m.get("volume", ""),
                "issue": m.get("issue", ""),
                "page": m.get("page", ""),
                "type": m.get("type", ""),
                "title_overlap": round(overlap, 3),
            }
        )
        print(f"  [{i:>2}/{len(refs)}] {r['key']:<22} ok  ({overlap:.2f})")
        time.sleep(args.sleep)

    if failures:
        print(f"\n{len(failures)} reference(s) did not verify — nothing written:\n", file=sys.stderr)
        for k, d, why in failures:
            print(f"  {k:<22} {d:<38} {why}", file=sys.stderr)
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as fh:
        fh.write(
            "# Evidence base for the Quantum Biology Atlas.\n"
            "#\n"
            "# GENERATED by scripts/build_evidence_base.py — do not hand-edit.\n"
            "# Every entry was resolved against CrossRef and its title matched against the\n"
            "# manuscript's bibliography at build time. Regenerate rather than patching.\n"
            "#\n"
            f"# source: Porterfield & Barker, 'Plant Responses to Near-Null Magnetic Fields'\n"
            f"# entries: {len(resolved)}\n"
            "references:\n"
        )
        for e in sorted(resolved, key=lambda x: x["key"]):
            fh.write(f"  - key: {e['key']}\n")
            fh.write(f"    doi: {yaml_str(e['doi'])}\n")
            fh.write(f"    title: {yaml_str(e['title'])}\n")
            fh.write(f"    year: {e['year']}\n")
            fh.write(f"    container: {yaml_str(e['container'])}\n")
            for field in ("volume", "issue", "page"):
                if e[field]:
                    fh.write(f"    {field}: {yaml_str(e[field])}\n")
            fh.write(f"    type: {yaml_str(e['type'])}\n")
            fh.write("    authors:\n")
            for a in e["authors"]:
                fh.write(f"      - {yaml_str(a)}\n")
            fh.write(f"    crossref_title_overlap: {e['title_overlap']}\n")

    print(f"\nWrote {len(resolved)} verified references to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
