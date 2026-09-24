/**
 * Legibility probe — runs inside a real browser against a rendered QBM map.
 *
 * This is the acceptance test for the standing requirement that figures be
 * legible: no overlapping text, nothing clipped at the edges, every label
 * readable. The review draft it replaces carried the margin note
 * "The text spills out of the box's", and the fix was structural — boxes are
 * sized around measured text — so the test has to be structural too.
 *
 * It deliberately does NOT re-run the compiler's arithmetic. qbio.layout sizes
 * boxes with matplotlib's glyph metrics; this probe measures what a browser
 * actually painted, using its own independent text layout. If the two engines
 * disagree, that disagreement is the bug, and a test that shared the metric
 * engine would never see it.
 *
 * Everything is measured in SCREEN space via getBoundingClientRect(), not
 * getBBox(). getBBox() reports an element's own untransformed coordinates, so a
 * node inside a <g transform="translate(...)"> appears to sit at negative
 * coordinates and every element reads as clipped. Screen space is also simply
 * what the reader sees.
 *
 * Returns {failures: [...], stats: {...}}. An empty `failures` is a pass.
 *
 * Every assertion below has been verified non-vacuous by injecting the matching
 * defect into a clean map and confirming the probe fires: shrinking a node box
 * raised TEXT OVERFLOW, moving one box onto another raised NODE OVERLAP,
 * moving a label background onto a node raised EDGE LABEL, and moving the title
 * off-canvas raised CLIPPED.
 */
