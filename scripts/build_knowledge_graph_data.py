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

ORGANELLE_MAP = {
    "mitochondrial_matrix": ("comp_mitochondria", "Mitochondria"),
    "mitochondrial_inner_membrane": ("comp_mitochondria", "Mitochondria"),
    "mitochondrial_intermembrane_space": ("comp_mitochondria", "Mitochondria"),
    "chloroplast_stroma": ("comp_chloroplast", "Chloroplast"),
    "thylakoid_membrane": ("comp_chloroplast", "Chloroplast"),
    "thylakoid_lumen": ("comp_chloroplast", "Chloroplast"),
    "nucleus": ("comp_nucleus", "Nucleus"),
    "cytosol": ("comp_cytosol", "Cytosol"),
    "peroxisome": ("comp_peroxisome", "Peroxisome"),
    "plasma_membrane": ("comp_plasma_membrane", "Plasma Membrane & Cell"),
    "cell": ("comp_plasma_membrane", "Plasma Membrane & Cell"),
    "organism": ("comp_environment", "Whole Organism & Environment"),
    "environment": ("comp_environment", "Whole Organism & Environment"),
}

COMPARTMENT_LABELS = {
    "mitochondrial_matrix": "Mitochondrial Matrix",
    "mitochondrial_inner_membrane": "Mitochondrial Inner Membrane",
    "mitochondrial_intermembrane_space": "Mitochondrial Intermembrane Space",
    "chloroplast_stroma": "Chloroplast Stroma",
    "thylakoid_membrane": "Thylakoid Membrane",
    "thylakoid_lumen": "Thylakoid Lumen",
    "nucleus": "Nucleus",
    "cytosol": "Cytosol",
    "peroxisome": "Peroxisome",
    "plasma_membrane": "Plasma Membrane",
    "cell": "Cellular Context",
    "organism": "Whole Organism Phenotype",
    "environment": "Extracellular / Magnetic Field Environment",
}

def main():
    qbo = ontology.load()
    
    # Calculate counts per organelle
    organelle_counts = {}
    for entity in qbo:
        org_id, org_name = ORGANELLE_MAP.get(entity.compartment, ("comp_cell", "Cellular Context"))
        organelle_counts[org_id] = organelle_counts.get(org_id, 0) + 1

    # Create parent compound nodes
    parent_nodes = []
    seen_orgs = set()
    for entity in qbo:
        org_id, org_name = ORGANELLE_MAP.get(entity.compartment, ("comp_cell", "Cellular Context"))
        if org_id not in seen_orgs:
            seen_orgs.add(org_id)
            parent_nodes.append({
                "data": {
                    "id": org_id,
                    "label": f"{org_name} ({organelle_counts[org_id]})",
                    "is_compartment": True,
                    "organelle_name": org_name,
                    "count": organelle_counts[org_id]
                }
            })

    # Sort parent nodes predictably
    parent_nodes.sort(key=lambda p: p["data"]["label"])

    nodes_out = list(parent_nodes)
    for entity in qbo:
        org_id, org_name = ORGANELLE_MAP.get(entity.compartment, ("comp_cell", "Cellular Context"))
        comp_display = COMPARTMENT_LABELS.get(entity.compartment, entity.compartment or "Unspecified")
        nodes_out.append({
            "data": {
                "id": entity.id.replace("QBO:", ""),
                "label": entity.label,
                "kind": entity.kind,
                "quantum_class": list(entity.quantum_class),
                "evidence_tier": entity.evidence_tier,
                "is_magnetically_addressable": entity.is_magnetically_addressable(qbo.core),
                "compartment": entity.compartment or "",
                "compartment_name": comp_display,
                "organelle": org_name,
                "organelle_id": org_id,
                "parent": org_id,  # Default to subcellular localisation grouping
                "default_parent": org_id,
                "description": entity.description or "",
                "cofactors": list(entity.cofactors) if hasattr(entity, "cofactors") else []
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
