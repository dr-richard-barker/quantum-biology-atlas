#!/usr/bin/env python3
import pathlib
import sys
import json

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from build_site import e, head, tail

DOCS = ROOT / "docs"
ASSETS = DOCS / "assets"
GRAPH_DATA = ASSETS / "qb-graph-data.json"

def build_kg():
    out = [head(
        "Interactive Knowledge Graph",
        "View and overlay collective experimental effects across the QB ontology.",
    )]
    
    out.append("""<style>
  #cy {
    width: 100%;
    height: 700px;
    border: 1px solid var(--qba-rule);
    border-radius: 12px;
    background: var(--qba-card);
    margin-top: 20px;
  }
  .controls {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    margin: 20px 0;
  }
  .controls button {
    border: 1px solid var(--qba-rule);
    background: var(--qba-bg);
    color: var(--qba-ink);
    border-radius: 9px;
    padding: 7px 12px;
    cursor: pointer;
    font-size: .85rem;
  }
  .controls button.active {
    background: var(--qba-accent);
    color: #fff;
    border-color: var(--qba-accent);
  }
  .tooltip {
    position: absolute;
    background: var(--qba-bg);
    border: 1px solid var(--qba-rule);
    padding: 8px;
    border-radius: 6px;
    box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    font-size: 0.85rem;
    pointer-events: none;
    z-index: 100;
    display: none;
  }
</style>""")

    out.append("""<header class="hero">
<h1>Interactive Knowledge Graph</h1>
<p class="lede">Explore the QB ontology as a graph and overlay data from all experiments.</p>
</header>
<div class="controls" id="exp-toggles"></div>
<div id="cy"></div>
<div id="tooltip" class="tooltip"></div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/cytoscape/3.26.0/cytoscape.min.js"></script>
<script>
  let cy;
  let graphData = null;
  let activeExps = new Set();

  fetch('assets/qb-graph-data.json').then(r => r.json()).then(data => {
    graphData = data;
    initGraph();
    initControls();
  });

  function initControls() {
    const container = document.getElementById('exp-toggles');
    for (const exp of Object.keys(graphData.experiments)) {
      const btn = document.createElement('button');
      btn.textContent = exp;
      btn.onclick = () => {
        if (activeExps.has(exp)) {
          activeExps.delete(exp);
          btn.classList.remove('active');
        } else {
          activeExps.add(exp);
          btn.classList.add('active');
        }
        updateNodeColors();
      };
      container.appendChild(btn);
    }
  }
  
  function getColor(val) {
      if (val === undefined || val === null) return '#ccc';
      if (val > 0) return '#D55E00'; // Vermillion (Upregulated)
      if (val < 0) return '#0072B2'; // Blue (Downregulated)
      return '#f0f0f0';
  }

  function updateNodeColors() {
    cy.nodes().forEach(node => {
      const nid = node.id();
      let vals = [];
      for (const exp of activeExps) {
        let v = graphData.experiments[exp][nid];
        if (typeof v === 'object' && v !== null) {
          v = v.log2fc || v.mean_log2fc;
        }
        if (v !== undefined && v !== null) {
          vals.push(v);
        }
      }
      
      let avg = null;
      if (vals.length > 0) {
        avg = vals.reduce((a, b) => a + b, 0) / vals.length;
      }
      
      let color = (avg !== null) ? getColor(avg) : '#ccc';
      node.style('background-color', color);
      node.data('avg_log2fc', avg);
    });
  }

  function initGraph() {
    cy = cytoscape({
      container: document.getElementById('cy'),
      elements: graphData.elements,
      style: [
        {
          selector: 'node',
          style: {
            'label': 'data(label)',
            'background-color': '#ccc',
            'border-width': 2,
            'border-style': 'solid',
            'border-color': ele => ele.data('evidence_tier') === 'T1' ? '#1a2230' : (ele.data('evidence_tier') === 'T2' ? '#5a6473' : '#8892a3'),
            'font-size': '10px',
            'text-valign': 'bottom',
            'text-margin-y': 5
          }
        },
        {
          selector: 'edge',
          style: {
            'width': 1.5,
            'line-color': '#e5e9f0',
            'target-arrow-color': '#e5e9f0',
            'target-arrow-shape': 'triangle',
            'curve-style': 'bezier',
            'label': 'data(label)',
            'font-size': '8px',
            'color': '#8892a3',
            'text-rotation': 'autorotate'
          }
        }
      ],
      layout: {
        name: 'cose',
        padding: 50,
        nodeRepulsion: 8000,
        idealEdgeLength: 100,
        edgeElasticity: 0.45,
        nestingFactor: 0.1,
        gravity: 0.25,
        numIter: 2500,
      }
    });

    cy.on('mouseover', 'node', function(e) {
      const node = e.target;
      const tooltip = document.getElementById('tooltip');
      const val = node.data('avg_log2fc');
      tooltip.innerHTML = `<strong>${node.data('label')}</strong><br/>
                           Evidence: ${node.data('evidence_tier')}<br/>
                           Avg Log2FC: ${val !== null ? val.toFixed(2) : 'N/A'}`;
      tooltip.style.display = 'block';
    });

    cy.on('mousemove', function(e) {
      const tooltip = document.getElementById('tooltip');
      if(tooltip.style.display === 'block') {
        tooltip.style.left = (e.originalEvent.pageX + 10) + 'px';
        tooltip.style.top = (e.originalEvent.pageY + 10) + 'px';
      }
    });

    cy.on('mouseout', 'node', function(e) {
      document.getElementById('tooltip').style.display = 'none';
    });
  }
</script>
""")
    out.append(tail())
    return "\n".join(out)


