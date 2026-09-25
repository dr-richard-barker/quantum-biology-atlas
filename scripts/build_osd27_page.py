#!/usr/bin/env python3
"""
Render `docs/osd27.html` from `results/osd27/record.json`.

The page has an awkward job: the honest result is a null one. Five independent
field-isolating contrasts, good node coverage, and not one node moves the same way in
all five. Writing that up as though something were found would be the easy path and the
wrong one, so the null is the headline and the machinery is what the page demonstrates.
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

RECORD = ROOT / "results" / "osd27" / "record.json"
DOCS = ROOT / "docs"


def signs(by_contrast: dict, labels: list[str]) -> str:
    out = []
    for l in labels:
        c = by_contrast.get(l)
        if c is None:
            out.append('<span class="sg n">·</span>')
        else:
            cls = "up" if c["log2fc"] > 0 else "dn"
            mark = "▲" if c["log2fc"] > 0 else "▼"
            star = "*" if c["significant"] else ""
            out.append(f'<span class="sg {cls}">{mark}{star}</span>')
    return "".join(out)


def build() -> str:
    r = json.loads(RECORD.read_text())
    labels = [c["label"] for c in r["contrasts"]]
    o = r["orthology"]
    pc = r["projection_collapses"]

    total_nodes = sum(len(m["consistency"]) for m in r["maps"].values() if "consistency" in m)
    consistent = sum(
        1 for m in r["maps"].values() if "consistency" in m
        for c in m["consistency"] if c["consistent_direction"] != "mixed"
    )
    biggest = max(
        (abs(c["mean_log2fc"]) for m in r["maps"].values() if "consistency" in m
         for c in m["consistency"]), default=0.0
    )

    out = [head(
        "OSD-27 — Drosophila in a 16.5 T levitation magnet",
        "A plant-anchored quantum ontology projected onto the fly, in a strong-field "
        "study, with a null result reported in full.",
    )]

    out.append(f"""<style>
  .sg {{ display:inline-block; width:1.35em; text-align:center; font-size:.9em; }}
  .sg.up {{ color:#D55E00; }} .sg.dn {{ color:#0072B2; }} .sg.n {{ color:var(--qba-faint); }}
  .ctab td, .ctab th {{ white-space:nowrap; }}
</style>""")

    out.append(f"""<header class="hero">
<h1>A plant ontology on a fly, in a 16.5&nbsp;tesla magnet</h1>
<p class="lede">{e(r['title'])} — NASA OSDR
<a href="https://osdr.nasa.gov/bio/repo/data/studies/OSD-27">OSD-27</a>,
<a href="https://doi.org/{e(r['publication_doi'])}">doi:{e(r['publication_doi'])}</a>.
This is the page where the cross-species machinery does real work, and where it is
easiest to see what that machinery costs.</p>
<ul class="stats">
<li><b>{o['mapped']}/{o['requested']}</b>atlas loci reach the fly</li>
<li><b>{len(labels)}</b>contrasts isolate the field</li>
<li><b>{total_nodes}</b>nodes received data</li>
<li><b>{consistent}</b>move consistently</li>
</ul>
</header>""")

    # ---- the null result, stated first ------------------------------------
    out.append(f"""<div class="note">
<p><strong>The result is null, and that is the finding.</strong> Across
{len(labels)} independent field-isolating contrasts — two sexes, three exposure
durations — <strong>not one of the {total_nodes} nodes with data moves in the same
direction in all five</strong>. The largest mean effect on any node is
{biggest:.3f} log<sub>2</sub> fold change, about a
{(2 ** biggest - 1) * 100:.0f}% change.</p>
<p>This is not a coverage failure. Coverage here is
{', '.join(f"{m['fraction']:.0%} on {mid}" for mid, m in r['maps'].items())} — better
than several pages in this atlas that do show structure. The nodes were measured; they
simply did not agree.</p>
</div>""")

    # ---- reconciling with the original paper -------------------------------
    out.append("""<h2>The original authors report an effect. This page does not contradict them.</h2>
<p>Herranz <em>et al.</em>'s own abstract states that
<em>“a strong magnetic field, of 16.5 Tesla, had a significant effect on the expression
of these genes, independent of the effects associated with magnetically-induced
levitation and hypergravity”</em>. That is a finding about the fly transcriptome. This
page reports a null. Both can be true, and the difference is worth being precise
about:</p>
<ul>
<li><strong>A different gene set.</strong> They analysed the transcriptome. This page
looks only at the handful of fly genes that QBO's <em>Arabidopsis</em> loci reach
through orthology — a small, non-random slice chosen for quantum chemistry, not for
responsiveness.</li>
<li><strong>A different question.</strong> They asked whether the field had a
significant effect. This page asks whether individual QBO nodes move the
<em>same way</em> in all five matched contrasts. A gene can contribute to a real
overall effect while its direction varies between sexes and durations.</li>
<li><strong>A different multiple-testing position.</strong> Significance here is the
adjusted p-value GeneLab computed across the whole array, read per gene. Nothing on this
page re-tests anything.</li>
</ul>
<p>So the honest summary is narrow: <strong>the quantum-chemistry nodes this atlas cares
about are not where that reported effect shows up consistently.</strong> Nothing here
argues the effect is absent.</p>""")

    # ---- what the study is ------------------------------------------------
    out.append(f"""<h2>What this study is, and what it is not</h2>
<p><strong>It is a strong-field study.</strong> Roughly
{r['field_tesla_nominal']}&nbsp;T, against the ~50&nbsp;µT geomagnetic field the review
is about. Those are opposite ends of the same axis, about six orders of magnitude apart.
QBO's <code>field_regimes</code> vocabulary spans both, so the data is in scope — but
nothing here should be read as evidence about near-null fields, and a node that does not
respond at 16.5&nbsp;T has not thereby been shown insensitive at 30&nbsp;nT.</p>

<p><strong>Diamagnetic levitation confounds field with gravity.</strong> Inside the bore,
position determines effective gravity, so 0<em>g</em>*, 1<em>g</em>* and 2<em>g</em>* all
occur at high field. Most of the study's <strong>420 contrasts change field and gravity
together</strong>. Only these {len(labels)} compare the magnet against Earth at matched
effective gravity, duration, temperature and sex:</p>
<div class="tablewrap"><table><thead><tr><th>Duration</th><th>Temperature</th><th>Sex</th></tr></thead><tbody>""")
    for c in r["contrasts"]:
        out.append(f"<tr><td>{e(c['duration'])}</td><td>{e(c['temperature'])}</td>"
                   f"<td>{e(c['sex'])}</td></tr>")
    out.append("</tbody></table></div>")
    out.append("""<p>Every other comparison in the file was excluded. Five contrasts are
five replications of one question, not five results — so the evidence on this page is
whether a node moves the <em>same way</em> across them, not whether it moves at all in
one.</p>""")

    # ---- the orthology bridge ---------------------------------------------
    cry = r["cry1"]
    out.append(f"""<h2>The bridge, and where it lands</h2>
<p>The ontology is anchored on <em>Arabidopsis</em>. Reaching the fly means asking, for
each locus, what the corresponding gene is — here through Ensembl Compara
<code>pan_homology</code>, the only division that crosses kingdoms.
<strong>{o['mapped']} of {o['requested']}</strong> atlas loci map
({o['fraction']:.0%}), {o['one_to_one']} of them one-to-one.</p>
<p><strong>Only one backbone could run.</strong> The committed OrthoDB matrix is
human-anchored and has no <em>Drosophila</em> column, so this projection has no second
method to corroborate it. That is stated rather than left to look like agreement:
<code>{e(', '.join(o['methods_used']))}</code>.</p>
<p>Where it lands is worth seeing on its own. Arabidopsis <strong>CRY1</strong>
(<code>{e(cry['arabidopsis'])}</code>) projects onto <em>Drosophila</em>
<code>{e(', '.join(cry['drosophila']))}</code> — <strong>cry</strong>, the canonical
animal magnetoreceptor — in a dataset where the flies were sitting in a superconducting
magnet. A plant-anchored quantum ontology reaches the one animal gene the
radical-pair literature is built on.</p>""")

    # ---- what projection destroys -----------------------------------------
    out.append("""<h2>What the projection destroys</h2>
<p>An ortholog call is not an identity, and a finished figure gives no sign of how much
of the map's own structure survived the crossing. Two collapses happen here, both real
and neither an error in the orthology — they are true statements about how plant and
fly gene families correspond. They are errors only if left unsaid.</p>""")

    if pc["nodes_sharing_a_target_gene"]:
        out.append("""<p><strong>Distinct nodes landing on the same fly gene.</strong>
When this happens the nodes carry identical numbers, and a reader sees agreement between
independent measurements that are one measurement drawn several times.</p>
<div class="tablewrap"><table><thead><tr><th>Map</th><th>Nodes that collapse together</th>
<th>Shared fly gene(s)</th></tr></thead><tbody>""")
        for c in pc["nodes_sharing_a_target_gene"]:
            out.append(
                f"<tr><td>{e(c['map'])}</td>"
                f"<td>{e(', '.join(c['nodes']))}</td>"
                f"<td>{' '.join(f'<code>{e(g)}</code>' for g in c['target_genes'])}</td></tr>"
            )
        out.append("</tbody></table></div>")
        out.append("""<p>The cryptochrome map is the severe case: <strong>CRY1, CRY2 and
the Trp-triad node all project onto the single fly gene <code>cry</code></strong>. On
QBM-03 the three are distinct entities with different evidence; in the fly they are one
number shown three times. The complex&nbsp;I pair is benign by comparison — the FMN site
is part of complex&nbsp;I, so sharing subunits is what should happen.</p>""")

    if pc["nodes_averaging_many_genes"]:
        out.append("""<p><strong>One node averaging very many fly genes.</strong> A node
standing for one gene and a node standing for forty are not measuring the same kind of
thing, and nothing on the map distinguishes them.</p><ul>""")
        for f in pc["nodes_averaging_many_genes"]:
            out.append(
                f"<li><code>{e(f['node_id'])}</code> on {e(f['map'])} averages "
                f"<strong>{f['n_target_genes']} fly genes</strong>, reached from "
                f"{' '.join(f'<code>{e(l)}</code>' for l in f['loci'])} — largely the "
                f"glutathione S-transferase family. Its value should be read as "
                f"'something in a large family', not as a measurement of the "
                f"ascorbate–glutathione cycle.</li>"
            )
        out.append("</ul>")

    # ---- figures -----------------------------------------------------------
    out.append("<h2>The maps</h2>")
    out.append(f"""<p>One panel per map, showing the first contrast, on a colour scale
fixed across all {len(labels)} so the panels are comparable rather than each
self-normalised. The full per-contrast values are in the table below — the panel is an
illustration, the table is the evidence.</p>""")
    for f in r["figures"]:
        png = f"maps/png/{pathlib.Path(f['svg']).stem}.png"
        fac = f["factors"]
        out.append(f"""<figure class="map">
<a href="{e(f['svg'])}"><img src="{e(f['svg'])}" alt="{e(f['id'])} with the OSD-27 fly data projected" loading="lazy"></a>
<figcaption>
<span class="t">{e(f['id'])} · {e(fac['duration'])}, {e(fac['temperature'])}, {e(fac['sex'])} · {f['nodes_with_data']} nodes ({f['fraction_covered']:.0%})</span>
<p>{e(f['provenance'])}</p>
<p class="dl"><a href="{e(f['svg'])}">SVG</a></p>
</figcaption>
</figure>""")

    # ---- consistency tables ------------------------------------------------
    out.append("<h2>Every node across every contrast</h2>")
    out.append(f"""<p>The actual evidence. ▲ is up in the magnet, ▼ is down, and
<code>*</code> marks significance at adjusted p ≤ {r['alpha']}. A node with five arrows
the same way would be a finding; none has.</p>""")
    short = [f"{c['duration'].replace(' ','')} {c['sex'][:1]}" for c in r["contrasts"]]
    for map_id, m in r["maps"].items():
        if "consistency" not in m:
            continue
        out.append(f"<h3>{e(map_id)} — {m['nodes_with_data']} of {m['addressable']} "
                   f"identifier-bearing nodes ({m['fraction']:.0%})</h3>")
        out.append('<div class="tablewrap"><table class="ctab"><thead><tr>'
                   "<th>Node</th><th>Tier</th><th>Fly genes</th><th>Direction</th>"
                   + "".join(f"<th>{e(s)}</th>" for s in short)
                   + "<th>Mean</th><th>Verdict</th></tr></thead><tbody>")
        for c in m["consistency"]:
            cells = "".join(
                f"<td>{c['by_contrast'][l]['log2fc']:+.3f}"
                + ("*" if c["by_contrast"][l]["significant"] else "")
                + "</td>" if l in c["by_contrast"] else "<td>—</td>"
                for l in labels
            )
            out.append(
                f"<tr><td>{e(c['node_id'])}</td>"
                f"<td><span class='swatch {e(c['evidence_tier'])}'></span>{e(c['evidence_tier'])}</td>"
                f"<td>{c['n_target_genes']}</td>"
                f"<td>{signs(c['by_contrast'], labels)}</td>"
                f"{cells}<td><b>{c['mean_log2fc']:+.3f}</b></td>"
                f"<td>{e(c['consistent_direction'])}</td></tr>"
            )
        out.append('</tbody></table></div><p class="tablenote">Scroll the table '
                   "sideways to see every contrast.</p>")

    # ---- reading it --------------------------------------------------------
    out.append(f"""<h2>How to read a null like this</h2>
<ul>
<li><strong>It does not show the field had no effect.</strong> It shows that these
{total_nodes} nodes, measured on a 2012 microarray through a cross-kingdom ortholog
projection, did not move consistently. Each of those three steps loses signal.</li>
<li><strong>It does not transfer to near-null fields.</strong> 16.5&nbsp;T and
30&nbsp;nT are different regimes, and the mechanisms proposed for each are different.</li>
<li><strong>The confound is handled, not removed.</strong> The {len(labels)} contrasts
match effective gravity, but every one of them is still <em>inside</em> a
16.5&nbsp;T bore, where the flies were also being levitated.</li>
<li><strong>No power analysis is offered here.</strong> The atlas's pre-registered test
reports its own minimum detectable effect; this page does not, so "no consistent
change" should not be read as "no change larger than <em>x</em>".</li>
</ul>

<h2>Reproducing it</h2>
<pre><code>PYTHONPATH=src python3 scripts/build_osd27_showcase.py
PYTHONPATH=src python3 scripts/build_osd27_page.py</code></pre>
<p>The differential-expression table at OSDR is ~623&nbsp;MB across ~1,690 columns.
<code>qbio.osd27</code> streams it a row at a time and keeps only the
{len(labels)}&nbsp;contrasts' columns, so the cached slice is a few hundred KB. Coverage,
per-contrast values and the collapse analysis are written to
<a href="results/osd27/record.json"><code>results/osd27/record.json</code></a>, and this
page is generated from that record.</p>

<footer>
<p><strong>Data.</strong> NASA OSDR <a href="https://osdr.nasa.gov/bio/repo/data/studies/OSD-27">OSD-27</a>,
GeneLab-processed differential expression. Provenance class
<code>{e(r['provenance_class'])}</code>.</p>
<p><strong>Publication.</strong> <a href="https://doi.org/{e(r['publication_doi'])}">doi:{e(r['publication_doi'])}</a>.</p>
<p><a href="index.html">← Quantum Biology Atlas</a></p>
</footer>""")

    out.append(tail())
    return "\n".join(out)


def main() -> int:
    argparse.ArgumentParser().parse_args()
    html = build()
    path = DOCS / "osd27.html"
    path.write_text(html, encoding="utf-8")
    print(f"wrote {path.relative_to(ROOT)} ({len(html) / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
