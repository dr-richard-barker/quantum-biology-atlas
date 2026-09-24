#!/usr/bin/env python3
"""
Render `docs/osd8.html` from `results/osd8/record.json`.

This page carries the atlas's most uncomfortable result, so it leads with it. The QBO
node set is not more responsive to a 16.5 T field than loci drawn at random from the
same array — in any of the seven experimental groups. The maps are shown after that is
said, not before.
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

RECORD = ROOT / "results" / "osd8" / "record.json"
DOCS = ROOT / "docs"


def build() -> str:
    r = json.loads(RECORD.read_text())
    groups = {g["key"]: g for g in r["groups"]}
    primary = groups[r["primary_group"]]
    spec = r["specificity"]
    ps = spec[r["primary_group"]]
    pj = r["platform_join"]
    order = [g["key"] for g in r["groups"]]

    out = [head(
        "OSD-8 — the cleanest field-only contrast, and a specificity test it fails",
        "Arabidopsis at 1g inside and outside a 16.5 T magnet, with non-magnetic "
        "gravity controls, and a permutation test asking whether the atlas's loci "
        "respond at all specially.",
    )]

    out.append(f"""<header class="hero">
<h1>The same gravity, inside and outside the magnet</h1>
<p class="lede">{e(r['title'])} — NASA OSDR
<a href="https://osdr.nasa.gov/bio/repo/data/studies/OSD-8">OSD-8</a>,
<a href="https://doi.org/{e(r['publication_doi'])}">doi:{e(r['publication_doi'])}</a>.
This study declares magnetic field and altered gravity as <em>separate</em> factors and
carries gravity controls that use no magnet at all. One group changes the field and
nothing else — the cleanest such comparison anywhere in this atlas, in the anchor
species, at full coverage.</p>
<ul class="stats">
<li><b>{pj['distinct_loci']:,}</b>loci on the array</li>
<li><b>125/125</b>atlas loci reached</li>
<li><b>{len(r['groups'])}</b>experimental groups</li>
<li><b>1</b>isolates the field</li>
</ul>
</header>""")

    # ---- the headline result ----------------------------------------------
    direction = ("less" if ps["observed_mean_abs_log2fc"] < ps["background_mean"]
                 else "more")
    out.append(f"""<div class="note">
<p><strong>The atlas's loci are not more field-responsive than random loci.</strong>
In the field-isolating contrast, the {ps['n_qbo_loci_measured']} QBO loci move by a mean
|log<sub>2</sub> fold change| of <strong>{ps['observed_mean_abs_log2fc']:.4f}</strong>,
against <strong>{ps['background_mean']:.4f}</strong> for the same number of loci drawn
at random from the other {ps['n_background_loci']:,} on the array
(<strong>p = {ps['p_value']:.3f}</strong>, {ps['permutations']:,} permutations,
one-sided). They move slightly <strong>{direction}</strong>, not more.</p>
<p>And it is not a quirk of one group. The same test in all
{len(r['groups'])} groups — including the two that change gravity with no magnet —
gives p between {min(s['p_value'] for s in spec.values()):.2f} and
{max(s['p_value'] for s in spec.values()):.2f}, never once favouring the atlas's
loci.</p>
</div>""")

    out.append("""<h2>What that does and does not mean</h2>
<ul>
<li><strong>It does not invalidate the ontology.</strong> QBO selects entities for the
quantum chemistry they carry — an unpaired spin, a radical pair, a paramagnetic
cofactor — which is a claim about what <em>could</em> mechanistically respond, not a
prediction that it <em>will</em> respond to 16.5&nbsp;T in callus culture.</li>
<li><strong>It does constrain what a coloured map may be said to show.</strong> On this
dataset, the colours on the figures below are not evidence that the field acts
selectively on these nodes. They show what these nodes did, next to a background that
did as much.</li>
<li><strong>The same pattern appears in the gravity-only controls</strong>, which have no
magnet in them at all. So this is not a statement about magnetism specifically; the QBO
set is simply less variable than the array average in this experiment. A plausible
reason — untested here — is that it is largely core bioenergetic and antioxidant
machinery, which tends to be buffered.</li>
<li><strong>It is a strong-field result.</strong> Like OSD-27, this is tesla-scale, not
the near-null regime the review is about. A locus unmoved at 16.5&nbsp;T has not been
shown unmoved at 30&nbsp;nT.</li>
</ul>""")

    out.append('<div class="tablewrap"><table><thead><tr><th>Group</th><th>What varies</th>'
               "<th>QBO mean |log2FC|</th><th>Random background</th><th>p</th>"
               "</tr></thead><tbody>")
    for k in order:
        g, s = groups[k], spec[k]
        kind = ("<strong>field only</strong>" if g["isolates_field"]
                else "gravity only, no magnet" if g["isolates_gravity"]
                else "field and gravity together")
        out.append(
            f"<tr><td><code>{e(k)}</code></td><td>{kind}</td>"
            f"<td>{s['observed_mean_abs_log2fc']:.4f}</td>"
            f"<td>{s['background_mean']:.4f} ± {s['background_sd']:.4f}</td>"
            f"<td>{s['p_value']:.3f}</td></tr>"
        )
    out.append("</tbody></table></div>")

    # ---- the design --------------------------------------------------------
    out.append(f"""<h2>Why this design is worth the trouble</h2>
