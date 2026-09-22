#!/usr/bin/env python3
"""
Resolve Arabidopsis gene symbols to AGI loci against Ensembl Plants.

Authoring aid, not part of the runtime. The ontology stores AGI loci directly
because that is what omics tables join on; this script is how those loci get
into the ontology without anyone typing one from memory, and
`tests/test_ontology.py` independently re-checks every locus that lands there.

Two things learned the hard way and encoded here:

  * Symbol lookup is ambiguous. `ACO2` returns ACC oxidase 2, not aconitase 2;
    `LIP1` returns a lipase, not lipoyl synthase. So the resolver reports the
    description alongside every hit and the caller is expected to read it — and
    the ontology stores the AGI, never the symbol.

  * Ensembl times out. Results are cached per symbol under `.locus_cache/`, and
    the run writes its output file incrementally, so an interrupted run resumes
    instead of starting over.

Usage:
    python3 scripts/resolve_loci.py SYMBOL [SYMBOL ...] --out data/loci.tsv
    python3 scripts/resolve_loci.py --file symbols.txt --out data/loci.tsv
    python3 scripts/resolve_loci.py --id AT4G26970          # reverse lookup
"""
from __future__ import annotations

import argparse
import json
import pathlib
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ENSEMBL = "https://rest.ensembl.org"
UA = "quantum-biology-atlas/0.1 (mailto:dr.richard.barker@gmail.com)"
CACHE = pathlib.Path(__file__).resolve().parent.parent / ".locus_cache"
RETRIABLE = (socket.timeout, TimeoutError, urllib.error.URLError, ConnectionError)


def _get(path: str, timeout: int = 30) -> object | None:
    """GET a JSON endpoint, retrying transient failures. None = definitively absent."""
    req = urllib.request.Request(
        ENSEMBL + path, headers={"Accept": "application/json", "User-Agent": UA}
    )
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429:                       # Ensembl rate limit
                time.sleep(2 + attempt * 2)
                continue
            if e.code in (400, 404):                # no such symbol/id
                return None
            time.sleep(1 + attempt)
        except RETRIABLE:
            time.sleep(1 + attempt * 2)
    return None


def resolve(symbol: str, species: str = "arabidopsis_thaliana") -> dict | None:
    """Symbol -> {agi, symbol, description}. Cached. Falls back to xref search."""
    CACHE.mkdir(exist_ok=True)
    key = CACHE / f"{species}__{symbol.replace('/', '_')}.json"
    if key.exists():
        cached = json.loads(key.read_text())
        return cached or None

    q = urllib.parse.quote(symbol)
    hit = None

    d = _get(f"/lookup/symbol/{species}/{q}?")
    if isinstance(d, dict) and d.get("id"):
        hit = {
            "agi": d["id"],
            "symbol": d.get("display_name") or symbol,
            "description": (d.get("description") or "").split(" [Source:")[0],
        }
    else:
        # Ensembl's display_name is not always the community symbol (RISP, FIT,
        # NDUFS4 all miss). /xrefs/symbol also searches external-database names.
        x = _get(f"/xrefs/symbol/{species}/{q}?object_type=gene")
        if isinstance(x, list) and x:
            gid = x[0].get("id")
            g = _get(f"/lookup/id/{gid}?") if gid else None
            if isinstance(g, dict) and g.get("id"):
                hit = {
                    "agi": g["id"],
                    "symbol": g.get("display_name") or symbol,
                    "description": (g.get("description") or "").split(" [Source:")[0],
                }

    key.write_text(json.dumps(hit or {}))
    return hit


def reverse(agi: str) -> dict | None:
    """AGI -> {symbol, description}. Cached, because the ontology test calls it for
    every locus in the ontology and Ensembl is not always quick."""
    CACHE.mkdir(exist_ok=True)
    key = CACHE / f"id__{agi.upper()}.json"
    if key.exists():
        return json.loads(key.read_text()) or None

    d = _get(f"/lookup/id/{urllib.parse.quote(agi)}?")
    hit = None
    if isinstance(d, dict) and d.get("id"):
        hit = {
            "agi": d["id"],
            "symbol": d.get("display_name") or "",
            "description": (d.get("description") or "").split(" [Source:")[0],
        }
    # Only cache a definitive answer; a transient failure must not be memoised
    # as "this locus does not exist".
    if hit is not None:
        key.write_text(json.dumps(hit))
    return hit


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("symbols", nargs="*")
    ap.add_argument("--file", type=pathlib.Path)
    ap.add_argument("--out", type=pathlib.Path)
    ap.add_argument("--id", action="append", default=[], help="reverse-lookup an AGI locus")
    ap.add_argument("--species", default="arabidopsis_thaliana")
    args = ap.parse_args()

    for agi in args.id:
        r = reverse(agi)
        print(f"  {agi:<12} {r['symbol'] if r else 'NOT FOUND':<14} {r['description'][:60] if r else ''}")
    if args.id and not (args.symbols or args.file):
        return 0

    symbols = list(args.symbols)
    if args.file:
        symbols += [
            ln.strip() for ln in args.file.read_text().splitlines()
            if ln.strip() and not ln.startswith("#")
        ]
    if not symbols:
        ap.error("give at least one symbol, --file, or --id")

    fh = None
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        fh = args.out.open("w", encoding="utf-8")
        fh.write("symbol\tagi\tensembl_symbol\tdescription\n")

    found = missing = 0
    for s in symbols:
        r = resolve(s, args.species)
        if not r:
            missing += 1
            print(f"  {s:<12} NOT FOUND", file=sys.stderr)
            continue
        found += 1
        flag = "" if r["symbol"].upper() == s.upper() else "  <- symbol differs, CHECK"
        print(f"  {s:<12} {r['agi']}  {r['description'][:56]}{flag}")
        if fh:
            fh.write(f"{s}\t{r['agi']}\t{r['symbol']}\t{r['description']}\n")
            fh.flush()          # incremental: an interrupted run keeps what it got

    if fh:
        fh.close()
        print(f"\nwrote {found} loci to {args.out}")
    if missing:
        print(f"{missing} unresolved", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
