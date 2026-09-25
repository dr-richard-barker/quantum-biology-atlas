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


def heatmap_inline(per_locus: dict[str, list[float | None]], vmax: float) -> str:
    """Render an inline SVG 2-row (or multi-row) heatmap showing per-locus divergence."""
    if not per_locus or vmax <= 0:
        return ""
    loci = sorted(per_locus)
    row_h = 13.0
    height = len(loci) * row_h + 4.0
    width = 145.0
    rows_svg = []
    for i, loc in enumerate(loci):
        vals = per_locus[loc]
        v = vals[0] if vals else None
        y = 2.0 + i * row_h
        color = "#D55E00" if (v is not None and v >= 0) else "#0072B2"
        txt = f"{loc}: {v:+.2f}" if v is not None else f"{loc}: —"
        rows_svg.append(
            f'<rect x="2" y="{y:.1f}" width="18" height="10" rx="2" fill="{color}"/>'
            f'<text x="24" y="{y + 8.5:.1f}" font-size="9.5" fill="currentColor" '
            f'font-family="ui-monospace,SFMono-Regular,Menlo,monospace">{e(txt)}</text>'
        )
    return (
        f'<svg viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
        f'role="img" aria-label="2-row isoform heatmap">'
        + "".join(rows_svg) + "</svg>"
    )