<p>Diamagnetic levitation normally confounds field with gravity: position inside the bore
sets effective gravity, so changing one changes the other. This study breaks that
confound twice over. It runs a <strong>1g * point inside the magnet</strong> — where
the magnetic force balances to leave effective gravity at 1g — against a 1g control
outside it, and it reaches µg and 2g <em>without any magnet</em> using a
random-positioning machine and a centrifuge.</p>
<div class="tablewrap"><table><thead><tr><th>Group</th><th>Test</th><th>Reference</th>
<th>Field</th><th>Gravity</th><th>n</th><th>Isolates</th></tr></thead><tbody>""")
    for k in order:
        g = groups[k]
        iso = ("<strong>field</strong>" if g["isolates_field"]
               else "gravity" if g["isolates_gravity"] else "—")
        out.append(
            f"<tr><td><code>{e(k)}</code></td><td>{e(g['test'])}</td>"
            f"<td>{e(g['reference'])}</td>"
            f"<td>{g['field_tesla']:g} T vs {g['reference_field_tesla']:g} T</td>"
            f"<td>{e(g['gravity'])} vs {e(g['reference_gravity'])}</td>"
            f"<td>{g['n_arrays']}</td><td>{iso}</td></tr>"
        )
    out.append("</tbody></table></div>")
    out.append(f"""<p><code>{e(primary['key'])}</code> is the one group where the two
channels differ in field and in <em>nothing else</em>: {primary['field_tesla']:g}&nbsp;T
against {primary['reference_field_tesla']:g}&nbsp;T, both at
{e(primary['gravity'])}. That is computed from the design table rather than asserted, and
the build fails if more or fewer than one group qualifies.</p>""")

    # ---- provenance --------------------------------------------------------
    out.append(f"""<h2>Where the numbers come from, and what they are not</h2>
<p><strong>There is no GeneLab differential expression for this study.</strong> Unlike
OSD-38 and OSD-27, it carries 20 two-colour arrays and a normalized archive with no
contrasts file. The values here are <strong>the depositors' own normalized log
ratios</strong> ({e(r['geo_series'])}), which is a different and weaker provenance:
<code>{e(r['provenance_class'])}</code>.</p>
<p><strong>No model was fitted, so no significance is shown.</strong> Two-colour arrays
are natively ratios; there is no adjusted p-value in the source and none is invented.
Every other overlay in this atlas marks significant nodes with an asterisk. These do not,
deliberately.</p>
<p><strong>The dye swap is already handled — by the depositors.</strong> The arrays
alternate control-on-Cy3 and control-on-Cy5, and GEO's own value definition reads
<em>“{e(r['value_definition'])}”</em>: already oriented test-over-reference regardless of
dye. This matters more than it sounds. Had the column been raw log(Cy5/Cy3) instead,
averaging the replicates in each group would have cancelled real signal toward zero and
produced a clean, entirely false null.</p>
<p><strong>The probe-to-gene join is one extra inferential hop.</strong> The processed
tables key on bare Agilent feature numbers (<code>1</code>, <code>2</code>,
<code>3</code>), so the {e(r['platform'])} platform table is required to reach genes at
all. Its <code>GENE_SYMBOL</code> column carries an AGI locus only sometimes — often a
trivial name like <code>AtATG18b</code> instead — and reading only that column reaches
<strong>17 of the atlas's 125 loci</strong>. The authoritative identifier sits in
<code>ACCESSION_STRING</code> as <code>tair|AT4G30510.1</code>, which reaches
<strong>all 125</strong>. Of {pj['probes']:,} non-control probes,
{pj['probes_with_agi_from_accession_string']:,} get their locus that way,
{pj['probes_with_agi_only_from_gene_symbol']:,} only from the symbol column, and
{pj['probes_without_agi']:,} carry no AGI at all and are dropped.</p>
<p>Multiple probes for one locus are combined by <strong>median</strong> rather than
mean, so a single bad spot on a 45,000-feature array cannot drag a gene with it;
replicate arrays are then combined by mean.</p>""")

    # ---- figures -----------------------------------------------------------
    out.append("<h2>The maps</h2>")
    out.append(f"""<p>The field-isolating contrast on four maps, at
