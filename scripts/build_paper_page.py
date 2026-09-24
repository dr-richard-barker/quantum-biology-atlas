#!/usr/bin/env python3
"""
Render `docs/paper-<key>.html` from `results/papers/<key>/record.json`.

Generated from the record for the same reason every other page in this repository is:
a number typed into HTML cannot be re-derived, and the figures this atlas replaces had
their values hard-coded. If a count on this page is wrong, the record is wrong, and the
record came from the parser.

Reuses `scripts/build_site.py`'s head/tail so the CoSE palette and the absence of the
navigation rail stay in one place.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from build_site import e, head, tail  # noqa: E402

RESULTS = ROOT / "results" / "papers"
DOCS = ROOT / "docs"


def sparkline_inline(points, vmax: float, width: float = 92.0, height: float = 22.0) -> str:
    """A small inline SVG trace for the per-node table, same encoding as the map."""
    obs = [(i, v) for i, v in enumerate(points) if v is not None]
    if not obs or vmax <= 0:
        return ""
    step = width / max(1, len(points) - 1)
    zero = height / 2.0
    pts = [(i * step, zero - max(-1.0, min(1.0, v / vmax)) * (height / 2 - 2), v) for i, v in obs]
    segs = [
        f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
        f'stroke="{"#D55E00" if v1 >= 0 else "#0072B2"}" stroke-width="1.4"/>'
        for (x1, y1, v1), (x2, y2, _) in zip(pts, pts[1:])
    ]
    dots = [
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="1.6" fill="{"#D55E00" if v >= 0 else "#0072B2"}"/>'
        for x, y, v in pts
    ]
    return (
        f'<svg viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
        f'role="img" aria-label="time course trace">'
        f'<line x1="0" y1="{zero}" x2="{width}" y2="{zero}" stroke="currentColor" '
        f'stroke-width="0.7" opacity=".28"/>' + "".join(segs + dots) + "</svg>"
    )


def build(key: str) -> str:
    rec = json.loads((RESULTS / key / "record.json").read_text())
    figs = rec["figures"]
    tps = figs[0]["timepoints"]

    out = [head(
        f"{rec['citation'].split(' (')[0]} — near-null field time course",
        f"A {len(tps)}-point time course from {rec['citation']} projected onto the "
        f"quantum pathway maps as trajectories.",
    )]

    out.append(f"""<header class="hero">
<h1>Time on a map</h1>
<p class="lede">A {len(tps)}-point near-null-field time course — {e(', '.join(tps))} — in
roots and shoots, projected onto the redox and respiratory maps. Every other overlay in
this atlas is a single snapshot; this one is a trajectory, which is the only way to see a
node that goes down and then comes back.</p>
<p class="lede">Source: {e(rec['citation'])},
<a href="https://doi.org/{e(rec['doi'])}">doi:{e(rec['doi'])}</a>
(<a href="https://www.ncbi.nlm.nih.gov/pmc/articles/{e(rec['pmcid'])}/">{e(rec['pmcid'])}</a>),
{e(rec['organism'])}.</p>
<ul class="stats">
<li><b>{rec['loci_in_table']}</b>loci in the source table</li>
<li><b>{len(rec['qbo_loci_covered'])}</b>are QBO atlas loci</li>
<li><b>{len(tps)}</b>timepoints × {len(rec['tissues'])} tissues</li>
<li><b>{rec['cells_parsed']:,}</b>values parsed</li>
</ul>
</header>""")

    # ---- the provenance warning, first and unmissable ---------------------
    out.append(f"""<div class="note">
<p><strong>These are the authors' published results, not a reanalysis.</strong>
No raw data was deposited in any public repository. The article's Data Availability
Statement reads, in full: <em>“{e(rec['data_availability_verbatim'])}”</em></p>
<p>So nothing on this page can be recomputed, re-thresholded or re-tested from source
data. What is drawn is what the authors chose to report, read out of
<code>{e(rec['source_table'])}</code> and re-projected onto the maps. That is a weaker
provenance than the NASA OSDR pages in this atlas, which rest on processed data anyone
can download, and it is labelled differently throughout:
<code>{e(rec['provenance_class'])}</code>.</p>
</div>""")

    # ---- what was measured ------------------------------------------------
    out.append(f"""<h2>What was measured</h2>
<p>{e(rec['field_regime'])}. Values are {e(rec['citation'].split(',')[0])}'s reported
fold change for NNMF-grown plants relative to GMF-grown controls, as
<code>mean ± SD</code>.</p>
<p><strong>The scale matters more than it looks.</strong> The published values are
<em>ratios</em> — 1.0 means no change — while every overlay in this atlas expects log2,
where 0.0 means no change. Feeding the ratios in directly would have coloured every
unchanged gene as strongly upregulated, and the figure would have looked completely
normal. The conversion happens in <code>qbio.papers.Series.to_log2</code>, the SD is
carried through the same transform rather than left in the wrong units, and
<code>qbio.project.project_series</code> refuses a series that is still on a ratio
scale.</p>
<p>The parse is complete: {rec['cells_parsed']:,} cells read,
{rec['cells_blank']} blank, {rec['rows_without_locus']} rows without a usable locus.
The identifiers in the source are written <code>At1g01980.1</code> — lowercase
<code>g</code>, with a transcript suffix — so a naive AGI pattern matches
<strong>none</strong> of them; normalisation is done in the parser rather than left to
each caller.</p>""")

    # ---- figures ----------------------------------------------------------
    out.append("<h2>The maps</h2>")
    out.append("""<p>Each node is tinted by its most extreme timepoint and carries a
