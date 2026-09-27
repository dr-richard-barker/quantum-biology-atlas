#!/usr/bin/env python3
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from qbio import ontology, maps

DOCS_ASSETS = ROOT / "docs" / "assets"
DOCS_ASSETS.mkdir(parents=True, exist_ok=True)
OUT_FILE = DOCS_ASSETS / "qb-graph-data.json"

def main():
    qbo = ontology.load()
    
    nodes_out = []
    for entity in qbo:
        nodes_out.append({
            "data": {
                "id": entity.id.replace("QBO:", ""),
                "label": entity.label,
                "kind": entity.kind,
                "quantum_class": entity.quantum_class,
                "evidence_tier": entity.evidence_tier,
                "is_magnetically_addressable": entity.is_magnetically_addressable(qbo.core)
            }
        })
        
    edges_out = []
    edge_set = set()
    map_files = (ROOT / "maps" / "src").glob("*.yaml")
    for mf in map_files:
        spec = maps.load_spec(mf)
        for (source, target, eclass, elabel) in spec.edges:
            edge_id = f"{source}-{target}-{eclass}"
            if edge_id not in edge_set:
                edge_set.add(edge_id)
                edges_out.append({
                    "data": {
                        "id": edge_id,
                        "source": source,
                        "target": target,
                        "interaction": eclass,
                        "label": elabel
                    }
                })

    # Now experiments
    experiments = {}
    
    # OSD-8
    def parse_osd8():
        path = ROOT / "results" / "osd8" / "record.json"
        if not path.exists(): return {}
        rec = json.loads(path.read_text())
        primary = rec["primary_group"]
        out = {}
        for m in rec.get("maps", {}).values():
            for n in m.get("nodes", []):
                v = n.get("by_group", {}).get(primary)
                if v is not None:
                    out[n["node_id"]] = v
        return out
        
    # OSD-27
    def parse_osd27():
        path = ROOT / "results" / "osd27" / "record.json"
        if not path.exists(): return {}
        rec = json.loads(path.read_text())
        out = {}
        for m in rec.get("maps", {}).values():
            for n in m.get("consistency", []):
                v = n.get("mean_log2fc")
                if v is not None:
                    out[n["node_id"]] = v
        return out

    # Figures (Papers, OSD-782)
    def parse_figures_struct(path):
        if not path.exists(): return {}
        rec = json.loads(path.read_text())
        best = {}
        for fig in rec.get("figures", []):
            for n in fig.get("per_node", []):
                v = n.get("peak")
                if v is None:
                    v = n.get("value")
                if v is not None:
                    nid = n["node_id"]
                    cur = best.get(nid)
                    if cur is None or abs(v) > abs(cur):
                        best[nid] = v
        return best

    experiments["OSD-8"] = parse_osd8()
    experiments["OSD-27"] = parse_osd27()
    experiments["OSD-782"] = parse_figures_struct(ROOT / "results" / "osd782" / "record.json")
    experiments["Parmagnani 2022"] = parse_figures_struct(ROOT / "results" / "papers" / "Parmagnani2022" / "record.json")
    experiments["Agliassa 2018"] = parse_figures_struct(ROOT / "results" / "papers" / "Agliassa2018a" / "record.json")
    experiments["Mannino 2026"] = parse_figures_struct(ROOT / "results" / "papers" / "Mannino2026" / "record.json")

    out_data = {
        "elements": {
            "nodes": nodes_out,
            "edges": edges_out
        },
        "experiments": experiments
    }
    
    OUT_FILE.write_text(json.dumps(out_data, indent=2))
    print(f"Wrote {OUT_FILE}")

if __name__ == "__main__":
    main()