<strong>100% node coverage</strong> — every identifier-bearing node received a value,
which no other page in this atlas achieves. Colour scales are fixed across all
{len(r['groups'])} groups so the panels are comparable. Read them with the specificity
result above in mind.</p>""")
    for f in r["figures"]:
        png = f"maps/png/{pathlib.Path(f['svg']).stem}.png"
        out.append(f"""<figure class="map">
<a href="{e(f['svg'])}"><img src="{e(png)}" alt="{e(f['id'])} with the OSD-8 field-isolating contrast projected" loading="lazy"></a>
<figcaption>
<span class="t">{e(f['id'])} · {e(f['group_label'])} · {f['nodes_with_data']} of {f['nodes_with_data']} nodes ({f['fraction_covered']:.0%})</span>
<p>{e(f['provenance'])}</p>
<p class="dl"><a href="{e(f['svg'])}">SVG</a></p>
</figcaption>
</figure>""")

    # ---- per-node ----------------------------------------------------------
    out.append("<h2>Every node in every group</h2>")
    out.append("""<p>The field-isolating group is the one that matters; the rest are
shown beside it so a node that moves under field-plus-gravity but not under field alone
is visible as such. Values are log<sub>2</sub> fold change, test over reference.</p>""")
    for map_id, m in r["maps"].items():
        out.append(f"<h3>{e(map_id)} — {m['nodes_with_data']} of {m['addressable']} "
                   f"nodes ({m['fraction']:.0%})</h3>")
        out.append('<div class="tablewrap"><table><thead><tr><th>Node</th><th>Tier</th>'
                   + "".join(
                       f"<th>{'<strong>' if groups[k]['isolates_field'] else ''}"
                       f"{e(k)}{'</strong>' if groups[k]['isolates_field'] else ''}</th>"
                       for k in order)
                   + "</tr></thead><tbody>")
        for n in m["nodes"]:
            cells = "".join(
                f"<td>{n['by_group'][k]:+.3f}</td>" if k in n["by_group"] else "<td>—</td>"
                for k in order
            )
            out.append(
                f"<tr><td>{e(n['node_id'])}</td>"
                f"<td><span class='swatch {e(n['evidence_tier'])}'></span>"
                f"{e(n['evidence_tier'])}</td>{cells}</tr>"
            )
        out.append('</tbody></table></div><p class="tablenote">Scroll the table '
                   "sideways to see every group.</p>")

    # ---- reproducing -------------------------------------------------------
    out.append(f"""<h2>Reproducing it</h2>
<pre><code>PYTHONPATH=src python3 scripts/build_osd8_showcase.py
PYTHONPATH=src python3 scripts/build_osd8_page.py</code></pre>
<p>The permutation test is seeded (<code>{ps['seed']}</code>) and runs
{ps['permutations']:,} draws, so the p-values above reproduce exactly. The design table,
the platform join report, per-group specificity and every per-node value are written to
<a href="results/osd8/record.json"><code>results/osd8/record.json</code></a>, and this
page is generated from that record.</p>

<footer>
<p><strong>Data.</strong> NASA OSDR <a href="https://osdr.nasa.gov/bio/repo/data/studies/OSD-8">OSD-8</a>
/ GEO <a href="https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc={e(r['geo_series'])}">{e(r['geo_series'])}</a>,
platform <a href="https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc={e(r['platform'])}">{e(r['platform'])}</a>.
Provenance class <code>{e(r['provenance_class'])}</code> — the depositors' normalized
ratios, not a NASA pipeline output, and no model fitted.</p>
<p><strong>Publication.</strong> <a href="https://doi.org/{e(r['publication_doi'])}">doi:{e(r['publication_doi'])}</a>.</p>
<p><a href="index.html">← Quantum Biology Atlas</a></p>
</footer>""")

    out.append(tail())
    return "\n".join(out)


def main() -> int:
    argparse.ArgumentParser().parse_args()
    html = build()
    path = DOCS / "osd8.html"
    path.write_text(html, encoding="utf-8")
    print(f"wrote {path.relative_to(ROOT)} ({len(html) / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
