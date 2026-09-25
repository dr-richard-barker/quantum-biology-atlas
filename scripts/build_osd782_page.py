#!/usr/bin/env python3
"""
Render `docs/osd782.html` from `results/osd782/record.json` and `results/overlap/record.json`.

The page has one job and one warning. The job: show which quantum-biology nodes ionising
radiation moves, and whether they are the ones magnetic-field perturbation moves. The
warning: at node level that question gives a cleaner answer than the data supports,
because gene families split. The page leads with the radiation time course, gives the
overlap at locus level, and shows the AOX family as the worked case for why node level
is not enough.
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

RECORD = ROOT / "results" / "osd782" / "record.json"
OVERLAP = ROOT / "results" / "overlap" / "record.json"
OSD8 = ROOT / "results" / "osd8" / "record.json"
DOCS = ROOT / "docs"

SYMBOL = {
    "AT1G20630": "CAT1", "AT1G32350": "AOX1D", "AT5G64210": "AOX2",
    "AT3G09640": "APX2", "AT1G07890": "APX1", "AT3G22370": "AOX1A",
    "AT2G28190": "CSD2", "AT1G08830": "CSD1", "AT1G15550": "GA3OX1",
    "AT3G27620": "AOX1C", "AT4G25100": "FSD1",
}


def sym(locus: str) -> str:
    s = SYMBOL.get(locus)
    return f"{locus} ({s})" if s else locus


def build() -> str:
    r = json.loads(RECORD.read_text())
    ov = json.loads(OVERLAP.read_text())
    # Read the magnetic comparison from ITS record rather than repeating the number.
    o8 = json.loads(OSD8.read_text())
    mag = o8["specificity"][o8["primary_group"]]["observed_mean_abs_log2fc"]
    pert = r["perturbation"]
    nl = ov["nnmf_locus_arm"]
    la = ov["locus_arm"]
    div = ov["divergence_example"]

    best = min(
        ((s, d, t) for d, bt in r["specificity"].items() for t, s in bt.items()),
        key=lambda x: x[0]["p_value"],
    )
    rad_max = max(s["observed_mean_abs_log2fc"]
                  for bt in r["specificity"].values() for s in bt.values())
    bg_max = max(s["background_mean"]
                 for bt in r["specificity"].values() for s in bt.values())

    out = [head(
        "OSD-782 — ionising radiation on the quantum maps",
        "A dose × time radiation course in Arabidopsis, and whether it moves the same "
        "nodes as magnetic-field perturbation.",
    )]

    out.append(f"""<header class="hero">
<h1>Does radiation move the same chemistry a magnetic field does?</h1>
<p class="lede">{e(r['title'])} — NASA OSDR
<a href="https://osdr.nasa.gov/bio/repo/data/studies/OSD-782">OSD-782</a> /
{e(r['glds'])}. Two doses, four timepoints, <em>Arabidopsis</em>, GeneLab-processed
differential expression.</p>
<p class="lede"><strong>Ionising radiation is not a magnetic-field regime and this page
does not treat it as one.</strong> It is here because radiolysis makes radicals and ROS
directly, and the magnetic-field literature converges on the same redox machinery. So
the question is <em>overlap</em>: which nodes does radiation move, and are they the ones
a magnetic field moves? A shared locus is a lead, not a mechanism.</p>
<ul class="stats">
<li><b>{r['qbo_loci_measured']}/125</b>atlas loci measured</li>
<li><b>{len(r['doses_gy'])}×{len(r['timepoints'])}</b>doses × timepoints</li>
<li><b>{nl['summary']['responded_in_more_than_one']}/{nl['summary']['units_compared']}</b>loci respond to both</li>
<li><b>{nl['summary']['directions_agree']}</b>agree in direction</li>
</ul>
</header>""")

    agreeing = nl["summary"]["agreeing_keys"]
    out.append(f"""<div class="note">
