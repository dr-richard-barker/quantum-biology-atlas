/**
 * qbm-explore-ui — the page wiring for explore.html.
 *
 * All the logic that decides anything lives in qbm-explore.js: parsing, namespace
 * detection, the join, and the two refusals ported from qbio.project. This file only
 * moves data between the DOM and that module, and — importantly — renders the refusals
 * where a person will see them.
 *
 * A console.error is not a refusal. The whole point of `project_expression` raising on
 * an empty join is that a pale map looks like a result; that property is lost if the
 * browser version logs quietly and draws the map anyway.
 */
import {
  parseTable, pickValueColumn, pickIdColumn, pickPadjColumn, detectNamespace,
  joinToMap, applyOverlay, LOW_COVERAGE, CATALOG, MAPS,
} from './qbm-explore.js';

const $ = (id) => document.getElementById(id);
const report = $('report');
const stage = $('stage');

const state = {
  parsed: null,
  fileName: null,
  orthologs: null,
  sidecars: new Map(),
  svgs: new Map(),
};

// ---------------------------------------------------------------------------
// messages
// ---------------------------------------------------------------------------

function show(kind, title, bodyHtml) {
  report.innerHTML =
    `<div class="msg ${kind}"><h4>${escapeHtml(title)}</h4>${bodyHtml}</div>`;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

function clearStage() {
  stage.innerHTML = '';
}

// ---------------------------------------------------------------------------
// fetching
// ---------------------------------------------------------------------------

async function sidecar(mapId) {
  if (!state.sidecars.has(mapId)) {
    const r = await fetch(`${CATALOG}/qbo/${mapId}.json`);
    if (!r.ok) throw new Error(`could not load the annotation sidecar for ${mapId}`);
    state.sidecars.set(mapId, await r.json());
  }
  return state.sidecars.get(mapId);
}

async function mapSvg(mapId) {
  if (!state.svgs.has(mapId)) {
    const r = await fetch(`${MAPS}/${mapId}.svg`);
    if (!r.ok) throw new Error(`could not load the map ${mapId}`);
    state.svgs.set(mapId, await r.text());
  }
  return state.svgs.get(mapId);
}

async function orthologs() {
  if (!state.orthologs) {
    const r = await fetch(`${CATALOG}/orthologs.json`);
    if (!r.ok) throw new Error('could not load the ortholog map');
    state.orthologs = await r.json();
  }
  return state.orthologs;
}

// ---------------------------------------------------------------------------
// loading a table
// ---------------------------------------------------------------------------

function describeTable(parsed, name) {
  const idCol = pickIdColumn(parsed.header, parsed.rows);
  let valCol;
  try {
    valCol = pickValueColumn(parsed.header, parsed.rows);
  } catch (err) {
    throw new Error(
      `${err.message}. Columns found: ${parsed.header.join(', ') || '(none named)'}`
    );
  }
  const padjCol = pickPadjColumn(parsed.header);
  const ns = idCol.ns || { id: 'unknown', label: 'unrecognised', fraction: 0 };

  if (ns.fraction < 0.5) {
    throw new Error(
      `no column looks like gene identifiers — the best candidate, ` +
      `"${parsed.header[idCol.index] || `column ${idCol.index + 1}`}", matched a known ` +
      `namespace in only ${(ns.fraction * 100).toFixed(0)}% of rows. ` +
      `Recognised: Arabidopsis AGI, FlyBase, Ensembl, WormBase, SGD.`
    );
  }
  return { idCol, valCol, padjCol, ns };
}

function loadTable(text, name) {
  const parsed = parseTable(text);
  const cols = describeTable(parsed, name);
  state.parsed = parsed;
  state.cols = cols;
  state.fileName = name;

  // Pre-select the species the identifiers imply, so the commonest mistake — leaving
  // the selector on Arabidopsis with a fly table — needs an active choice to make.
  if (cols.ns.species) $('species').value = cols.ns.species;

  show('ok', `Read ${parsed.rows.length.toLocaleString()} rows from ${name}`, `
    <ul>
      <li>Format: <strong>${parsed.delimiter}</strong></li>
      <li>Identifiers: <strong>${escapeHtml(cols.ns.label)}</strong> in column
        "<code>${escapeHtml(parsed.header[cols.idCol.index] || cols.idCol.index + 1)}</code>"
        (${(cols.ns.fraction * 100).toFixed(0)}% of sampled rows match)</li>
      <li>Values: column
        "<code>${escapeHtml(parsed.header[cols.valCol] || cols.valCol + 1)}</code>"</li>
      <li>Adjusted p: ${cols.padjCol == null
        ? '<em>none found — no node will be marked significant</em>'
        : `column "<code>${escapeHtml(parsed.header[cols.padjCol])}</code>"`}</li>
    </ul>
    <p>Pick a map and press <strong>Project</strong>.</p>`);
  clearStage();
}

// ---------------------------------------------------------------------------
// projecting
// ---------------------------------------------------------------------------


/**
 * Distinct nodes that ended up drawing from exactly the same source rows.
 *
 * Cross-species projection collapses distinctions: on the cryptochrome map, CRY1, CRY2
 * and the Trp-triad node all reach the single fly gene `cry`, so all three carry one
 * number. Three nodes agreeing looks like corroboration between independent
 * measurements, and it is one measurement drawn three times. The repository's OSD-27
 * page reports this; a tool that lets anyone make the same figure has to report it too.
 */
function findCollapses(values) {
  const byKey = new Map();
  for (const [nodeId, v] of Object.entries(values)) {
    // The rows actually used: the ortholog targets when projecting, else the loci.
    // DEDUPLICATED — a node reaching one fly gene through two Arabidopsis loci (the
    // Trp-triad node reaches `cry` via both CRY1 and CRY2) otherwise gets a key with a
    // repeat in it, fails to match the single-locus nodes beside it, and is left out of
    // the very collapse it belongs to.
    const used = [...new Set(
      (v.via && v.via.length) ? v.via.map((x) => x.split('\u2192')[1]) : v.loci
    )].sort();
    const key = used.join('|');
    if (!key) continue;
    if (!byKey.has(key)) byKey.set(key, { rows: used, nodes: [] });
    byKey.get(key).nodes.push(nodeId);
  }
  return [...byKey.values()].filter((g) => g.nodes.length > 1);
}

function coverageList(c) {
  return `<ul class="cov">
    <li><b>${c.nodesWithData}/${c.addressable}</b>nodes with data</li>
    <li><b>${(c.fraction * 100).toFixed(0)}%</b>coverage</li>
    <li><b>${c.rowsUsed.toLocaleString()}</b>of your rows used</li>
    <li><b>${c.withoutLoci.length}</b>nodes carry no identifier</li>
  </ul>`;
}

function diagnostics(c) {
  const bits = [];
  if (c.unmatched.length) {
    bits.push(`<p><strong>${c.unmatched.length} node(s) had no match in your table:</strong>
      <code>${c.unmatched.map(escapeHtml).join('</code> <code>')}</code></p>`);
  }
  if (c.noOrtholog.length) {
    bits.push(`<p><strong>${c.noOrtholog.length} node(s) have no ortholog in that
      species</strong> — a real finding, not a gap: <code>${c.noOrtholog.map(escapeHtml).join('</code> <code>')}</code></p>`);
  }
  if (c.withoutLoci.length) {
    bits.push(`<p><strong>${c.withoutLoci.length} node(s) carry no gene identifier</strong>
      and cannot receive data by construction:
      <code>${c.withoutLoci.map(escapeHtml).join('</code> <code>')}</code></p>`);
  }
  if (c.rowsUnparseable) {
    bits.push(`<p>${c.rowsUnparseable.toLocaleString()} row(s) had no usable identifier
      or a non-numeric value and were skipped.</p>`);
  }
  if (!bits.length) return '';
  return `<details class="diag"><summary>What could not be mapped</summary>${bits.join('')}</details>`;
}

async function project() {
  if (!state.parsed) {
    show('err', 'No data loaded', '<p>Drop a table first, or load the example.</p>');
    return;
  }
  const mapId = $('map').value;
  const species = $('species').value;
  const aggregator = $('agg').value;
  const alpha = parseFloat($('alpha').value);

  try {
    const [side, svgText, orth] = await Promise.all([
      sidecar(mapId), mapSvg(mapId), orthologs(),
    ]);

    // A namespace that cannot reach the chosen species is an error, not an empty map.
    const ns = state.cols.ns;
    if (ns.species && ns.species !== species) {
      show('warn', 'Identifier namespace does not match the species you chose', `
        <p>Your identifiers look like <strong>${escapeHtml(ns.label)}</strong>
        (${escapeHtml(ns.species)}), but you selected
        <strong>${escapeHtml(species)}</strong>. Projecting anyway would match nothing.</p>
        <p>Change the species selector to ${escapeHtml(ns.species)}, or upload a table in
        the namespace for the species you want.</p>`);
      clearStage();
      return;
    }
    if (species !== 'arabidopsis_thaliana' && !orth.species?.[species]) {
      throw new Error(`no ortholog map is published for ${species}`);
    }

    const { values, coverage } = joinToMap(state.parsed, side, orth, {
      idIndex: state.cols.idCol.index,
      valueIndex: state.cols.valCol,
      padjIndex: state.cols.padjCol,
      species, aggregator,
      alpha: Number.isFinite(alpha) ? alpha : 0.05,
    });

    // ---- the refusals, rendered where a person will see them ----
    if (coverage.nodesWithData === 0) {
      show('err', 'Refusing to draw an empty map', `
        <p>Not one of ${coverage.addressable} identifier-bearing nodes on
        ${escapeHtml(mapId)} matched your table. A map rendered from nothing looks like a
        result, which is worse than an error, so nothing was drawn.</p>
        <p>Most likely the identifier namespaces differ. Yours were read as
        <strong>${escapeHtml(ns.label)}</strong>.</p>
        ${diagnostics(coverage)}`);
      clearStage();
      return;
    }

    const parser = new DOMParser();
    const doc = parser.parseFromString(svgText, 'image/svg+xml');
    const svg = doc.documentElement;
    const vmax = Math.max(...Object.values(values).map((v) => Math.abs(v.value)));
    if (!(vmax > 0)) {
      show('err', 'Every projected value is zero', `
        <p>The colour scale would be degenerate, so nothing was drawn. This is almost
        always a join that matched the wrong column.</p>${diagnostics(coverage)}`);
      clearStage();
      return;
    }

    stage.innerHTML = '';
    stage.appendChild(svg);
    const tinted = applyOverlay(svg, values, vmax);

    const collapses = findCollapses(values);
    const collapseWarn = collapses.length ? `
      <p><strong>${collapses.length} group(s) of nodes are drawing from the same
      source rows</strong>, so they carry identical values and will look like
      independent measurements agreeing:</p>
      <ul>${collapses.map((g) => `<li><code>${g.nodes.map(escapeHtml).join('</code>, <code>')}</code>
        \u2190 ${g.rows.length} row(s): <code>${g.rows.map(escapeHtml).join('</code> <code>')}</code></li>`).join('')}</ul>
      <p class="hint">This is not an error in the mapping \u2014 it is what the gene
      families really do. It is only misleading if unsaid.</p>` : '';

    const low = coverage.fraction < LOW_COVERAGE;
    const head = low
      ? `Projected, but coverage is only ${(coverage.fraction * 100).toFixed(0)}%`
      : `Projected onto ${mapId}`;
    const warn = low
      ? `<p><strong>That is below the ${(LOW_COVERAGE * 100).toFixed(0)}% threshold this
         atlas uses for its own figures.</strong> The map is drawn because you asked for
         it, and the number is stated because at this coverage the figure can mislead:
         most nodes are unfilled for want of data, not because they did not respond.</p>`
      : '';
    show(low ? 'warn' : 'ok', head, `
      ${warn}
      <p>${tinted} node(s) tinted, scale ±${vmax.toFixed(2)} log<sub>2</sub> fold change,
      multi-locus nodes combined by <strong>${escapeHtml(aggregator)}</strong>.
      ${species === 'arabidopsis_thaliana'
        ? 'No orthology projection was needed.'
        : `Orthology: Arabidopsis → ${escapeHtml(species)} via
           <code>${escapeHtml((orth.species[species].methods_used || []).join(', '))}</code>.`}
      ${state.cols.padjCol == null
        ? 'No adjusted p-value column was found, so no node is marked significant.'
        : `An asterisk marks a node with at least one locus at adjusted p ≤ ${alpha}.`}</p>
      ${coverageList(coverage)}
      ${collapseWarn}
      ${diagnostics(coverage)}`);
  } catch (err) {
    show('err', 'Could not project', `<p>${escapeHtml(err.message)}</p>`);
    clearStage();
  }
}

// ---------------------------------------------------------------------------
// wiring
// ---------------------------------------------------------------------------

function readFile(file) {
  const reader = new FileReader();
  reader.onload = () => {
    try {
      loadTable(String(reader.result), file.name);
    } catch (err) {
      show('err', 'Could not read that file', `<p>${escapeHtml(err.message)}</p>`);
      clearStage();
    }
  };
  reader.onerror = () => show('err', 'Could not read that file', '<p>The browser failed to read it.</p>');
  reader.readAsText(file);
}

const drop = $('drop');
['dragenter', 'dragover'].forEach((ev) =>
  drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add('over'); }));
['dragleave', 'drop'].forEach((ev) =>
  drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove('over'); }));
drop.addEventListener('drop', (e) => {
  const f = e.dataTransfer?.files?.[0];
  if (f) readFile(f);
});
$('file').addEventListener('change', (e) => {
  const f = e.target.files?.[0];
  if (f) readFile(f);
});
$('go').addEventListener('click', project);
$('demo').addEventListener('click', async () => {
  show('ok', 'Loading the example…', '<p>OSD-8 field-isolating contrast.</p>');
  try {
    const r = await fetch('example-data/OSD-8_MAG-1g_field-contrast.csv');
    if (!r.ok) throw new Error('the example file could not be fetched');
    loadTable(await r.text(), 'OSD-8_MAG-1g_field-contrast.csv');
  } catch (err) {
    show('err', 'Could not load the example', `<p>${escapeHtml(err.message)}</p>`);
  }
});

// Re-project on a control change, but only once something is loaded.
['map', 'species', 'agg'].forEach((id) =>
  $(id).addEventListener('change', () => { if (state.parsed) project(); }));

export { project, loadTable, state };