sparkline of the whole trajectory: the colour says how far it moved, the line says when.
A node with no measurement is left unfilled, which is not the same as a measured zero.
Vermillion is above no-change, blue below, and the flat line through each trace is
log2 0.</p>""")

    for f in figs:
        png = f"maps/png/{pathlib.Path(f['svg']).stem}.png"
        low = ""
        if f["low_coverage_published"]:
            low = (f"""<p><strong>Coverage is below the atlas's own 25% threshold</strong>
({f['fraction_covered']:.0%}). It is shown anyway, with the number stated, because the
map's remaining nodes are respiratory complexes the source table does not cover at all —
not nodes that were measured and found unchanged.</p>""")
        rev = f["nodes_reversing_direction"]
        revtxt = (
            f"<p><strong>{len(rev)} of {f['nodes_with_data']} nodes reverse direction</strong> "
            f"during the course ({e(', '.join(rev))}) — behaviour no single-contrast "
            f"overlay can represent.</p>"
            if rev else ""
        )
        out.append(f"""<figure class="map">
<a href="{e(f['svg'])}"><img src="{e(png)}" alt="{e(f['id'])} with the {e(f['tissue'].lower())} time course projected" loading="lazy"></a>
<figcaption>
<span class="t">{e(f['id'])} · {e(f['tissue'].title())} · {f['nodes_with_data']} nodes with data ({f['fraction_covered']:.0%})</span>
{low}{revtxt}
<p>{e(f['provenance'])}</p>
<p class="dl"><a href="{e(f['svg'])}">SVG</a></p>
</figcaption>
</figure>""")

    # ---- per-node table ---------------------------------------------------
    out.append("<h2>Every value behind the figures</h2>")
    out.append("""<p>The numbers on the maps, in full, so the figures can be checked
rather than taken on trust. Values are log2 fold change (NNMF vs GMF); the trace uses
the same encoding as the maps.</p>""")

    for f in figs:
        out.append(f"<h3>{e(f['id'])} · {e(f['tissue'].title())}</h3>")
        out.append('<div class="tablewrap"><table><thead><tr><th>Node</th><th>Tier</th>'
                   "<th>Loci</th><th>Trace</th>" + "".join(f"<th>{e(t)}</th>" for t in tps)
                   + "<th>Peak</th></tr></thead><tbody>")
        for n in f["per_node"]:
            cells = "".join(
                f"<td>{'—' if v is None else f'{v:+.2f}'}</td>" for v in n["log2"]
            )
            out.append(
                f"<tr><td>{e(n['node_id'])}"
                + (" <em>(reverses)</em>" if n["reverses_direction"] else "")
                + f"</td><td><span class='swatch {e(n['evidence_tier'])}'></span>"
                f"{e(n['evidence_tier'])}</td>"
                # One element per locus: the cell may break between identifiers,
                # never inside one.
                + "<td>"
                + " ".join(f"<code>{e(l)}</code>" for l in n["loci"])
                + "</td>"
                f"<td>{sparkline_inline(n['log2'], f['vmax'])}</td>"
                f"{cells}<td><b>{n['peak']:+.2f}</b> @ {e(n['peak_timepoint'])}</td></tr>"
            )
        out.append('</tbody></table></div>'
                   '<p class="tablenote">Scroll the table sideways to see every '
                   'timepoint.</p>')

    # ---- what this does and does not show ---------------------------------
    out.append(f"""<h2>What this does not show</h2>
<ul>
<li><strong>Coverage is partial by construction.</strong> The source table was filtered
by its authors to genes involved in oxidative reactions, so it reaches the redox map well
and the respiratory map barely. {len(rec['qbo_loci_covered'])} of the atlas's QBO loci
appear in it: <code>{e(', '.join(rec['qbo_loci_covered']))}</code>.</li>
<li><strong>No significance is shown.</strong> The source reports <code>mean ± SD</code>
with no per-gene adjusted p-value, so there is no threshold to mark and none is invented.
The atlas's other overlays carry an asterisk for significance; this one deliberately has
none.</li>
<li><strong>A tier is not a result.</strong> The border style still reports how much is
known about each node's field sensitivity, which is independent of how far it moved here.
A T3 node that responds strongly is still a node with no measured magnetic mechanism.</li>
<li><strong>One experiment.</strong> Replication across the near-null-field literature is
what the atlas's pre-registered test addresses, and that test's result was null with a
minimum detectable effect of 4.0 — this page does not change that.</li>
</ul>

<h2>Reproducing it</h2>
<pre><code>PYTHONPATH=src python3 scripts/build_paper_showcase.py --paper {e(rec['key'])}
PYTHONPATH=src python3 scripts/build_paper_page.py --paper {e(rec['key'])}</code></pre>
<p>The supplementary archive is fetched from EuropePMC and cached under
<code>data/external/papers/</code>; the parsed values, per-node series and coverage are
written to <a href="results/papers/{e(rec['key'])}/record.json"><code>results/papers/{e(rec['key'])}/record.json</code></a>,
and this page is generated from that record.</p>

<footer>
<p><strong>Source.</strong> {e(rec['citation'])},
<a href="https://doi.org/{e(rec['doi'])}">doi:{e(rec['doi'])}</a>. Published open access
under CC BY; the values reproduced here are the authors'.</p>
<p><strong>Provenance class.</strong> <code>{e(rec['provenance_class'])}</code> — results
as published, no deposited raw data, no reanalysis.</p>
<p><a href="index.html">← Quantum Biology Atlas</a></p>
</footer>""")

    out.append(tail())
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--paper", default="Parmagnani2022")
    args = ap.parse_args()
    html = build(args.paper)
    path = DOCS / f"paper-{args.paper}.html"
    path.write_text(html, encoding="utf-8")
    print(f"wrote {path.relative_to(ROOT)} ({len(html) / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