(() => {
  const svg = document.querySelector('svg');
  if (!svg) return { failures: ['no <svg> element on the page'], stats: {} };

  const root = svg.getBoundingClientRect();
  const rel = (el) => {
    const r = el.getBoundingClientRect();
    return {
      x: r.left - root.left,
      y: r.top - root.top,
      x2: r.right - root.left,
      y2: r.bottom - root.top,
      w: r.width,
      h: r.height,
    };
  };
  const CANVAS = { x: 0, y: 0, x2: root.width, y2: root.height };

  const inside = (i, o, tol) =>
    i.x >= o.x - tol && i.y >= o.y - tol && i.x2 <= o.x2 + tol && i.y2 <= o.y2 + tol;
  const overlaps = (a, b, tol) =>
    !(a.x2 <= b.x + tol || b.x2 <= a.x + tol || a.y2 <= b.y + tol || b.y2 <= a.y + tol);
  const fmt = (b) =>
    `[${b.x.toFixed(1)},${b.y.toFixed(1)} → ${b.x2.toFixed(1)},${b.y2.toFixed(1)}]`;

  const failures = [];
  // Two different tolerances, and mixing them up is easy:
  //   CONTAIN_TOL  slack when asking "is A inside B" — a positive value is lenient.
  //   PENETRATE_TOL how far two boxes must actually intrude before it counts as an
  //                 overlap. Passing a NEGATIVE value to overlaps() would expand both
  //                 boxes and turn the test into a proximity check — which is how an
  //                 earlier draft reported 19 false "unit chip covers label" failures
  //                 on boxes with 0.2px of genuine clearance.
  const CONTAIN_TOL = 1.5;
  const PENETRATE_TOL = 0.5;

  // ---- 1. every text run sits inside the box that was sized around it -----
  const rects = {};
  svg.querySelectorAll('[data-node-rect]').forEach((r) => {
    rects[r.getAttribute('data-node-rect')] = rel(r);
  });
  let textRuns = 0;
  svg.querySelectorAll('[data-text-for]').forEach((t) => {
    textRuns++;
    const id = t.getAttribute('data-text-for');
    const box = rects[id];
    if (!box) {
      failures.push(`text references unknown node "${id}"`);
      return;
    }
    const tb = rel(t);
    if (!inside(tb, box, CONTAIN_TOL)) {
      failures.push(
        `TEXT OVERFLOW on "${id}": "${t.textContent}" ${fmt(tb)} escapes box ${fmt(box)}`
      );
    }
  });

  // ---- 2. no two node boxes overlap --------------------------------------
  const ids = Object.keys(rects);
  for (let i = 0; i < ids.length; i++) {
    for (let j = i + 1; j < ids.length; j++) {
      if (overlaps(rects[ids[i]], rects[ids[j]], PENETRATE_TOL)) {
        failures.push(`NODE OVERLAP: "${ids[i]}" ${fmt(rects[ids[i]])} / "${ids[j]}" ${fmt(rects[ids[j]])}`);
      }
    }
  }

  // ---- 3. nothing is clipped by the canvas -------------------------------
  let checked = 0;
  svg.querySelectorAll('rect, text, path, tspan').forEach((el) => {
    let b;
    try {
      b = rel(el);
    } catch (e) {
      return;
    }
    if (b.w === 0 && b.h === 0) return;           // empty markers, defs
    checked++;
    if (!inside(b, CANVAS, CONTAIN_TOL)) {
      failures.push(
        `CLIPPED <${el.tagName}> "${(el.textContent || '').slice(0, 44)}" ${fmt(b)} outside canvas ${fmt(CANVAS)}`
      );
    }
  });

  // ---- 4. edge labels never cover a node ---------------------------------
  svg.querySelectorAll('[data-edge-label]').forEach((l) => {
    const lb = rel(l);
    ids.forEach((id) => {
      if (overlaps(lb, rects[id], PENETRATE_TOL)) {
        failures.push(`EDGE LABEL "${l.getAttribute('data-edge-label')}" covers node "${id}"`);
      }
    });
  });

  // ---- 5. unit chips never cover a node's own label -----------------------
  let chipPairs = 0;
  svg.querySelectorAll('[data-unit-for]').forEach((u) => {
    const id = u.getAttribute('data-unit-for');
    const ub = rel(u);
    // Scoped to this chip's own node: a chip sitting above node A is expected to
    // be nowhere near node B's text, and comparing them all-against-all only
    // produces noise.
    svg.querySelectorAll(`[data-text-for="${id}"]`).forEach((t) => {
      chipPairs++;
      if (overlaps(ub, rel(t), PENETRATE_TOL)) {
        failures.push(`UNIT CHIP covers the label of "${id}"`);
      }
    });
  });

  // ---- 6. compartment bands must not overlap each other -------------------
  // Added after two bands shipped overlapping by 12px: a band is drawn
  // COMPARTMENT_PAD below its last node and COMPARTMENT_PAD + the label band above
  // its first, so a uniform row gutter between lanes in different compartments is
  // not enough. Nothing else here would have caught it — the nodes were fine, only
  // the bands around them collided.
  const bands = Array.from(svg.querySelectorAll('[data-compartment-rect]')).map((r, i) => ({
    i,
    name: r.getAttribute('data-compartment-rect'),
    box: rel(r),
  }));
  for (let i = 0; i < bands.length; i++) {
    for (let j = i + 1; j < bands.length; j++) {
      if (overlaps(bands[i].box, bands[j].box, PENETRATE_TOL)) {
        const dy =
          Math.min(bands[i].box.y2, bands[j].box.y2) - Math.max(bands[i].box.y, bands[j].box.y);
        failures.push(
          `COMPARTMENT BANDS OVERLAP: "${bands[i].name}"[${i}] / "${bands[j].name}"[${j}] ` +
            `by ${dy.toFixed(1)}px`
        );
      }
    }
  }

  // ---- 7. a compartment label must not land on a node --------------------
  const compLabels = Array.from(svg.querySelectorAll('.qbm-compartment-label'));
  compLabels.forEach((l) => {
    const lb = rel(l);
    ids.forEach((id) => {
      if (overlaps(lb, rects[id], PENETRATE_TOL)) {
        failures.push(`COMPARTMENT LABEL "${l.textContent}" covers node "${id}"`);
      }
    });
  });

  // ---- 8. on a data-overlaid map, the overlay must actually have rendered --
  // The overlay slot once carried an inline style="fill:none", which outranks every
  // selector, so the per-node fills silently never applied and the "data" map was
  // identical to the base map. Assert the overlay changed something.
  const valueChips = svg.querySelectorAll('[data-value-for]').length;
  if (valueChips > 0) {
    let tinted = 0;
    svg.querySelectorAll('[data-overlay-for]').forEach((o) => {
      const f = getComputedStyle(o).fill;
      if (f && f !== 'none' && !/rgba\(0,\s*0,\s*0,\s*0\)/.test(f)) tinted++;
    });
    if (tinted === 0) {
      failures.push(
        `OVERLAY DID NOT RENDER: ${valueChips} nodes carry a value chip but none is tinted`
      );
    }
    const bar = svg.querySelector('.qbm-overlay-legend');
    if (!bar) {
      failures.push('data-overlaid map has no colour-bar legend');
    } else {
      const bb = rel(bar);
      ids.forEach((id) => {
        if (overlaps(bb, rects[id], PENETRATE_TOL)) failures.push(`COLOUR BAR covers node "${id}"`);
      });
      svg.querySelectorAll('.qbm-caption, .qbm-title, .qbm-subtitle').forEach((c) => {
        if (overlaps(bb, rel(c), PENETRATE_TOL)) failures.push('COLOUR BAR covers title or caption');
      });
    }
  }

  // ---- 9. the tier legend must sit clear of the drawing ------------------
  // It used to be drawn at a fixed top-left position inside the canvas group, which
  // happened to be empty on QBM-01 and was not on QBM-03, where it landed on the
  // NUCLEUS band label. It now gets reserved header height; this asserts that.
  const tierLegend = svg.querySelector('.qbm-legend-group');
  if (!tierLegend) {
    failures.push('no evidence-tier legend — every map must show how to read its borders');
  } else {
    const lb = rel(tierLegend);
    ids.forEach((id) => {
      if (overlaps(lb, rects[id], PENETRATE_TOL)) failures.push(`TIER LEGEND covers node "${id}"`);
    });
    bands.forEach((b) => {
      if (overlaps(lb, b.box, PENETRATE_TOL))
        failures.push(`TIER LEGEND covers compartment band "${b.name}"`);
    });
    svg.querySelectorAll('.qbm-compartment-label, .qbm-title, .qbm-subtitle').forEach((c) => {
      if (overlaps(lb, rel(c), PENETRATE_TOL))
        failures.push(`TIER LEGEND covers "${c.textContent.slice(0, 30)}"`);
    });
  }

  // ---- 10. the map must carry a caption naming its data source -----------
  const caption = Array.from(svg.querySelectorAll('.qbm-caption'))
    .map((n) => n.textContent)
    .join(' ');
  if (/&amp;|&quot;|&lt;|&gt;/.test(caption)) {
    failures.push('CAPTION IS DOUBLE-ESCAPED — entities are showing as literal text');
  }
  if (caption.trim().length < 80) {
    failures.push('CAPTION missing or too short — every map must state what it shows and where it came from');
  } else if (!/derived from/i.test(caption)) {
    failures.push('CAPTION does not say what the map was derived from');
  }

  // ---- 11. time-course sparklines sit on their node, not on its text ------
  // Only present on a series overlay. Two things have to hold: the trace must be
  // INSIDE the node it belongs to (an overlay appended without the body group's
  // transform lands next to the wrong node entirely, which is how the first
  // published OSD-38 overlay shipped), and its value label must not cover the
  // node's own identifiers.
  const sparks = Array.from(svg.querySelectorAll('.qbm-spark'));
  let sparkChecks = 0;
  sparks.forEach((g) => {
    const id = g.getAttribute('data-spark-for');
    const gb = rel(g);
    const nb = rects[id];
    if (!nb) {
      failures.push(`SPARKLINE for unknown node "${id}"`);
      return;
    }
    sparkChecks++;
    // Use the probe's own `inside` helper and its {x,y,x2,y2} box shape. Writing a
    // fresh comparison against .left/.right here read fine and compared against
    // undefined on every axis, so it failed for all four sparklines on a figure that
    // was correct — the mirror image of a vacuous check.
    if (!inside(gb, nb, CONTAIN_TOL)) {
      failures.push(`SPARKLINE for "${id}" is not inside its node box ${fmt(gb)} / ${fmt(nb)}`);
    }
    svg.querySelectorAll(`[data-text-for="${id}"]`).forEach((t) => {
      if (overlaps(gb, rel(t), PENETRATE_TOL)) {
        failures.push(`SPARKLINE for "${id}" covers that node's own label`);
      }
    });
  });
  if (sparks.length) {
    const traces = svg.querySelectorAll('.qbm-spark-line').length;
    if (!traces) failures.push('SPARKLINE groups present but no trace was drawn');
  }

  return {
    failures,
    stats: {
      sparklines: sparks.length,
      sparkChecks,
      nodes: ids.length,
      textRuns,
      elementsChecked: checked,
      canvas: `${root.width.toFixed(0)}x${root.height.toFixed(0)} css px`,
      viewBox: svg.getAttribute('viewBox'),
      chipPairs,
      captionChars: caption.trim().length,
    },
  };
})();
