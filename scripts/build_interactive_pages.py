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
        "Interactive network of 83 quantum-annotated entities across 7 subcellular compartments, with mathematical clustering, circular and CoSE layouts, distance scaling, and experimental data overlays.",
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
  .panel-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 10px;
    margin-bottom: 10px;
  }
  .panel-header h3, .panel-box h3 {
    margin: 0;
    font-size: 0.88rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--qba-soft);
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .spacing-controls {
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
  .spacing-label {
    font-size: 0.78rem;
    color: var(--qba-soft);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
  .btn-group {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
  }
  .btn-group button, .tool-btn {
    border: 1px solid var(--qba-rule);
    background: var(--qba-bg);
    color: var(--qba-ink, #0f172a);
    border-radius: 8px;
    padding: 7px 13px;
    cursor: pointer;
    font-size: 0.85rem;
    font-weight: 550;
    transition: all 0.15s ease;
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
  .btn-group button:hover, .tool-btn:hover {
    border-color: var(--qba-accent);
    color: var(--qba-accent);
    background: var(--qba-card2);
  }
  .btn-group button.active {
    background: var(--qba-accent);
    color: #ffffff !important;
    border-color: var(--qba-accent);
    font-weight: 600;
    box-shadow: 0 2px 4px rgba(59,110,165,0.25);
  }
  .btn-group button.spacing-btn, .tool-btn.spacing-btn {
    background: var(--qba-card2);
    border-color: var(--qba-rule);
    font-weight: 600;
  }
  .btn-group button.spacing-btn:hover, .tool-btn.spacing-btn:hover {
    background: var(--qba-accent);
    color: #ffffff;
    border-color: var(--qba-accent);
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
    color: var(--qba-ink, #0f172a);
    line-height: 1.45;
  }
  .canvas-wrapper {
    position: relative;
    border: 1px solid var(--qba-rule);
    border-radius: 12px;
    overflow: hidden;
    background: var(--qba-bg, #ffffff);
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
    background: var(--qba-bg, #ffffff);
    color: var(--qba-ink, #0f172a);
    width: 240px;
    box-shadow: 0 2px 6px rgba(0,0,0,0.06);
    outline: none;
  }
  .search-input:focus {
    border-color: var(--qba-accent);
    box-shadow: 0 0 0 2px rgba(59,110,165,0.2);
  }
  #cy {
    width: 100%;
    height: 760px;
    display: block;
    background: var(--qba-bg, #ffffff);
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
    color: var(--qba-ink, #0f172a);
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
    color: var(--qba-soft, #475569);
  }
  .tier-pill {
    display: inline-block;
    width: 22px;
    height: 10px;
    background: #cbd5e1;
    border-radius: 2px;
  }
  .tier-t1 { border: 2.5px solid #0f172a; }
  .tier-t2 { border: 1.5px solid #334155; }
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
    background: var(--qba-bg, #ffffff);
    border: 1px solid var(--qba-rule);
    padding: 12px 14px;
    border-radius: 9px;
    box-shadow: 0 8px 24px rgba(0,0,0,0.16);
    font-size: 0.84rem;
    color: var(--qba-ink, #0f172a);
    pointer-events: none;
    z-index: 1000;
    display: none;
    max-width: 320px;
    line-height: 1.4;
  }
  .tooltip strong {
    font-size: 0.95rem;
    color: var(--qba-ink, #0f172a);
  }
  .badge {
    display: inline-block;
    padding: 2px 7px;
    border-radius: 4px;
    font-size: 0.72rem;
    font-weight: 600;
    margin-right: 4px;
    margin-top: 4px;
  }
  .badge-tier { background: #f1f5f9; border: 1px solid #cbd5e1; color: #0f172a; }
  .badge-org { background: #e0f2fe; border: 1px solid #bae6fd; color: #0369a1; }
  .badge-chem { background: #fef3c7; border: 1px solid #fde68a; color: #92400e; }
  .badge-mag { background: #ffedd5; border: 1px solid #fed7aa; color: #c2410c; }
  .exp-table {
    width: 100%;
    margin-top: 8px;
    border-collapse: collapse;
    font-size: 0.78rem;
    color: var(--qba-ink, #0f172a);
  }
  .exp-table td {
    padding: 3px 0;
    border-top: 1px solid var(--qba-rule);
  }
  .val-up { color: #c2410c; font-weight: 700; text-align: right; }
  .val-down { color: #0369a1; font-weight: 700; text-align: right; }
  .val-none { color: #64748b; text-align: right; }
</style>""")

    out.append("""<header class="hero">
<h1>Interactive Knowledge Graph</h1>
<p class="lede">Explore the Quantum Biology Ontology as an interconnected network of <strong>83 entities</strong> across <strong>7 subcellular compartments</strong> connected by <strong>154 biochemical edges</strong>. Project differential expression data across multiple experimental studies, partition the topology using mathematical clustering algorithms, or expand/contract node distances to resolve dense clusters.</p>
</header>

<div class="kg-container">
  <!-- Layout & Clustering Controls -->
  <div class="panel-box">
    <div class="panel-header">
      <h3>Layout &amp; Mathematical Clustering</h3>
      <div class="spacing-controls">
        <span class="spacing-label">Cluster Distance:</span>
        <button class="tool-btn spacing-btn" id="btn-expand" title="Spread out nodes to resolve dense clusters">&plus; Expand Distance</button>
        <button class="tool-btn spacing-btn" id="btn-contract" title="Pack nodes closer together">&minus; Contract Distance</button>
      </div>
    </div>
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
    <strong>Subcellular Localisation (Default):</strong> Grouping 83 entities into 7 biological compartments (Mitochondria, Chloroplast, Nucleus, Cytosol, Peroxisome, Plasma Membrane &amp; Cell, Environment) inside compound boundaries using physics-based relaxation. Use <em>Expand Distance</em> to spread dense clusters.
  </div>

  <!-- Canvas Stage -->
  <div class="canvas-wrapper">
    <div class="canvas-toolbar">
      <div class="toolbar-left">
        <input type="text" class="search-input" id="search-input" placeholder="Search entity (e.g. AOX, CRY1, CSD)..." autocomplete="off">
      </div>
      <div class="toolbar-right">
        <button class="tool-btn spacing-btn" id="btn-expand-canvas" title="Spread out nodes to resolve dense clusters">&harr; Expand Spacing</button>
        <button class="tool-btn spacing-btn" id="btn-contract-canvas" title="Pack nodes closer together">&rarr;&larr; Contract Spacing</button>
        <button class="tool-btn" id="btn-zoom-in" title="Zoom In">+ Zoom In</button>
        <button class="tool-btn" id="btn-zoom-out" title="Zoom Out">- Zoom Out</button>
        <button class="tool-btn" id="btn-fit" title="Fit to View">Fit View</button>
      </div>
    </div>
    <div id="cy"></div>
    <div class="legend-box">
      <div class="legend-group">
        <span style="font-weight:650; color:var(--qba-ink, #0f172a);">Evidence Tier:</span>
        <span class="legend-item"><span class="tier-pill tier-t1"></span> T1 Demonstrated</span>
        <span class="legend-item"><span class="tier-pill tier-t2"></span> T2 Inferred</span>
        <span class="legend-item"><span class="tier-pill tier-t3"></span> T3 Plausible</span>
        <span class="legend-item"><span class="tier-pill tier-t4"></span> T4 Context</span>
      </div>
      <div class="legend-group">
        <span style="font-weight:650; color:var(--qba-ink, #0f172a);">Expression Response:</span>
        <span class="legend-item"><span class="color-bar"></span></span>
        <span class="legend-item" style="color:#0369a1; font-weight:700;">Down (&le; -2.0)</span>
        <span class="legend-item" style="color:var(--qba-soft, #475569);">Neutral</span>
        <span class="legend-item" style="color:#c2410c; font-weight:700;">Up (&ge; +2.0)</span>
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
  let spacingMultiplier = 1.0;

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

    // Distance Spacing buttons (both top panel and canvas toolbar)
    const handleExpand = () => scaleSpacing(1.25);
    const handleContract = () => scaleSpacing(0.80);
    
    document.getElementById('btn-expand').onclick = handleExpand;
    document.getElementById('btn-contract').onclick = handleContract;
    document.getElementById('btn-expand-canvas').onclick = handleExpand;
    document.getElementById('btn-contract-canvas').onclick = handleContract;

    // Zoom and Fit buttons
    document.getElementById('btn-zoom-in').onclick = () => {
      if (cy) cy.zoom({ level: cy.zoom() * 1.25, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } });
    };
    document.getElementById('btn-zoom-out').onclick = () => {
      if (cy) cy.zoom({ level: cy.zoom() * 0.8, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } });
    };
    document.getElementById('btn-fit').onclick = () => {
      if (cy) cy.animate({ fit: { padding: 45 }, duration: 350 });
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

  function scaleSpacing(factor) {
    if (!cy) return;
    spacingMultiplier *= factor;

    const childNodes = cy.nodes('[!is_compartment]');
    if (childNodes.length === 0) return;

    if (currentLayoutName === 'subcellular') {
      // In subcellular layout, scale intra-compartment node positions relative to compartment centroid,
      // and scale compartment centroids relative to global center.
      let gX = 0, gY = 0, total = 0;
      childNodes.forEach(n => {
        const p = n.position();
        gX += p.x;
        gY += p.y;
        total++;
      });
      const centerX = gX / total;
      const centerY = gY / total;

      const compCenters = {};
      const parents = cy.nodes('[?is_compartment]');
      parents.forEach(pNode => {
        const cChildren = childNodes.filter(n => n.data('default_parent') === pNode.id());
        if (cChildren.length > 0) {
          let cX = 0, cY = 0;
          cChildren.forEach(n => {
            const pos = n.position();
            cX += pos.x;
            cY += pos.y;
          });
          compCenters[pNode.id()] = {
            x: cX / cChildren.length,
            y: cY / cChildren.length
          };
        }
      });

      cy.batch(() => {
        childNodes.forEach(n => {
          const pId = n.data('default_parent');
          const cCenter = compCenters[pId] || { x: centerX, y: centerY };
          const pos = n.position();

          const dx = (pos.x - cCenter.x) * factor;
          const dy = (pos.y - cCenter.y) * factor;

          const newCenterX = centerX + (cCenter.x - centerX) * factor;
          const newCenterY = centerY + (cCenter.y - centerY) * factor;

          n.position({
            x: newCenterX + dx,
            y: newCenterY + dy
          });
        });
      });
    } else {
      // Global centroid scaling for flat layouts
      let gX = 0, gY = 0, total = 0;
      childNodes.forEach(n => {
        const p = n.position();
        gX += p.x;
        gY += p.y;
        total++;
      });
      const centerX = gX / total;
      const centerY = gY / total;

      cy.batch(() => {
        childNodes.forEach(n => {
          const pos = n.position();
          n.position({
            x: centerX + (pos.x - centerX) * factor,
            y: centerY + (pos.y - centerY) * factor
          });
        });
      });
    }

    // Smoothly fit into view
    cy.animate({ fit: { padding: 45 }, duration: 300 });
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

        // ALWAYS keep label color dark slate/ink (#0f172a) with white outline halo!
        // NEVER set label to white on white canvas.
        node.style('color', '#0f172a');
        node.style('text-outline-color', '#ffffff');
        node.style('text-outline-width', 2.5);

        if (activeExps.size > 0) {
          node.style('background-color', getExpressionColor(avg));
        } else if (currentLayoutName === 'mcl' && node.data('mcl_color')) {
          node.style('background-color', node.data('mcl_color'));
        } else if (currentLayoutName === 'kmeans' && node.data('kmeans_color')) {
          node.style('background-color', node.data('kmeans_color'));
        } else {
          node.style('background-color', '#e2e8f0');
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
            'background-opacity': 0.70,
            'border-width': 1.5,
            'border-style': 'dashed',
            'border-color': '#3B6EA5',
            'border-opacity': 0.85,
            'border-radius': 14,
            'label': 'data(label)',
            'font-size': '12.5px',
            'font-weight': 'bold',
            'color': '#1e3a8a', /* deep navy ink - high contrast */
            'text-outline-color': '#ffffff',
            'text-outline-width': 2.0,
            'text-outline-opacity': 1.0,
            'text-valign': 'top',
            'text-halign': 'center',
            'text-margin-y': 10,
            'padding': '28px'
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
              return t === 'T1' ? '#0f172a' : (t === 'T2' ? '#334155' : (t === 'T3' ? '#64748b' : '#94a3b8'));
            },
            'font-size': '9.5px',
            'font-weight': '600',
            'font-family': 'system-ui, -apple-system, sans-serif',
            'color': '#0f172a', /* deep dark ink — NEVER white! */
            'text-outline-color': '#ffffff', /* white halo protects text from background / edge collisions */
            'text-outline-width': 2.5,
            'text-outline-opacity': 1.0,
            'text-valign': 'bottom',
            'text-margin-y': 6,
            'text-wrap': 'ellipsis',
            'text-max-width': '105px'
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
            'font-size': '8.5px',
            'color': '#334155', /* dark slate */
            'text-outline-color': '#ffffff',
            'text-outline-width': 1.5,
            'text-outline-opacity': 0.95,
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
      const addressableBadge = data.is_magnetically_addressable ? '<span class="badge badge-mag">Magnetically Addressable</span>' : '';

      tooltip.innerHTML = `
        <strong>${data.label}</strong> <span style="font-size:0.75rem; color:#64748b;">(${data.id})</span><br/>
        <div style="margin:4px 0;">
          <span class="badge badge-tier">${data.evidence_tier} (${data.evidence_tier === 'T1' ? 'Demonstrated' : (data.evidence_tier === 'T2' ? 'Inferred' : (data.evidence_tier === 'T3' ? 'Plausible' : 'Context'))})</span>
          <span class="badge badge-org">${data.organelle || data.compartment_name}</span>
          ${addressableBadge}
        </div>
        ${qClasses ? `<div style="margin-top:2px;">${qClasses}</div>` : ''}
        ${data.description ? `<p style="margin:6px 0 0; font-size:0.8rem; color:#475569;">${data.description}</p>` : ''}
        ${avg !== null ? `<div style="margin-top:6px; font-weight:650; color:#0f172a;">Average Selected Effect: <span class="${avg > 0 ? 'val-up' : (avg < 0 ? 'val-down' : '')}">${(avg > 0 ? '+' : '') + avg.toFixed(2)} log₂FC</span></div>` : ''}
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
      infoEl.innerHTML = '<strong>Subcellular Localisation (Default):</strong> Grouping 83 entities into 7 biological compartments (Mitochondria, Chloroplast, Nucleus, Cytosol, Peroxisome, Plasma Membrane &amp; Cell, Environment) inside compound boundaries using physics-based relaxation. Use <em>Expand Distance</em> to spread dense clusters.';
      
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
        'comp_chloroplast': { x: -420, y: -300 },
        'comp_mitochondria': { x: 420, y: -300 },
        'comp_cytosol': { x: 0, y: -50 },
        'comp_nucleus': { x: -420, y: 240 },
        'comp_peroxisome': { x: 420, y: 240 },
        'comp_plasma_membrane': { x: 0, y: 400 },
        'comp_environment': { x: 0, y: -520 }
      };

      cy.nodes('[!is_compartment]').forEach(n => {
        const p = n.data('default_parent');
        const pos = compPositions[p] || { x: 0, y: 0 };
        const jitterX = (Math.random() - 0.5) * 180;
        const jitterY = (Math.random() - 0.5) * 180;
        n.position({ x: pos.x + jitterX, y: pos.y + jitterY });
      });

      // 4. Run compound cose layout with generous spacing
      cy.layout({
        name: 'cose',
        animate: true,
        animationDuration: 800,
        fit: true,
        padding: 45,
        randomize: false,
        componentSpacing: 90,
        nodeRepulsion: 18000,
        idealEdgeLength: 95,
        edgeElasticity: 0.45,
        nestingFactor: 0.15,
        gravity: 0.22,
        numIter: 1600
      }).run();

      updateNodeColors();
      return;
    }

    // Unparent for flat layouts
    unparentNodes();

    if (name === 'cose') {
      infoEl.innerHTML = '<strong>Compound Spring Embedder (CoSE):</strong> Unconstrained force-directed physics simulation based on spring tension and electrical repulsion across the entire network. Use <em>Expand Distance</em> to spread clusters.';
      cy.layout({
        name: 'cose',
        animate: true,
        animationDuration: 800,
        fit: true,
        padding: 45,
        randomize: true,
        componentSpacing: 70,
        nodeRepulsion: 14000,
        idealEdgeLength: 100,
        edgeElasticity: 0.45,
        nestingFactor: 0.1,
        gravity: 0.22,
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
        minNodeSpacing: 30,
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
        padding: 45,
        directed: true,
        roots: roots.length > 0 ? roots : undefined,
        spacingFactor: 1.5
      }).run();
    }

    updateNodeColors();
  }

  function layoutClusterConstellation(clusters) {
    const K = clusters.length;
    const R = 340;
    clusters.forEach((clusterNodes, cIdx) => {
      const angle = (2 * Math.PI * cIdx) / K;
      const cx = R * Math.cos(angle);
      const cy_pos = R * Math.sin(angle);
      const N = clusterNodes.length;
      const subRadius = Math.max(38, 22 * Math.sqrt(N));
      clusterNodes.forEach((node, nIdx) => {
        const subAngle = (2 * Math.PI * nIdx) / N;
        const x = cx + subRadius * Math.cos(subAngle);
        const y = cy_pos + subRadius * Math.sin(subAngle);
        node.position({ x, y });
      });
    });
    cy.animate({ fit: { padding: 45 }, duration: 600 });
  }
</script>
""")
    out.append(tail())
    return "\n".join(out)


def build_heatmap():
    out = [head(
        "Collective Heatmap — Quantum Biology Atlas",
        "A dense, high-contrast summary table of all experimental data across all ontology entities.",
    )]
    out.append("""<style>
  .heatmap-container {
    overflow-x: auto;
    margin-top: 20px;
    border: 1px solid var(--qba-rule);
    border-radius: 10px;
    background: var(--qba-bg, #ffffff);
    box-shadow: 0 2px 8px rgba(0,0,0,0.04);
  }
  table.heatmap {
    border-collapse: collapse;
    width: 100%;
    font-size: 0.85rem;
    color: var(--qba-ink, #0f172a);
  }
  table.heatmap th, table.heatmap td {
    padding: 7px 12px;
    text-align: left;
    border-bottom: 1px solid var(--qba-rule);
  }
  table.heatmap th {
    background: var(--qba-card);
    font-weight: 700;
    color: var(--qba-ink, #0f172a);
    position: sticky;
    top: 0;
    z-index: 2;
  }
  table.heatmap th:first-child {
    left: 0;
    z-index: 3;
    min-width: 220px;
  }
  table.heatmap td:first-child {
    background: var(--qba-card);
    font-weight: 600;
    color: var(--qba-ink, #0f172a);
    position: sticky;
    left: 0;
    z-index: 1;
    border-right: 1px solid var(--qba-rule);
  }
  .cell {
    text-align: center;
    font-weight: 600;
    font-family: system-ui, -apple-system, sans-serif;
  }
  .controls {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-top: 15px;
    margin-bottom: 15px;
  }
  .controls label {
    font-size: 0.85rem;
    font-weight: 600;
    color: var(--qba-soft, #475569);
  }
  select {
    padding: 6px 12px;
    border-radius: 6px;
    border: 1px solid var(--qba-rule);
    background: var(--qba-bg, #ffffff);
    color: var(--qba-ink, #0f172a);
    font: inherit;
    font-size: 0.88rem;
  }
</style>""")
    
    out.append("""<header class="hero">
<h1>Collective Heatmap</h1>
<p class="lede">A consolidated high-contrast view of all experimental data across all 83 Quantum Biology entities. Cells show the log₂ fold change, color-scaled from blue (downregulation) through white to vermillion (upregulation).</p>
</header>
<div class="controls">
  <label for="sort">Sort by:</label>
  <select id="sort" onchange="renderHeatmap()">
    <option value="name">Entity Name (Alphabetical)</option>
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
      
      // Vermillion #D55E00 (213, 94, 0)
      // Blue #0072B2 (0, 114, 178)
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
    
    // Filter out parent compound nodes so only actual entities appear
    let nodes = graphData.elements.nodes
      .filter(n => !n.data.is_compartment)
      .map(n => {
         let vals = [];
         experiments.forEach(e => {
           let v = graphData.experiments[e] ? graphData.experiments[e][n.data.id] : undefined;
           if (typeof v === 'object' && v !== null) v = v.log2fc !== undefined ? v.log2fc : v.mean_log2fc;
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
        let text = (v !== undefined && v !== null) ? (v > 0 ? '+' : '') + v.toFixed(2) : '—';
        
        // High contrast text check:
        // White text ONLY on heavily saturated cells (|v| >= 1.0)
        // Dark ink (#0f172a) on light/white cells (|v| < 1.0)
        let textColor = '#0f172a';
        if (v !== undefined && v !== null && Math.abs(v) >= 1.0) {
          textColor = '#ffffff';
        } else if (color === 'transparent') {
          textColor = '#64748b';
        }
        
        let style = color !== 'transparent' 
          ? `background-color: ${color}; color: ${textColor};` 
          : `color: #64748b;`;
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