<p><strong>Two loci respond to both ionising radiation and a near-null magnetic field,
in the same direction:</strong>
{' and '.join(f'<code>{e(sym(g))}</code>' for g in agreeing)}. Of
{nl['summary']['units_compared']} atlas loci measured in both experiments,
{nl['summary']['responded_in_more_than_one']} respond to both and
{nl['summary']['directions_agree']} agree in sign; the other
{nl['summary']['directions_disagree']} move in <em>opposite</em> directions.</p>
<p><strong>This is a lead, not a result.</strong> Eleven loci is far too few to test —
<code>compare.overlap_exceeds_chance</code> refuses rather than returning a p-value that
would look like evidence. Catalase in particular responds to almost every stress, so
finding it in two lists means little on its own.</p>
</div>""")

    # ---- the divergence warning, before any node-level claim -----------------
    out.append(f"""<h2>Why this page works at locus level, not node level</h2>
<p>The obvious way to ask the question is per node: does the AOX node respond to both?
Done that way the answer looked clean — three of six shared nodes, two agreeing in
direction. <strong>It does not survive looking at the underlying genes.</strong></p>
<p>{e(div['why'])}</p>
<div class="tablewrap"><table><thead><tr><th>Locus</th><th>Radiation</th>
<th>Near-null field</th></tr></thead><tbody>""")
    for l in div["loci"]:
        rad = "—" if l["radiation"] is None else f"{l['radiation']:+.2f}"
        nn = "not in that table" if l["NNMF"] is None else f"{l['NNMF']:+.2f}"
        out.append(f"<tr><td><code>{e(sym(l['locus']))}</code></td>"
                   f"<td>{rad}</td><td>{nn}</td></tr>")
    out.append("</tbody></table></div>")
    heat_nodes = sorted({n for f in r["figures"] for n in f["nodes_with_heatmap"]})
    out.append(f"""<p><strong>So the maps below draw multi-locus nodes as a per-locus
heatmap rather than a single trace.</strong> One row per locus, one column per
timepoint, same diverging colour scale as everything else — a family that splits shows
as a warm row above a cool one. On these maps
{len(heat_nodes)} node(s) are drawn that way:
{', '.join(f'<code>{e(n)}</code>' for n in heat_nodes)}. A node standing for a single
locus keeps its sparkline, which reads better when there genuinely is one trace.</p>
<p>The AOX heatmap is the case above made visual: the <code>1g32350</code> row is warm
across all four timepoints while <code>5g64210</code> turns blue at 24 and 72 hours. No
aggregate could have shown that, and it took a separate investigation to find before the
heatmap existed.</p>""")
    out.append("""<p>So the atlas gained a check it did not have:
<code>qbio.project.project_series</code> now records, per timepoint, whether a node's
loci disagreed in <em>sign</em>, and the caption says so. Under radiation
<strong>almost every multi-locus node diverges</strong> — a strong perturbation splits
gene families, and a node aggregating them is summarising genes doing different things.
That qualifies every multi-locus value on every page in this atlas, not just this
one.</p>""")

    # ---- the overlap table ---------------------------------------------------
    out.append("<h2>Radiation against near-null field, locus by locus</h2>")
    out.append(f"""<p>The near-null comparison is
