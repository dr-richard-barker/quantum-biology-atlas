#!/usr/bin/env python3
"""
Build the published catalogue: `catalog/manifest.json` plus the per-map QBO sidecars.

This is what makes the atlas consumable by something other than this repository.
The SBGN Pathway Visualizer already renders SBGN-ML deterministically and overlays
omics data on it; pointing it at this manifest adds the quantum-biology maps as a
pathway source without either project needing to know much about the other.

The manifest is deliberately flat and self-describing: a consumer needs the map list,
a URL per SBGN file, and — the part that is not in the SBGN — the evidence tier,
quantum class and citations per node, so it can draw the tier channel and show a
tooltip without parsing the `<extension>` blocks.

Everything here is derived from the compiled maps and the ontology. Nothing is
hand-maintained, so the manifest cannot drift from what is actually published.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from qbio import maps, ontology  # noqa: E402

DEFAULT_BASE = "https://dr-richard-barker.github.io/quantum-biology-atlas"


def build(base_url: str, out_dir: pathlib.Path) -> dict:
    onto = ontology.load()
    records = maps.compile_all(onto)

    out_dir.mkdir(parents=True, exist_ok=True)
    sidecar_dir = out_dir / "qbo"
    sidecar_dir.mkdir(exist_ok=True)

    entries = []
    for r in records:
        spec = next(
            maps.load_spec(p)
            for p in sorted((ROOT / "maps" / "src").glob("*.yaml"))
            if maps.load_spec(p).id == r["id"]
        )

        # Per-node annotation, flattened so a consumer does not have to read SBGN.
        nodes = []
        for nid in spec.node_ids:
            qbo_id = spec.nodes.get(nid, {}).get("qbo")
            ent = onto.get(qbo_id) if qbo_id else None
            if ent is None:
                continue
            nodes.append(
                {
                    "node_id": nid,
                    "qbo": ent.id,
                    "label": ent.label,
                    "kind": ent.kind,
                    "compartment": ent.compartment,
                    "evidence_tier": ent.evidence_tier,
                    "confidence": ent.confidence,
                    "quantum_class": list(ent.quantum_class),
                    "nuclei": list(ent.nuclei),
                    "agi": list(ent.agi),
                    "magnetically_addressable": ent.is_magnetically_addressable(onto.core),
                    "rationale": ent.rationale,
                    "caveat": ent.caveat,
                    "evidence": [
                        {
                            "ref": ev.ref,
                            "doi": (onto.references.get(ev.ref) or {}).get("doi", ""),
                            "claim": ev.claim,
                            "direction": ev.direction,
                            "field_regime": ev.field_regime,
                            "species": ev.species,
                        }
                        for ev in ent.evidence
                    ],
                }
            )

        sidecar = {
            "map": r["id"],
            "title": r["title"],
            "qbo_version": onto.core.version,
            "nodes": nodes,
        }
        (sidecar_dir / f"{r['id']}.json").write_text(json.dumps(sidecar, indent=2))

        entries.append(
            {
                "id": r["id"],
                "title": r["title"],
                "subtitle": r["subtitle"],
                "caption": r["caption"],
                "derived_from": r["derived_from"],
                "species_anchor": r["species_anchor"],
                "nodes": r["nodes"],
                "edges": r["edges"],
                "tiers": r["tiers"],
                "compartments": sorted(set(r["compartments"])),
                "agi_loci": r["agi_loci"],
                "sbgn_url": f"{base_url}/{r['sbgn']}",
                "svg_url": f"{base_url}/{r['svg']}",
                "qbo_url": f"{base_url}/catalog/qbo/{r['id']}.json",
            }
        )

    tier_totals: dict[str, int] = {}
    for e in entries:
        for t, n in e["tiers"].items():
            tier_totals[t] = tier_totals.get(t, 0) + n

    manifest = {
        "name": "Quantum Biology Atlas",
        "description": (
            "Identifier-bound SBGN-ML pathway maps annotated with quantum-mechanistic "
            "descriptors and an explicit evidence tier per node."
        ),
        "qbo_version": onto.core.version,
        "base_url": base_url,
        "license": {"maps": "CC-BY-4.0", "ontology": "CC-BY-4.0", "code": "MIT"},
        "evidence_tiers": [
            {"id": t["id"], "label": t["label"], "definition": " ".join(t["definition"].split())}
            for t in onto.core._data.get("evidence_tiers", [])
        ],
        "totals": {
            "maps": len(entries),
            "nodes": sum(e["nodes"] for e in entries),
            "edges": sum(e["edges"] for e in entries),
            "distinct_agi_loci": len({l for e in entries for l in e["agi_loci"]}),
            "entities": len(onto),
            "references": len(onto.references),
            "nodes_by_tier": tier_totals,
        },
        "reading_note": (
            "Evidence tier is a border channel on every rendered map: T1 solid heavy, "
            "T2 solid light, T3 dashed, T4 hairline. The maps are mostly dashed, which "
            "is the finding rather than a defect — the near-null-field literature is "
            "developmental and nutritional and has not measured a respiratory complex "
            "directly. No base map encodes a quantitative value; numbers appear only "
            "when measured data is projected onto one."
        ),
        "maps": entries,
    }

    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default=DEFAULT_BASE)
    ap.add_argument("--out", type=pathlib.Path, default=ROOT / "catalog")
    args = ap.parse_args()

    m = build(args.base_url, args.out)
    t = m["totals"]
    print(f"catalog: {t['maps']} maps, {t['nodes']} nodes, {t['edges']} edges")
    print(f"  {t['distinct_agi_loci']} distinct AGI loci, {t['entities']} entities, "
          f"{t['references']} references")
    print(f"  nodes by tier: {t['nodes_by_tier']}")
    print(f"  wrote {args.out / 'manifest.json'} + {t['maps']} QBO sidecars")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
