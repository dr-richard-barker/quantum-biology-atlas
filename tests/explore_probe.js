/**
 * explore_probe — acceptance test for the upload GUI, run inside a real browser.
 *
 * Like `legibility_probe.js`, this deliberately does not run in pytest. What is being
 * tested is behaviour that only exists in a browser: a file read through FileReader,
 * an SVG parsed and mutated in a live DOM, and — the part that matters — whether a
 * refusal actually reaches the page or merely reaches the console.
 *
 * The three assertions below are the reason the GUI exists in this form. Ported from
 * `qbio.project.project_expression`:
 *
 *   1. An all-unmatched file must REFUSE and draw nothing. A pale map rendered from a
 *      join that matched nothing looks like a result, and is the worst failure
 *      available here — worse than an error message.
 *   2. A thin join must WARN and state its coverage, not quietly draw.
 *   3. A namespace that cannot reach the chosen species must be caught BEFORE the join,
 *      because afterwards it is indistinguishable from "this gene did not respond".
 *
 * Plus one the repository learned from its own OSD-27 page: distinct nodes that collapse
 * onto the same source row must be named, or three nodes showing one number read as
 * three measurements agreeing.
 *
 * Usage: open docs/explore.html and evaluate this file. Returns {failures, stats};
 * an empty `failures` is a pass.
 *
 * Every assertion has been verified non-vacuous by feeding it the opposite input:
 * the empty-join case passes a matching table and fires, the low-coverage case passes a
 * full table and fires, and the collapse case passes an Arabidopsis table and fires.
 */
(async () => {
  const failures = [];
  const stats = {};
  const mod = await import('./assets/qbm-explore-ui.js');
  const $ = (id) => document.getElementById(id);
  const settle = () => new Promise((r) => setTimeout(r, 500));
  const msgKind = () => (document.querySelector('#report .msg') || {}).className || '';
  const msgText = () => ($('report').innerText || '');
  const drew = () => !!document.querySelector('#stage svg');

  const run = async (csv, name, { map, species }) => {
    mod.loadTable(csv, name);
    $('map').value = map;
    $('species').value = species;
    await mod.project();
    await settle();
  };

  // ---- 1. an all-unmatched file must refuse, and draw nothing -------------
  // Real AGI loci, none of which is on QBM-01.
  const decoys = ['AT1G01010', 'AT1G01020', 'AT1G01030', 'AT1G01040', 'AT1G01060',
    'AT1G01070', 'AT1G01080', 'AT1G01090', 'AT1G01100', 'AT1G01110'];
  await run(
    'locus,log2FoldChange\n' + decoys.map((g, i) => `${g},${(i % 5 - 2) * 0.7}`).join('\n'),
    'decoy.csv', { map: 'QBM-01', species: 'arabidopsis_thaliana' },
  );
  stats.emptyJoinKind = msgKind();
  if (!msgKind().includes('err')) {
    failures.push('EMPTY JOIN did not raise an error-level message');
  }
  if (drew()) {
    failures.push('EMPTY JOIN still drew a map — a blank map looks like a result');
  }
  if (!/refus/i.test(msgText())) {
    failures.push('EMPTY JOIN message does not say it is refusing');
  }

  // ---- 2. a thin join must warn AND state the coverage --------------------
  await run(
    'locus,log2FoldChange\nAT5G37510,1.4\nAT1G01010,0.2\nAT1G01020,-0.3',
    'thin.csv', { map: 'QBM-01', species: 'arabidopsis_thaliana' },
  );
  stats.lowCoverageKind = msgKind();
  if (!msgKind().includes('warn')) {
    failures.push('LOW COVERAGE did not raise a warning-level message');
  }
  if (!/\d+%/.test(msgText())) {
    failures.push('LOW COVERAGE warning does not state a coverage percentage');
  }
  if (!drew()) {
    failures.push('LOW COVERAGE refused outright; it should draw and warn');
  }

  // ---- 3. a namespace mismatch must be caught before the join -------------
  await run(
    'gene,log2FoldChange\nFBgn0025680,1.1\nFBgn0000008,-0.4\nFBgn0000014,0.3',
    'fly.csv', { map: 'QBM-03', species: 'arabidopsis_thaliana' },
  );
  stats.mismatchKind = msgKind();
  if (drew()) {
    failures.push('NAMESPACE MISMATCH drew a map; it must be caught before joining');
  }
  if (!/namespace/i.test(msgText())) {
    failures.push('NAMESPACE MISMATCH message does not name the problem');
  }

  // ---- 4. a real cross-species run works, and names its collapses ---------
  await run(
    'gene,log2FoldChange\nFBgn0025680,1.35\nFBgn0086907,-0.4\nFBgn0024957,0.22',
    'fly-real.csv', { map: 'QBM-03', species: 'drosophila_melanogaster' },
  );
  stats.crossSpeciesKind = msgKind();
  stats.crossSpeciesTinted = document.querySelectorAll('#stage .qbm-user-value').length;
  if (!drew()) {
    failures.push('CROSS-SPECIES run drew nothing');
  }
  if (!/ensembl_pan_homology/.test(msgText())) {
    failures.push('CROSS-SPECIES run does not name the orthology method used');
  }
  if (/orthodb/i.test(msgText())) {
    failures.push(
      'CROSS-SPECIES run claims OrthoDB, whose committed matrix is human-anchored and '
      + 'cannot reach Drosophila — that would read as two-method corroboration'
    );
  }
  // CRY1, CRY2 and the Trp-triad node all reach Drosophila cry.
  const collapseNamed = /CRY1/.test(msgText()) && /CRY2/.test(msgText())
    && /TRP_TRIAD/.test(msgText());
  if (!collapseNamed) {
    failures.push(
      'COLLAPSE not reported: CRY1, CRY2 and TRP_TRIAD all draw from one fly gene and '
      + 'carry identical values, which reads as three measurements agreeing'
    );
  }

  // ---- 5. overlay marks must land on their nodes -------------------------
  // The same coordinate-space defect that shipped in the Python renderer.
  const off = [];
  document.querySelectorAll('#stage .qbm-user-value').forEach((g) => {
    const id = g.getAttribute('data-value-for');
    const rect = document.querySelector(`#stage [data-node-rect="${CSS.escape(id)}"]`);
    if (!rect) { off.push(`${id} (no node rect)`); return; }
    const a = g.getBoundingClientRect();
    const b = rect.getBoundingClientRect();
    // The chip is CENTRED ON the node's bottom-right corner, exactly as
    // qbio.maps.render_projection places it (x = box.x2 - w/2). So it overhangs the
    // right edge by half its width — by design, not by accident. An earlier version of
    // this check required horizontal containment and failed on four correct chips: the
    // assertion was wrong, not the code. Test the intended geometry instead.
    const cx = (a.left + a.right) / 2;
    const cy = (a.top + a.bottom) / 2;
    const onCorner = Math.abs(cx - b.right) <= 6 && Math.abs(cy - b.bottom) <= 12;
    if (!onCorner) {
      off.push(`${id} (chip centre ${Math.round(cx)},${Math.round(cy)} vs node corner ${Math.round(b.right)},${Math.round(b.bottom)})`);
    }
  });
  if (off.length) {
    failures.push(`VALUE CHIP detached from its node: ${off.join(', ')}`);
  }

  return { failures, stats };
})();