def build_heatmap():
    out = [head(
        "Collective Heatmap",
        "A dense summary of all experimental data across all ontology entities.",
    )]
    out.append("""<style>
  .heatmap-container {
    overflow-x: auto;
    margin-top: 20px;
    border: 1px solid var(--qba-rule);
    border-radius: 8px;
    background: var(--qba-bg);
  }
  table.heatmap {
    border-collapse: collapse;
    width: 100%;
    font-size: 0.85rem;
    color: var(--qba-ink);
  }
  table.heatmap th, table.heatmap td {
    padding: 6px 10px;
    text-align: left;
    border-bottom: 1px solid var(--qba-rule);
  }
  table.heatmap th {
    background: var(--qba-card);
    font-weight: 700;
    position: sticky;
    top: 0;
    z-index: 2;
  }
  table.heatmap th:first-child {
    left: 0;
    z-index: 3;
    min-width: 200px;
  }
  table.heatmap td:first-child {
    background: var(--qba-card);
    font-weight: 600;
    position: sticky;
    left: 0;
    z-index: 1;
    border-right: 1px solid var(--qba-rule);
  }
  .cell {
    text-align: center;
    font-weight: 600;
    color: #fff;
    text-shadow: 0px 0px 2px rgba(0,0,0,0.5);
  }
  .controls { margin-bottom: 15px; }
  select { padding: 5px 10px; border-radius: 5px; }
</style>""")
    
    out.append("""<header class="hero">
<h1>Collective Heatmap</h1>
<p class="lede">A consolidated view of all experiments across all entities.</p>
</header>
<div class="controls">
  <label for="sort">Sort by:</label>
  <select id="sort" onchange="renderHeatmap()">
    <option value="name">Entity Name</option>
    <option value="mean_abs">Mean Absolute Response</option>
  </select>
</div>
<div class="heatmap-container" id="heatmap-wrapper"></div>

<script>
  let graphData = null;

  fetch('assets/qb-graph-data.json').then(r => r.json()).then(data => {
    graphData = data;
    renderHeatmap();
  });
  
  function getHexColor(val) {
      if (val === undefined || val === null) return 'transparent';
      const max = 2.0; 
      let intensity = Math.min(Math.abs(val) / max, 1.0);
      
      // Interpolate to red (#D55E00 = 213,94,0) or blue (#0072B2 = 0,114,178)
      if (val > 0) {
          let r = Math.round(255 - (255 - 213) * intensity);
          let g = Math.round(255 - (255 - 94) * intensity);
          let b = Math.round(255 - (255 - 0) * intensity);
          return `rgb(${r},${g},${b})`;
      } else {
          let r = Math.round(255 - (255 - 0) * intensity);
          let g = Math.round(255 - (255 - 114) * intensity);
          let b = Math.round(255 - (255 - 178) * intensity);
          return `rgb(${r},${g},${b})`;
      }
  }

  function renderHeatmap() {
    const experiments = Object.keys(graphData.experiments);
    let nodes = graphData.elements.nodes.map(n => {
       let vals = [];
       experiments.forEach(e => {
         let v = graphData.experiments[e][n.data.id];
         if (typeof v === 'object' && v !== null) v = v.log2fc || v.mean_log2fc;
         vals.push(v);
       });
       let validVals = vals.filter(v => v !== undefined && v !== null);
       let meanAbs = validVals.length ? validVals.reduce((a,b) => a + Math.abs(b), 0) / validVals.length : 0;
       return { id: n.data.id, label: n.data.label, vals: vals, meanAbs: meanAbs };
    });
    
    // sorting
    const sortMode = document.getElementById('sort').value;
    if (sortMode === 'mean_abs') {
      nodes.sort((a,b) => b.meanAbs - a.meanAbs);
    } else {
      nodes.sort((a,b) => a.label.localeCompare(b.label));
    }
    
    let html = `<table class="heatmap"><thead><tr><th>Entity</th>`;
    experiments.forEach(e => html += `<th>${e}</th>`);
    html += `</tr></thead><tbody>`;
    
    nodes.forEach(n => {
      html += `<tr><td>${n.label}</td>`;
      n.vals.forEach(v => {
        let color = getHexColor(v);
        let text = (v !== undefined && v !== null) ? v.toFixed(2) : '-';
        let style = color !== 'transparent' ? `background-color: ${color}; color: ${(Math.abs(v)>0.8)?'#fff':'#333'}; text-shadow: none;` : `color: #aaa;`;
        html += `<td class="cell" style="${style}">${text}</td>`;
      });
      html += `</tr>`;
    });
    html += `</tbody></table>`;
    
    document.getElementById('heatmap-wrapper').innerHTML = html;
  }
</script>
""")
    out.append(tail())
    return "\n".join(out)


def main():
    path_kg = DOCS / "knowledge_graph.html"
    path_kg.write_text(build_kg(), encoding="utf-8")
    print(f"wrote {path_kg.relative_to(ROOT)}")
    
    path_hm = DOCS / "heatmap.html"
    path_hm.write_text(build_heatmap(), encoding="utf-8")
    print(f"wrote {path_hm.relative_to(ROOT)}")

if __name__ == "__main__":
    main()