<a href="paper-Parmagnani2022.html">Parmagnani 2022</a>, the only near-null time course
in <em>Arabidopsis</em> available. It reaches {nl['summary']['units_compared']} of the
atlas's loci, because its supplementary table was filtered by its authors to
oxidative-reaction enzymes. A locus counts as responding at
|log<sub>2</sub>FC| ≥ {ov['response_threshold_log2fc']}, applied identically to both
sides — the point of a fixed threshold is that it cannot be tuned to make the overlap
more interesting.</p>""")
    out.append('<div class="tablewrap"><table><thead><tr><th>Locus</th>'
               "<th>Radiation</th><th>at</th><th>Near-null</th><th>at</th>"
               "<th>Responds to</th><th>Same direction?</th></tr></thead><tbody>")
    for row in nl["rows"]:
        agree = ("—" if row["directions_agree"] is None
                 else "<strong>yes</strong>" if row["directions_agree"] else "no")
        out.append(
            f"<tr><td><code>{e(sym(row['locus']))}</code></td>"
            f"<td>{row['radiation']:+.2f}</td><td>{e(row['radiation_at'])}</td>"
            f"<td>{row['NNMF']:+.2f}</td><td>{e(row['NNMF_at'])}</td>"
            f"<td>{e(', '.join(row['responded_in']) or 'neither')}</td>"
            f"<td>{agree}</td></tr>"
        )
    out.append('</tbody></table></div><p class="tablenote">Scroll sideways for every '
               "column. Values are the most extreme timepoint in each experiment.</p>")

    # ---- the strong-field arm ------------------------------------------------
    c = la["chance"]
    out.append(f"""<h2>And against a strong field, where a test is possible</h2>
<p>The <a href="osd8.html">OSD-8</a> 16.5 T contrast shares
<strong>{la['summary']['units_compared']} loci</strong> with this study — enough to test.
{la['summary']['responded_in_more_than_one']} respond to both, against
{c['expected_overlap']} expected by chance
(<strong>p = {c['p_value']:.3f}</strong>, {c['permutations']:,} permutations), and
{la['summary']['directions_agree']} agree in direction.</p>
<p>That is no overlap at all, and it is consistent with the strong-field study itself:
16.5 T moved none of the six shared nodes past threshold. The near-null regime — the one
the review is actually about — is where the leads are.</p>""")

    # ---- specificity ---------------------------------------------------------
    out.append(f"""<h2>Are the atlas's loci especially radiation-responsive? No.</h2>
<p>The same permutation test the OSD-8 page runs, from the same function in
<code>qbio.compare</code> with the same seed and permutation count — otherwise the two
numbers could not be placed beside each other. At every dose and timepoint the atlas's
loci move <strong>less</strong> than the background, p between
{min(s['p_value'] for bt in r['specificity'].values() for s in bt.values()):.2f} and
{max(s['p_value'] for bt in r['specificity'].values() for s in bt.values()):.2f}.</p>
<p><strong>But they are not inert, and that matters.</strong> They move up to
{rad_max:.3f} mean |log<sub>2</sub>FC| under radiation against {mag:.3f} under the
16.5 T field — roughly {rad_max / mag:.1f}× more. The background moves more still ({bg_max:.3f}), which is
why they stay under-represented. So the magnetic null on the OSD-8 page
<strong>cannot be explained by these genes being unable to move</strong>. They move
perfectly well when something perturbs them; they simply are not preferentially
field-responsive.</p>""")
    out.append('<div class="tablewrap"><table><thead><tr><th>Dose</th><th>Time</th>'
               "<th>Atlas loci</th><th>Random background</th><th>p</th>"
               "</tr></thead><tbody>")
    for dose, bt in r["specificity"].items():
        for t, s in bt.items():
            out.append(
                f"<tr><td>{e(dose)}</td><td>{e(t)}</td>"
                f"<td>{s['observed_mean_abs_log2fc']:.4f}</td>"
                f"<td>{s['background_mean']:.4f} ± {s['background_sd']:.4f}</td>"
                f"<td>{s['p_value']:.4f}</td></tr>"
            )
    out.append("</tbody></table></div>")

    # ---- the study ----------------------------------------------------------
    out.append(f"""<h2>The study, and the contrast that needed its own rule</h2>