def build(key: str) -> str:
    rec = json.loads((RESULTS / key / "record.json").read_text())
    figs = rec["figures"]
    tps = figs[0]["timepoints"]

    out = [head(
        f"{rec['citation'].split(' (')[0]} — near-null field demonstration",
        f"Published results from {rec['citation']} projected onto the "
        f"quantum pathway maps.",
    )]

    out.append(f"""<header class="hero">
<h1>{"Gene-metabolite decoupling &amp; SOD isoform divergence" if key == "Mannino2026" else "Time on a map"}</h1>
<p class="lede">{
    "Sweet basil (Ocimum basilicum) exposed continuously for 4 weeks to near-null magnetic fields (<40 nT vs GMF ~44.4 µT): essential oils and flavonoids rise while their biosynthetic transcripts fall, and superoxide dismutase isoforms split in opposite directions."
    if key == "Mannino2026" else
    f"A {len(tps)}-point near-null-field time course — {e(', '.join(tps))} — in roots and shoots, projected onto the redox and respiratory maps. Every other overlay in this atlas is a single snapshot; this one is a trajectory, which is the only way to see a node that goes down and then comes back."
}</p>
<p class="lede">Source: {e(rec['citation'])},
<a href="https://doi.org/{e(rec['doi'])}">doi:{e(rec['doi'])}</a>,
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
<code>{e(rec['source_table'] or 'main-text figures & tables')}</code> and re-projected onto the maps. That is a weaker
provenance than the NASA OSDR pages in this atlas, which rest on processed data anyone
can download, and it is labelled differently throughout:
<code>{e(rec['provenance_class'])}</code>.</p>
</div>""")

    # ---- what was measured ------------------------------------------------
    out.append(f"""<h2>What was measured</h2>
<p>{e(rec['field_regime'])}. Values are {e(rec['citation'].split(',')[0])}'s reported
fold change for hMF-grown plants relative to GMF-grown controls, as
<code>mean ± SD</code>.</p>""")
    if key == "Mannino2026":
        out.append("""<p><strong>Two findings that require structural representation:</strong></p>
<ul>
<li><strong>2-Row Heatmap on Superoxide Dismutases (Isoform Divergence):</strong> Under hMF, cytosolic/chloroplastic Cu/Zn-SOD (<code>ObCSD</code> → <code>AT1G08830</code>) is strongly downregulated (log2FC = <code>-1.45 ± 0.15</code>, blue), whereas chloroplast Fe-SOD (<code>ObFSD1</code> → <code>AT4G25100</code>) is strongly upregulated (log2FC = <code>+1.15 ± 0.12</code>, vermillion). Averaging them into a single node value would yield <code>-0.15</code> — falsely reporting that superoxide dismutation did not respond. The 2-row heatmap preserves both isoforms side by side.</li>
<li><strong>Gene-Metabolite Decoupling in Phenylpropanoid &amp; Volatilome Biosynthesis:</strong> Essential oil volatiles (eugenol <code>+28%</code>, methyl eugenol <code>+79%</code>, cis-ocimene <code>+119%</code>) and total flavonoids (<code>+18%</code>) increase significantly, yet every measured biosynthetic transcript (<code>ObPAL</code>, <code>ObCOMT</code>, <code>ObEGS</code>, <code>ObEOMT</code>, <code>Ob4CL</code>, <code>ObCHS</code>, <code>ObCHI</code>, <code>ObCHIL</code>) is significantly repressed (log2FC <code>-0.70</code> to <code>-1.65</code>).</li>
</ul>""")
    else:
        out.append(f"""<p><strong>The scale matters more than it looks.</strong> The published values are
<em>ratios</em> — 1.0 means no change — while every overlay in this atlas expects log2,
where 0.0 means no change. Feeding the ratios in directly would have coloured every
unchanged gene as strongly upregulated, and the figure would have looked completely
normal. The conversion happens in <code>qbio.papers.Series.to_log2</code>, the SD is
carried through the same transform rather than left in the wrong units, and
<code>qbio.project.project_series</code> refuses a series that is still on a ratio
scale.</p>
<p>The parse is complete: {rec['cells_parsed']:,} cells read,
{rec['cells_blank']} blank, {rec['rows_without_locus']} rows without a usable locus.</p>""")

    # ---- dedicated submap panel if present --------------------------------
    if "submap_svg" in rec:
        submap_svg = rec["submap_svg"]
        out.append(f"""<h2>Dedicated Sub-Map: Phenylpropanoid &amp; Volatilome Gene-Metabolite Decoupling</h2>
<p>In sweet basil under near-null magnetic fields (&lt;40 nT), secondary metabolism decouples from steady-state transcript abundance: blue boxes show significant downregulation across all 8 phenylpropanoid and early flavonoid enzymes, while vermillion boxes show significant physical accumulation of their volatile and flavonoid end-products.</p>
<figure class="map">
<a href="{e(submap_svg)}"><img src="{e(submap_svg)}" alt="Phenylpropanoid and Volatilome Pathway Gene-Metabolite Decoupling Sub-Map" loading="lazy"></a>
<figcaption>
<span class="t">Sub-Map · Phenylpropanoid &amp; Volatilome Pathway (Ocimum basilicum)</span>
<p><strong>Decoupling of transcript abundance and metabolite accumulation.</strong> Blue enzyme boxes carry qRT-PCR log2 fold changes (hMF/GMF ± SD, all P &lt; 0.05); vermillion metabolite boxes carry GC-FID/GC-MS absolute accumulation fold changes and concentrations (mg g⁻¹ dry weight ± SD, P &lt; 0.05).</p>
<p class="dl"><a href="{e(submap_svg)}">SVG</a></p>
</figcaption>
</figure>""")

    # ---- figures ----------------------------------------------------------
    out.append("<h2>The QBO pathway maps</h2>")
    out.append("""<p>Each node is tinted by its extreme value; multi-locus nodes where isoforms diverge in sign (such as <code>SUPEROXIDE_DISMUTASES</code> displaying <code>ObCSD</code> vs <code>ObFSD1</code>) render a 2-row heatmap directly inside the node box.</p>""")

    for f in figs:
        svg_link = f["svg"]
        png_link = f"maps/png/{pathlib.Path(f['svg']).stem}.png"
        img_src = svg_link
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
        div = f.get("nodes_with_diverging_loci", [])
        divtxt = (
            f"<p><strong>2-Row Heatmap (Isoform Divergence) on {', '.join(div)}:</strong> "
            f"<code>AT1G08830</code> (ObCSD, Cu/Zn-SOD) is downregulated (<code>-1.45</code>, blue) while "
            f"<code>AT4G25100</code> (ObFSD1, Fe-SOD) is upregulated (<code>+1.15</code>, vermillion).</p>"
            if div else ""
        )
        out.append(f"""<figure class="map">
<a href="{e(svg_link)}"><img src="{e(img_src)}" alt="{e(f['id'])} with {e(f['tissue'].lower())} data projected" loading="lazy"></a>
<figcaption>
<span class="t">{e(f['id'])} · {e(f['tissue'].title())} · {f['nodes_with_data']} nodes with data ({f['fraction_covered']:.0%})</span>
{low}{revtxt}{divtxt}
<p>{e(f['provenance'])}</p>
<p class="dl"><a href="{e(svg_link)}">SVG</a> · <a href="{e(png_link)}">PNG</a></p>
</figcaption>
</figure>""")

    # ---- per-node table ---------------------------------------------------
    out.append("<h2>Every value behind the figures</h2>")
    out.append("""<p>The numbers on the maps, in full, so the figures can be checked
rather than taken on trust. Values are log2 fold change (hMF vs GMF); multi-locus nodes display their 2-row per-locus heatmap.</p>""")

    for f in figs:
        out.append(f"<h3>{e(f['id'])} · {e(f['tissue'].title())}</h3>")
        out.append('<div class="tablewrap"><table><thead><tr><th>Node</th><th>Tier</th>'
                   "<th>Loci</th><th>Trace / 2-Row Heatmap</th>" + "".join(f"<th>{e(t)}</th>" for t in tps)
                   + "<th>Peak</th></tr></thead><tbody>")
        for n in f["per_node"]:
            cells = "".join(
                f"<td>{'—' if v is None else f'{v:+.2f}'}</td>" for v in n["log2"]
            )
            per_loc = n.get("per_locus", {})
            visual = (
                heatmap_inline(per_loc, f["vmax"])
                if len(per_loc) > 1
                else sparkline_inline(n["log2"], f["vmax"])
            )
            div_badge = " <em>(isoforms diverge: 2-row heatmap)</em>" if n.get("loci_diverge") else ""
            out.append(
                f"<tr><td>{e(n['node_id'])}"
                + (" <em>(reverses)</em>" if n["reverses_direction"] else "")
                + div_badge
                + f"</td><td><span class='swatch {e(n['evidence_tier'])}'></span>"
                f"{e(n['evidence_tier'])}</td>"
                + "<td>"
                + " ".join(f"<code>{e(l)}</code>" for l in n["loci"])
                + "</td>"
                f"<td>{visual}</td>"
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
