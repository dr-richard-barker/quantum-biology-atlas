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
        "Interactive Knowledge Graph — Quantum Biology Atlas",
        "Interactive network of 83 quantum-annotated entities across 7 subcellular compartments, with mathematical clustering, circular and CoSE layouts, and experimental data overlays.",
    )]
    
    out.append("""<style>
  .kg-container {
    display: flex;
    flex-direction: column;
    gap: 16px;
    margin-top: 15px;
  }
  .panel-box {
    border: 1px solid var(--qba-rule);
    border-radius: 12px;
    background: var(--qba-card);
    padding: 14px 18px;
  }
  .panel-box h3 {
    margin: 0 0 10px;
    font-size: 0.88rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--qba-soft);
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .btn-group {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
  }
  .btn-group button {
    border: 1px solid var(--qba-rule);
    background: var(--qba-bg);
    color: var(--qba-ink);
    border-radius: 8px;
    padding: 7px 13px;
    cursor: pointer;
    font-size: 0.85rem;
    font-weight: 500;
    transition: all 0.15s ease;
    display: inline-flex;
    align-items: center;
    gap: 5px;
  }
  .btn-group button:hover {
    border-color: var(--qba-accent);
    color: var(--qba-accent);
    background: var(--qba-card2);
  }
  .btn-group button.active {
    background: var(--qba-accent);
    color: #fff;
    border-color: var(--qba-accent);
    font-weight: 600;
    box-shadow: 0 2px 4px rgba(59,110,165,0.25);
  }
  .btn-group button.accent-btn {
    border-color: var(--qba-accent2);
  }
  .btn-group button.clear-btn {
    color: var(--qba-soft);
    border-style: dashed;
  }
  .btn-group button.clear-btn:hover {
    color: var(--qba-warn);
    border-color: var(--qba-warn);
  }
  .algo-banner {
    border-left: 3px solid var(--qba-accent);
    background: var(--qba-card2);
    border-radius: 0 8px 8px 0;
    padding: 10px 14px;
    font-size: 0.88rem;
    color: var(--qba-ink);
    line-height: 1.45;
  }
  .canvas-wrapper {
    position: relative;
    border: 1px solid var(--qba-rule);
    border-radius: 12px;
    overflow: hidden;
    background: var(--qba-bg);
  }
  .canvas-toolbar {
    position: absolute;
    top: 12px;
    left: 12px;
    right: 12px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 10px;
    z-index: 10;
    pointer-events: none;
  }
  .toolbar-left, .toolbar-right {
    display: flex;
    gap: 8px;
    align-items: center;
    pointer-events: auto;
  }
  .search-input {
    font: inherit;
    font-size: 0.85rem;
    padding: 6px 12px;
    border: 1px solid var(--qba-rule);
    border-radius: 8px;
    background: var(--qba-bg);
    color: var(--qba-ink);
    width: 220px;
    box-shadow: 0 2px 6px rgba(0,0,0,0.06);
    outline: none;
  }
  .search-input:focus {
    border-color: var(--qba-accent);
    box-shadow: 0 0 0 2px rgba(59,110,165,0.2);
  }
  .tool-btn {
    border: 1px solid var(--qba-rule);
    background: var(--qba-bg);
    color: var(--qba-ink);
    border-radius: 8px;
    padding: 6px 10px;
    font-size: 0.82rem;
    cursor: pointer;
    box-shadow: 0 2px 4px rgba(0,0,0,0.05);
  }
  .tool-btn:hover {
    border-color: var(--qba-accent);
    color: var(--qba-accent);
  }
  #cy {
    width: 100%;
    height: 750px;
    display: block;
  }
  .legend-box {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 10px 16px;
    background: var(--qba-card);
    border-top: 1px solid var(--qba-rule);
    font-size: 0.82rem;
  }
  .legend-group {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 14px;
  }
  .legend-item {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    color: var(--qba-soft);
  }
  .tier-pill {
    display: inline-block;
    width: 22px;
    height: 10px;
    background: #cbd5e1;
    border-radius: 2px;
  }
  .tier-t1 { border: 2.5px solid #1a2230; }
  .tier-t2 { border: 1.5px solid #475569; }
  .tier-t3 { border: 1.5px dashed #64748b; }
  .tier-t4 { border: 1px dotted #94a3b8; }
  .color-bar {
    display: inline-flex;
    height: 10px;
    width: 90px;
    border-radius: 3px;
    background: linear-gradient(to right, #0072B2, #ffffff, #D55E00);
    border: 1px solid var(--qba-rule);
  }
  .tooltip {
    position: absolute;
    background: var(--qba-bg);
    border: 1px solid var(--qba-rule);
    padding: 12px 14px;
    border-radius: 9px;
    box-shadow: 0 8px 20px rgba(0,0,0,0.15);
    font-size: 0.84rem;
    pointer-events: none;
    z-index: 1000;
    display: none;
    max-width: 320px;
    line-height: 1.4;
  }
  .tooltip strong {
    font-size: 0.95rem;
    color: var(--qba-ink);
  }
  .badge {
    display: inline-block;
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 0.72rem;
    font-weight: 600;
    margin-right: 4px;
    margin-top: 4px;
  }
  .badge-tier { background: var(--qba-card2); border: 1px solid var(--qba-rule); }
  .badge-chem { background: rgba(59,110,165,0.12); color: var(--qba-accent); }
  .exp-table {
    width: 100%;
    margin-top: 8px;
    border-collapse: collapse;
    font-size: 0.78rem;
  }
  .exp-table td {
    padding: 3px 0;
    border-top: 1px solid var(--qba-rule);
  }
  .val-up { color: #D55E00; font-weight: 600; text-align: right; }
  .val-down { color: #0072B2; font-weight: 600; text-align: right; }
  .val-none { color: var(--qba-soft); text-align: right; }
</style>""")

    out.append("""<header class="hero">
<h1>Interactive Knowledge Graph</h1>
<p class="lede">Explore the Quantum Biology Ontology as an interconnected network of <strong>83 entities</strong> across <strong>7 subcellular compartments</strong> connected by <strong>154 biochemical edges</strong>. Project differential expression data across multiple experimental studies, or partition the topology using mathematical clustering algorithms.</p>
</header>

<div class="kg-container">
  <!-- Layout & Clustering Controls -->
  <div class="panel-box">
    <h3>Layout &amp; Mathematical Clustering</h3>
    <div class="btn-group" id="layout-toggles">
      <button class="active" data-layout="subcellular">Subcellular Localisation (Default)</button>
      <button data-layout="cose">CoSE (Force-Directed)</button>
      <button data-layout="circular">Circular</button>
      <button data-layout="concentric">Concentric (Centrality)</button>
      <button data-layout="mcl">Markov Clustering (MCL)</button>
      <button data-layout="kmeans">K-Means (Topological)</button>
      <button data-layout="breadthfirst">Hierarchical (BFS)</button>
    </div>
  </div>

  <!-- Experimental Data Controls -->
  <div class="panel-box">
    <h3>Experimental Data Overlays</h3>
    <div class="btn-group" id="exp-toggles"></div>
  </div>

  <!-- Dynamic Algorithm Info Banner -->
  <div class="algo-banner" id="layout-info">
    <strong>Subcellular Localisation (Default):</strong> Grouping 83 entities into 7 biological compartments (Mitochondria, Chloroplast, Nucleus, Cytosol, Peroxisome, Plasma Membrane &amp; Cell, Environment) using compound physics relaxation.
  </div>

  <!-- Canvas Stage -->
  <div class="canvas-wrapper">
    <div class="canvas-toolbar">
      <div class="toolbar-left">
        <input type="text" class="search-input" id="search-input" placeholder="Search entity (e.g. AOX, CRY1, CSD)..." autocomplete="off">
      </div>
      <div class="toolbar-right">
        <button class="tool-btn" id="btn-zoom-in" title="Zoom In">+ Zoom In</button>
        <button class="tool-btn" id="btn-zoom-out" title="Zoom Out">- Zoom Out</button>
        <button class="tool-btn" id="btn-fit" title="Fit to View">Fit View</button>
      </div>
    </div>
    <div id="cy"></div>
    <div class="legend-box">
      <div class="legend-group">
        <span style="font-weight:600; color:var(--qba-ink);">Evidence Tier:</span>
        <span class="legend-item"><span class="tier-pill tier-t1"></span> T1 Demonstrated</span>
        <span class="legend-item"><span class="tier-pill tier-t2"></span> T2 Inferred</span>
        <span class="legend-item"><span class="tier-pill tier-t3"></span> T3 Plausible</span>
        <span class="legend-item"><span class="tier-pill tier-t4"></span> T4 Context</span>
      </div>
      <div class="legend-group">
        <span style="font-weight:600; color:var(--qba-ink);">Expression Response:</span>
        <span class="legend-item"><span class="color-bar"></span></span>
        <span class="legend-item" style="color:#0072B2; font-weight:600;">Down (&le; -2.0)</span>
        <span class="legend-item" style="color:var(--qba-soft);">Neutral</span>
        <span class="legend-item" style="color:#D55E00; font-weight:600;">Up (&ge; +2.0)</span>
      </div>
    </div>
  </div>
</div>

<div id="tooltip" class="tooltip"></div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/cytoscape/3.26.0/cytoscape.min.js"></script>
<script>
  let cy = null;
  let graphData = null;
  let activeExps = new Set();
  let currentLayoutName = 'subcellular';

  fetch('assets/qb-graph-data.json').then(r => r.json()).then(data => {
    graphData = data;
    initControls();
    initGraph();
  });

  function initControls() {
    // Experiment buttons
    const expContainer = document.getElementById('exp-toggles');
    for (const exp of Object.keys(graphData.experiments)) {
      const btn = document.createElement('button');
      btn.textContent = exp;
      btn.dataset.exp = exp;
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
      expContainer.appendChild(btn);
    }
    
    // Clear button
    const clearBtn = document.createElement('button');
    clearBtn.className = 'clear-btn';
    clearBtn.textContent = 'Clear Overlays';
    clearBtn.onclick = () => {
      activeExps.clear();
      expContainer.querySelectorAll('button').forEach(b => b.classList.remove('active'));
      updateNodeColors();
    };
    expContainer.appendChild(clearBtn);

    // Layout toggles
    document.querySelectorAll('#layout-toggles button').forEach(btn => {
      btn.onclick = () => {
        const layout = btn.dataset.layout;
        setLayout(layout);
      };
    });

    // Toolbar buttons
    document.getElementById('btn-zoom-in').onclick = () => {
      if (cy) cy.zoom({ level: cy.zoom() * 1.25, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } });
    };
    document.getElementById('btn-zoom-out').onclick = () => {
      if (cy) cy.zoom({ level: cy.zoom() * 0.8, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } });
    };
    document.getElementById('btn-fit').onclick = () => {
      if (cy) cy.animate({ fit: { padding: 40 }, duration: 400 });
    };

    // Search input
    const searchInput = document.getElementById('search-input');
    searchInput.oninput = (e) => {
      const q = e.target.value.trim().toLowerCase();
      if (!cy) return;
      if (!q) {
        cy.elements().removeClass('highlighted dimmed');
        return;
      }
      cy.batch(() => {
        const matches = cy.nodes('[!is_compartment]').filter(n => {
          const lbl = (n.data('label') || '').toLowerCase();
          const id = (n.data('id') || '').toLowerCase();
          const comp = (n.data('compartment_name') || '').toLowerCase();
          const org = (n.data('organelle') || '').toLowerCase();
          return lbl.includes(q) || id.includes(q) || comp.includes(q) || org.includes(q);
        });
        if (matches.length > 0) {
          cy.elements().addClass('dimmed');
          matches.removeClass('dimmed').addClass('highlighted');
          matches.connectedEdges().removeClass('dimmed');
        } else {
          cy.elements().removeClass('highlighted dimmed');
        }
      });
    };
  }

  function getExpressionColor(val) {
    if (val === undefined || val === null) return '#e2e8f0';
    const max = 2.0;
    const clamped = Math.max(-max, Math.min(max, val));
    const intensity = Math.abs(clamped) / max;
    
    // Vermillion #D55E00 (213, 94, 0)
    // Blue #0072B2 (0, 114, 178)
    if (val > 0) {
      const r = Math.round(255 - (255 - 213) * intensity);
      const g = Math.round(255 - (255 - 94) * intensity);
      const b = Math.round(255 - (255 - 0) * intensity);
      return `rgb(${r},${g},${b})`;
    } else {
      const r = Math.round(255 - (255 - 0) * intensity);
      const g = Math.round(255 - (255 - 114) * intensity);
      const b = Math.round(255 - (255 - 178) * intensity);
      return `rgb(${r},${g},${b})`;
    }
  }

  function updateNodeColors() {
    if (!cy) return;
    cy.batch(() => {
      cy.nodes('[!is_compartment]').forEach(node => {
        const nid = node.id();
        let vals = [];
        for (const exp of activeExps) {
          let v = graphData.experiments[exp] ? graphData.experiments[exp][nid] : undefined;
          if (typeof v === 'object' && v !== null) {
            v = v.log2fc !== undefined ? v.log2fc : v.mean_log2fc;
          }
          if (v !== undefined && v !== null) {
            vals.push(v);
          }
        }

        let avg = null;
        if (vals.length > 0) {
          avg = vals.reduce((a, b) => a + b, 0) / vals.length;
        }
        node.data('avg_log2fc', avg);

        if (activeExps.size > 0) {
          node.style('background-color', getExpressionColor(avg));
          node.style('color', (avg !== null && Math.abs(avg) >= 0.8) ? '#ffffff' : 'var(--qba-ink, #1a2230)');
        } else if (currentLayoutName === 'mcl' && node.data('mcl_color')) {
          node.style('background-color', node.data('mcl_color'));
          node.style('color', '#ffffff');
        } else if (currentLayoutName === 'kmeans' && node.data('kmeans_color')) {
          node.style('background-color', node.data('kmeans_color'));
          node.style('color', '#ffffff');
        } else {
          node.style('background-color', '#e2e8f0');
          node.style('color', 'var(--qba-ink, #1a2230)');
        }
      });
    });
  }

  function initGraph() {
    cy = cytoscape({
      container: document.getElementById('cy'),
      elements: graphData.elements,
      style: [
        // Parent compound nodes (compartments)
        {
          selector: ':parent',
          style: {
            'background-color': '#f8fafc',
            'background-opacity': 0.65,
            'border-width': 1.5,
            'border-style': 'dashed',
            'border-color': '#3B6EA5',
            'border-opacity': 0.8,
            'border-radius': 12,
            'label': 'data(label)',
            'font-size': '12px',
            'font-weight': 'bold',
            'color': '#3B6EA5',
            'text-valign': 'top',
            'text-halign': 'center',
            'text-margin-y': 10,
            'padding': '26px'
          }
        },
        // Entity child nodes
        {
          selector: 'node[!is_compartment]',
          style: {
            'label': 'data(label)',
            'width': 36,
            'height': 36,
            'background-color': '#e2e8f0',
            'border-width': ele => {
              const t = ele.data('evidence_tier');
              return t === 'T1' ? 3.5 : (t === 'T2' ? 2.5 : (t === 'T3' ? 2.0 : 1.0));
            },
            'border-style': ele => {
              const t = ele.data('evidence_tier');
              return t === 'T3' ? 'dashed' : (t === 'T4' ? 'dotted' : 'solid');
            },
            'border-color': ele => {
              const t = ele.data('evidence_tier');
              return t === 'T1' ? '#1a2230' : (t === 'T2' ? '#475569' : (t === 'T3' ? '#64748b' : '#94a3b8'));
            },
            'font-size': '9.5px',
            'font-weight': '500',
            'color': '#1a2230',
            'text-valign': 'bottom',
            'text-margin-y': 6,
            'text-wrap': 'ellipsis',
            'text-max-width': '95px'
          }
        },
        // Shapes based on kind
        {
          selector: 'node[kind = "complex"]',
          style: { 'shape': 'round-rectangle' }
        },
        {
          selector: 'node[kind = "simple_chemical"]',
          style: { 'shape': 'diamond' }
        },
        {
          selector: 'node[kind = "macromolecule"]',
          style: { 'shape': 'ellipse' }
        },
        {
          selector: 'node[kind = "phenotype"], node[kind = "biological_process"]',
          style: { 'shape': 'hexagon' }
        },
        // Edges
        {
          selector: 'edge',
          style: {
            'width': 1.6,
            'line-color': '#cbd5e1',
            'target-arrow-color': '#94a3b8',
            'target-arrow-shape': ele => {
              const i = ele.data('interaction');
              if (i === 'inhibition') return 'tee';
              if (i === 'catalysis') return 'circle';
              return 'triangle';
            },
            'curve-style': 'bezier',
            'opacity': 0.7,
            'label': 'data(label)',
            'font-size': '8px',
            'color': '#64748b',
            'text-rotation': 'autorotate'
          }
        },
        // Highlights & dimming
        {
          selector: 'node.highlighted',
          style: {
            'border-color': '#3B6EA5',
            'border-width': 3.5,
            'shadow-blur': 12,
            'shadow-color': '#3B6EA5',
            'shadow-opacity': 0.8,
            'z-index': 999
          }
        },
        {
          selector: 'edge.highlighted',
          style: {
            'width': 3.0,
            'line-color': '#3B6EA5',
            'target-arrow-color': '#3B6EA5',
            'opacity': 1.0,
            'z-index': 998
          }
        },
        {
          selector: '.dimmed',
          style: {
            'opacity': 0.15
          }
        }
      ],
      layout: {
        name: 'preset'
      }
    });

    // Tooltip handling
    const tooltip = document.getElementById('tooltip');

    cy.on('mouseover', 'node[!is_compartment]', function(e) {
      const node = e.target;
      const data = node.data();
      const avg = data.avg_log2fc;
      
      let expRows = '';
      if (activeExps.size > 0) {
        expRows += '<table class="exp-table"><tbody>';
        for (const exp of activeExps) {
          let v = graphData.experiments[exp] ? graphData.experiments[exp][node.id()] : undefined;
          if (typeof v === 'object' && v !== null) {
            v = v.log2fc !== undefined ? v.log2fc : v.mean_log2fc;
          }
          let cls = 'val-none';
          let txt = 'No data';
          if (v !== undefined && v !== null) {
            cls = v > 0 ? 'val-up' : (v < 0 ? 'val-down' : 'val-none');
            txt = (v > 0 ? '+' : '') + v.toFixed(2) + ' log₂FC';
          }
          expRows += `<tr><td>${exp}:</td><td class="${cls}">${txt}</td></tr>`;
        }
        expRows += '</tbody></table>';
      }

      const qClasses = (data.quantum_class || []).map(c => `<span class="badge badge-chem">${c.replace(/_/g, ' ')}</span>`).join('');
      const addressableBadge = data.is_magnetically_addressable ? '<span class="badge badge-chem" style="background:rgba(213,94,0,0.12); color:#D55E00;">Magnetically Addressable</span>' : '';

      tooltip.innerHTML = `
        <strong>${data.label}</strong> <span style="font-size:0.75rem; color:var(--qba-soft);">(${data.id})</span><br/>
        <div style="margin:4px 0;">
          <span class="badge badge-tier">${data.evidence_tier} (${data.evidence_tier === 'T1' ? 'Demonstrated' : (data.evidence_tier === 'T2' ? 'Inferred' : (data.evidence_tier === 'T3' ? 'Plausible' : 'Context'))})</span>
          <span class="badge badge-tier">${data.organelle || data.compartment_name}</span>
          ${addressableBadge}
        </div>
        ${qClasses ? `<div style="margin-top:2px;">${qClasses}</div>` : ''}
        ${data.description ? `<p style="margin:6px 0 0; font-size:0.8rem; color:var(--qba-soft);">${data.description}</p>` : ''}
        ${avg !== null ? `<div style="margin-top:6px; font-weight:600;">Average Selected Effect: <span class="${avg > 0 ? 'val-up' : (avg < 0 ? 'val-down' : '')}">${(avg > 0 ? '+' : '') + avg.toFixed(2)} log₂FC</span></div>` : ''}
        ${expRows}
      `;
      tooltip.style.display = 'block';
    });

    cy.on('mousemove', function(e) {
      if (tooltip.style.display === 'block') {
        const x = e.originalEvent.pageX + 14;
        const y = e.originalEvent.pageY + 14;
        tooltip.style.left = x + 'px';
        tooltip.style.top = y + 'px';
      }
    });

    cy.on('mouseout', 'node', function(e) {
      tooltip.style.display = 'none';
    });

    // Node click to highlight neighborhood
    cy.on('tap', 'node[!is_compartment]', function(e) {
      const node = e.target;
      cy.batch(() => {
        cy.elements().removeClass('highlighted dimmed');
        const neighborhood = node.neighborhood().add(node);
        cy.elements().difference(neighborhood).addClass('dimmed');
        neighborhood.addClass('highlighted');
      });
    });

    // Background tap to reset highlight
    cy.on('tap', function(e) {
      if (e.target === cy) {
        cy.elements().removeClass('highlighted dimmed');
        const searchInput = document.getElementById('search-input');
        if (searchInput) searchInput.value = '';
      }
    });

    // Initial Layout: Subcellular Localisation (DEFAULT)
    setLayout('subcellular');
  }

  function unparentNodes() {
    cy.batch(() => {
      cy.nodes('[!is_compartment]').forEach(n => {
        n.move({ parent: null });
      });
      cy.nodes('[?is_compartment]').style('display', 'none');
    });
  }

  function setLayout(name) {
    currentLayoutName = name;
    
    // Update button active states
    document.querySelectorAll('#layout-toggles button').forEach(b => {
      b.classList.toggle('active', b.dataset.layout === name);
    });
    
    const infoEl = document.getElementById('layout-info');
    cy.elements().removeClass('highlighted dimmed');

    if (name === 'subcellular') {
      infoEl.innerHTML = '<strong>Subcellular Localisation (Default):</strong> Grouping 83 entities into 7 biological compartments (Mitochondria, Chloroplast, Nucleus, Cytosol, Peroxisome, Plasma Membrane &amp; Cell, Environment) inside compound boundaries using physics-based relaxation.';
      
      // 1. Show compound containers
      cy.nodes('[?is_compartment]').style('display', 'element');

      // 2. Re-parent children
      cy.batch(() => {
        cy.nodes('[!is_compartment]').forEach(n => {
          n.move({ parent: n.data('default_parent') });
        });
      });

      // 3. Set anatomical coordinates for compartment centroids
      const compPositions = {
        'comp_chloroplast': { x: -400, y: -280 },
        'comp_mitochondria': { x: 400, y: -280 },
        'comp_cytosol': { x: 0, y: -50 },
        'comp_nucleus': { x: -400, y: 220 },
        'comp_peroxisome': { x: 400, y: 220 },
        'comp_plasma_membrane': { x: 0, y: 380 },
        'comp_environment': { x: 0, y: -500 }
      };

      cy.nodes('[!is_compartment]').forEach(n => {
        const p = n.data('default_parent');
        const pos = compPositions[p] || { x: 0, y: 0 };
        const jitterX = (Math.random() - 0.5) * 160;
        const jitterY = (Math.random() - 0.5) * 160;
        n.position({ x: pos.x + jitterX, y: pos.y + jitterY });
      });

      // 4. Run compound cose layout with gentle bounds
      cy.layout({
        name: 'cose',
        animate: true,
        animationDuration: 800,
        fit: true,
        padding: 40,
        randomize: false,
        componentSpacing: 80,
        nodeRepulsion: 15000,
        idealEdgeLength: 85,
        edgeElasticity: 0.45,
        nestingFactor: 0.15,
        gravity: 0.25,
        numIter: 1600
      }).run();

      updateNodeColors();
      return;
    }

    // Unparent for flat layouts
    unparentNodes();

    if (name === 'cose') {
      infoEl.innerHTML = '<strong>Compound Spring Embedder (CoSE):</strong> Unconstrained force-directed physics simulation based on spring tension and electrical repulsion across the entire network.';
      cy.layout({
        name: 'cose',
        animate: true,
        animationDuration: 800,
        fit: true,
        padding: 40,
        randomize: true,
        componentSpacing: 60,
        nodeRepulsion: 12000,
        idealEdgeLength: 90,
        edgeElasticity: 0.45,
        nestingFactor: 0.1,
        gravity: 0.25,
        numIter: 2000
      }).run();
    } else if (name === 'circular') {
      infoEl.innerHTML = '<strong>Circular Layout:</strong> All 83 entities mapped along a single radial orbit ordered by subcellular compartment, emphasizing cross-network regulatory edges.';
      cy.layout({
        name: 'circle',
        animate: true,
        animationDuration: 600,
        fit: true,
        padding: 50,
        avoidOverlap: true,
        sort: (a, b) => {
          const orgA = a.data('organelle') || '';
          const orgB = b.data('organelle') || '';
          if (orgA !== orgB) return orgA.localeCompare(orgB);
          return a.data('label').localeCompare(b.data('label'));
        }
      }).run();
    } else if (name === 'concentric') {
      infoEl.innerHTML = '<strong>Concentric (Degree Centrality):</strong> Nodes arranged into radial shells based on connectivity degree. Core hubs (e.g. Cryptochrome, Complex I, Superoxide) occupy the inner core.';
      cy.layout({
        name: 'concentric',
        animate: true,
        animationDuration: 600,
        fit: true,
        padding: 50,
        minNodeSpacing: 25,
        concentric: n => n.degree(),
        levelWidth: nodes => 3
      }).run();
    } else if (name === 'mcl') {
      try {
        const clusters = cy.elements('[!is_compartment]').markovClustering({
          attributes: [edge => 1],
          inflateFactor: 2.0,
          expandFactor: 2.0,
          maxIterations: 25
        });
        
        const palette = ['#E69F00', '#56B4E9', '#009E73', '#F0E442', '#0072B2', '#D55E00', '#CC79A7', '#3FB6A8', '#8B5CF6', '#EC4899', '#6366F1'];
        clusters.forEach((clusterNodes, idx) => {
          const col = palette[idx % palette.length];
          clusterNodes.forEach(n => {
            n.data('mcl_cluster', idx);
            n.data('mcl_color', col);
          });
        });
        
        infoEl.innerHTML = `<strong>Markov Clustering (MCL):</strong> Stochastic flow simulation detected <strong>${clusters.length} functional community modules</strong> based on random-walk flow expansion. Modules are spatially clustered and color-tagged.`;
        layoutClusterConstellation(clusters);
      } catch(err) {
        console.error(err);
        infoEl.innerHTML = '<strong>MCL Clustering:</strong> Fallback to topological force layout.';
        cy.layout({ name: 'cose', animate: true, fit: true }).run();
      }
    } else if (name === 'kmeans') {
      try {
        const k = 6;
        const clusters = cy.nodes('[!is_compartment]').kMeans({
          k: k,
          attributes: [
            n => n.degree(),
            n => (n.data('evidence_tier') === 'T1' ? 4 : n.data('evidence_tier') === 'T2' ? 3 : n.data('evidence_tier') === 'T3' ? 2 : 1),
            n => (n.data('is_magnetically_addressable') ? 1 : 0)
          ]
        });
        
        const palette = ['#3B6EA5', '#3FB6A8', '#D55E00', '#009E73', '#CC79A7', '#E69F00'];
        clusters.forEach((clusterNodes, idx) => {
          const col = palette[idx % palette.length];
          clusterNodes.forEach(n => {
            n.data('kmeans_cluster', idx);
            n.data('kmeans_color', col);
          });
        });
        
        infoEl.innerHTML = `<strong>K-Means Clustering:</strong> Topological distance algorithm partitioned network into <strong>${k} mathematical clusters</strong> based on connectivity and evidence tiers.`;
        layoutClusterConstellation(clusters);
      } catch(err) {
        console.error(err);
        infoEl.innerHTML = '<strong>K-Means Clustering:</strong> Fallback to concentric layout.';
        cy.layout({ name: 'concentric', animate: true, fit: true }).run();
      }
    } else if (name === 'breadthfirst') {
      infoEl.innerHTML = '<strong>Hierarchical (Breadth-First):</strong> Directed flow hierarchy tracing regulatory pathways from external magnetic and radiation inputs to metabolic effectors.';
      const roots = cy.nodes('[id = "NNMF_INPUT"], [id = "GMF_REFERENCE"], [id = "PSII"], [id = "CRY1"]');
      cy.layout({
        name: 'breadthfirst',
        animate: true,
        animationDuration: 700,
        fit: true,
        padding: 40,
        directed: true,
        roots: roots.length > 0 ? roots : undefined,
        spacingFactor: 1.5
      }).run();
    }

    updateNodeColors();
  }

  function layoutClusterConstellation(clusters) {
    const K = clusters.length;
    const R = 320;
    clusters.forEach((clusterNodes, cIdx) => {
      const angle = (2 * Math.PI * cIdx) / K;
      const cx = R * Math.cos(angle);
      const cy_pos = R * Math.sin(angle);
      const N = clusterNodes.length;
      const subRadius = Math.max(35, 20 * Math.sqrt(N));
      clusterNodes.forEach((node, nIdx) => {
        const subAngle = (2 * Math.PI * nIdx) / N;
        const x = cx + subRadius * Math.cos(subAngle);
        const y = cy_pos + subRadius * Math.sin(subAngle);
        node.position({ x, y });
      });
    });
    cy.animate({ fit: { padding: 50 }, duration: 600 });
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