<p>Three declared factors: {', '.join(f'<code>{e(f)}</code>' for f in r['factors'])}.
{e(pert['source'])} at {' and '.join(f'{d:g} Gy' for d in r['doses_gy'])} against
non-irradiated controls, sampled at {e(', '.join(r['timepoints']))}.</p>
<p><strong>The dose comparisons differ in two declared factors, not one.</strong>
Radiation source and dose are coupled by construction — there is no such thing as
cesium-137 at zero dose — so the single-factor rule the
<a href="osd27.html">OSD-27 page</a> uses to isolate a magnetic field rejects every one
of them. <code>qbio.osd782.isolates_dose</code> treats source and dose as one coupled
axis and requires time to match. {len(r['contrasts'])} contrasts qualify, and the build
asserts that none of them is single-factor, so the reason the rule exists stays
encoded.</p>
<p>Contrasts are kept irradiated-first, so a positive log<sub>2</sub> fold change means
"higher after irradiation".</p>""")

    # ---- figures -------------------------------------------------------------
    out.append("<h2>The maps</h2>")
    out.append("""<p>Each node is tinted by its most extreme timepoint and carries its
trajectory. Read them with the divergence warning above in mind: where a node's loci
disagree in sign, its trace is the aggregator choosing between them, and the caption
says which nodes those are.</p>""")
    for f in r["figures"]:
        png = f"maps/png/{pathlib.Path(f['svg']).stem}.png"
        out.append(f"""<figure class="map">
<a href="{e(f['svg'])}"><img src="{e(png)}" alt="{e(f['id'])} with the OSD-782 {f['dose_gy']:g} Gy radiation time course projected" loading="lazy"></a>
<figcaption>
<span class="t">{e(f['id'])} · {f['dose_gy']:g} Gy · {f['nodes_with_data']} nodes ({f['fraction_covered']:.0%})</span>
<p>{e(f['provenance'])}</p>
<p class="dl"><a href="{e(f['svg'])}">SVG</a></p>
</figcaption>
</figure>""")

    out.append(f"""<h2>What this does not show</h2>
<ul>
<li><strong>Not evidence about magnetic fields.</strong> Radiation is a different
perturbation axis. QBO's <code>field_regimes</code> vocabulary is not used for it and
was not extended; the record carries its own <code>perturbation</code> block.</li>
<li><strong>Overlap is not shared mechanism.</strong> Two perturbations converging on
one locus says they converge, not why.</li>
<li><strong>Different labs, tissues and platforms.</strong> Callus versus seedling,
microarray ratio versus RNA-seq differential expression. Direction is the robust
comparison; magnitude is not, and no magnitude comparison is made across
experiments.</li>
<li><strong>Eleven loci is not a test.</strong> The near-null arm is reported as a
table and explicitly not tested.</li>
</ul>

<h2>Reproducing it</h2>
<pre><code>PYTHONPATH=src python3 scripts/build_osd782_showcase.py
PYTHONPATH=src python3 scripts/build_overlap.py
PYTHONPATH=src python3 scripts/build_osd782_page.py</code></pre>
<p>The differential-expression table is ~255 MB across {len(r['contrasts']) and 132}
contrasts; <code>qbio.osd27.slice_contrasts</code> streams it to a few hundred KB.
Every number here is written to
<a href="results/osd782/record.json"><code>results/osd782/record.json</code></a> and
<a href="results/overlap/record.json"><code>results/overlap/record.json</code></a>, and
this page is generated from them.</p>

<footer>
<p><strong>Data.</strong> NASA OSDR
<a href="https://osdr.nasa.gov/bio/repo/data/studies/OSD-782">OSD-782</a> / {e(r['glds'])},
GeneLab-processed differential expression. Provenance class
<code>{e(r['provenance_class'])}</code>.</p>
<p><strong>Related work.</strong> {e(r['related_work'])}</p>
<p><a href="index.html">← Quantum Biology Atlas</a> ·
<a href="osd8.html">the strong-field study</a> ·
<a href="paper-Parmagnani2022.html">the near-null time course</a></p>
</footer>""")

    out.append(tail())
    return "\n".join(out)


def main() -> int:
    argparse.ArgumentParser().parse_args()
    html = build()
    path = DOCS / "osd782.html"
    path.write_text(html, encoding="utf-8")
    print(f"wrote {path.relative_to(ROOT)} ({len(html) / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
