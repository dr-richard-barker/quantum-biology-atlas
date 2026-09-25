#!/usr/bin/env python3
"""
Render `docs/explore.html` — project your own expression data onto a quantum pathway map.

The site's first JavaScript page. `index.html` and the demonstration pages stay
script-free; the interactive work is quarantined here.

Generated rather than hand-written so the map list comes from the catalogue and the
species list from `catalog/orthologs.json`. A hard-coded dropdown would drift the moment
a map is added, and would offer species the ortholog map cannot actually reach.

**The refusals are the point.** `qbio.project` refuses an empty join and refuses below
25% coverage, because a pale map rendered from nothing looks like a result and is the
worst failure available. `docs/assets/qbm-explore.js` ports both, and this page makes
them visible rather than logging them to a console nobody opens.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from build_site import e, head  # noqa: E402

DOCS = ROOT / "docs"
EXAMPLE = "example-data/OSD-8_MAG-1g_field-contrast.csv"


def build() -> str:
    manifest = json.loads((ROOT / "catalog" / "manifest.json").read_text())
    orthologs = json.loads((ROOT / "catalog" / "orthologs.json").read_text())
    species = orthologs["species"]
    t = manifest["totals"]

    map_options = "\n".join(
        f'<option value="{e(m["id"])}">{e(m["id"])} — {e(m["title"])}</option>'
        for m in manifest["maps"]
    )
    species_options = "\n".join(
        f'<option value="{e(k)}">{e(v["common_name"].title())} '
        f'({v["mapped"]}/{v["requested"]} loci mapped)</option>'
        for k, v in sorted(species.items(), key=lambda kv: -kv[1]["mapped"])
    )

    out = [head(
        "Explore — project your own data onto a quantum pathway map",
        "Drop a differential-expression table and see it on the atlas's maps. Runs "
        "entirely in your browser; nothing is uploaded.",
    )]

    out.append("""<style>
  .drop { border:2px dashed var(--qba-rule); border-radius:14px; padding:34px 20px;
    text-align:center; background:var(--qba-card); transition:border-color .15s,background .15s; }
  .drop.over { border-color:var(--qba-accent); background:var(--qba-card2); }
  .drop input[type=file] { display:none; }
  .btn { display:inline-block; border:1px solid var(--qba-rule); background:var(--qba-bg);
    color:var(--qba-ink); border-radius:9px; padding:9px 16px; font:inherit; font-size:.92rem;
    cursor:pointer; }
  .btn:hover { border-color:var(--qba-accent); color:var(--qba-accent); }
  .btn.primary { background:var(--qba-accent); color:#fff; border-color:var(--qba-accent); }
  .controls { display:flex; flex-wrap:wrap; gap:14px; margin:20px 0; align-items:flex-end; }
  .controls label { display:block; font-size:.8rem; color:var(--qba-soft);
    text-transform:uppercase; letter-spacing:.05em; margin-bottom:5px; font-weight:650; }
  .controls select, .controls input { font:inherit; font-size:.92rem; padding:7px 9px;
    border:1px solid var(--qba-rule); border-radius:8px; background:var(--qba-bg);
    color:var(--qba-ink); max-width:100%; }
  .msg { border-radius:0 8px 8px 0; padding:12px 16px; margin:18px 0;
    border-left:3px solid var(--qba-rule); background:var(--qba-card); }
  .msg.err  { border-left-color:#D55E00; }
  .msg.warn { border-left-color:#E69F00; }
  .msg.ok   { border-left-color:#009E73; }
  .msg h4 { margin:0 0 6px; font-size:1rem; }
  .msg p, .msg ul { margin:6px 0; font-size:.92rem; }
  .cov { display:flex; flex-wrap:wrap; gap:10px; margin:14px 0 0; padding:0; list-style:none; }
  .cov li { background:var(--qba-bg); border:1px solid var(--qba-rule); border-radius:9px;
    padding:7px 12px; font-size:.85rem; }
  .cov b { display:block; font-size:1.1rem; }
  #stage { margin-top:22px; border:1px solid var(--qba-rule); border-radius:12px;
    overflow:hidden; background:var(--qba-bg); }
  #stage svg { width:100%; height:auto; display:block; }
  #stage:empty { display:none; }
  .hint { font-size:.85rem; color:var(--qba-soft); }
  details.diag { margin-top:10px; font-size:.88rem; }
  details.diag summary { cursor:pointer; color:var(--qba-accent); }
  details.diag code { font-size:.85em; }
</style>""")

    out.append(f"""<header class="hero">
<h1>Put your own data on the maps</h1>
<p class="lede">Drop a differential-expression table — CSV or TSV, an identifier column
and a log<sub>2</sub> fold change — and see it projected onto any of the atlas's
{t['maps']} maps. If it is not <em>Arabidopsis</em>, the orthology runs too.</p>
<p class="lede"><strong>Nothing is uploaded.</strong> The file is read in your browser,
joined against the catalogue that ships with this site, and drawn. That is a deliberate
property, not an accident of hosting: unpublished data should not have to leave your
machine to be looked at.</p>
</header>

<div class="drop" id="drop">
  <p><strong>Drop a CSV or TSV here</strong>, or
    <label class="btn" for="file">choose a file</label>
    <input type="file" id="file" accept=".csv,.tsv,.txt,text/csv,text/tab-separated-values">
  </p>
  <p class="hint">Never leaves your browser. No file size limit beyond your own memory.</p>
  <p><button class="btn" id="demo" type="button">Load a real example instead</button></p>
  <p class="hint">The example is the OSD-8 field-isolating contrast — 1g inside a
    16.5&nbsp;T magnet against 1g outside it, 2,125 <em>Arabidopsis</em> loci.
    <a href="osd8.html">What that study is</a>.</p>
</div>

<div class="controls">
  <div><label for="map">Map</label>
    <select id="map">{map_options}</select></div>
  <div><label for="species">Your data's species</label>
    <select id="species">
      <option value="arabidopsis_thaliana" selected>Arabidopsis thaliana (no projection needed)</option>
      {species_options}
    </select></div>
  <div><label for="agg">Multi-locus nodes</label>
    <select id="agg">
      <option value="extreme">Largest change</option>
      <option value="mean" selected>Mean</option>
      <option value="median">Median</option>
    </select></div>
  <div><label for="alpha">Significance α</label>
    <input type="number" id="alpha" value="0.05" min="0" max="1" step="0.01" style="width:7em"></div>
  <div><button class="btn primary" id="go" type="button">Project</button></div>
</div>

<div id="report"></div>
<div id="stage"></div>""")

    out.append(f"""<h2>What it does with your file</h2>
<p><strong>It detects the identifier namespace rather than asking.</strong> The commonest
silent failure in a tool like this is a user uploading Ensembl ids against an AGI-keyed
map: everything misses, a blank map renders, and it looks like a finding. Here the column
that looks most like identifiers is chosen by content, the namespace is named back to
you, and a namespace that cannot reach the species you picked is an error rather than an
empty result.</p>
<p><strong>It refuses rather than drawing something meaningless.</strong> A join that
matches nothing stops with an explanation. Below {t['maps'] and 25}% coverage it warns
loudly and states the number. Both rules are ported from
<code>qbio.project.project_expression</code>, which the generated figures on this site go
through, so an overlay you make here obeys the same discipline as one in the repository.</p>
<p><strong>It shows what it could not do.</strong> Nodes with no gene identifier at all,
nodes whose loci are absent from your table, and — for a cross-species run — loci with no
ortholog in your species are counted separately, because they are different problems.</p>
<p><strong>Colour means the same thing as everywhere else in the atlas.</strong>
Okabe-Ito vermillion above zero, blue below, transparent at no change, and the evidence
tier still shows as the border style. A dashed node is a hypothesis whatever your data
says about it.</p>

<h2>What it cannot tell you</h2>
<ul>
<li><strong>That a coloured node is field-sensitive.</strong> The atlas's own
<a href="osd8.html">specificity test</a> found its loci respond no more than random loci
on the same array. Colour shows what your data did at these nodes, not that these nodes
are special.</li>
<li><strong>Anything about statistical power.</strong> No test is run here. If your table
has an adjusted p-value column it is used to mark nodes at your chosen α and nothing
more.</li>
<li><strong>That an ortholog call is an identity.</strong> Cross-species projection
collapses distinctions — on the cryptochrome map, three nodes land on a single fly gene.
The coverage report names the method; the <a href="osd27.html">fly page</a> shows what
that costs.</li>
</ul>

<h2>Expected format</h2>
<pre><code>locus,log2FoldChange,padj
AT1G07890,-1.09,0.004
AT1G20630,0.94,0.21</code></pre>
<p class="hint">Tab-separated works too, and the delimiter is sniffed. The identifier and
value columns are detected, so column order and extra columns do not matter. A column
named like <code>log2FoldChange</code> is preferred over an unnamed numeric one; an
adjusted-p column is optional. Recognised namespaces: Arabidopsis AGI, FlyBase, Ensembl,
WormBase and SGD systematic names.</p>

<footer>
<p><a href="index.html">← Quantum Biology Atlas</a></p>
</footer>

<script type="module" src="assets/qbm-explore-ui.js"></script>
</div>
</body>
</html>
""")
    return "\n".join(out)


def main() -> int:
    argparse.ArgumentParser().parse_args()
    html = build()
    path = DOCS / "explore.html"
    path.write_text(html, encoding="utf-8")
    print(f"wrote {path.relative_to(ROOT)} ({len(html) / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
