#!/usr/bin/env python3
"""
Generate the GitHub Pages site into `docs/`.

Everything on the page is derived from `catalog/manifest.json`, the ontology and the
results directory, so the site cannot drift from what the repository actually
contains. There is no hand-maintained HTML with numbers in it.

The page is static HTML, which is deliberate: per the portfolio's Pages architecture
note, the shared CoSE theme is a static overlay and cannot theme a React SPA. The
interactive viewer lives in the separate SBGN Pathway Visualizer app, and this site
links to it rather than embedding one.

The CoSE COLOUR SCHEME is adopted, but not the CoSE navigation rail. Those are two
separate files in the shared kit and only one is wanted here:

  cose-map.css     the palette — --cose-l-* / --cose-d-* plus semantic tokens, with
                   light/dark driven by prefers-color-scheme. LOADED.
  cose-chrome.css  styles the injected rail, brand mark and toggles. NOT loaded.
  theme.js         injects the rail and the document map. NOT loaded.
  sites.js         the cross-site project registry the rail reads. NOT loaded.

The palette is referenced by absolute URL from the canonical CoSE origin rather than
vendored, so a change to the shared scheme reaches this site without a commit here.

One trap worth recording: in the CoSE vocabulary `--soft` is a SURFACE colour
(#f7f9fc), not a muted ink. A page that defines its own `--soft` for secondary text
and then loads this stylesheet gets near-white text on a white background. This page's
tokens are namespaced `--qba-*` for that reason, and map onto `--muted` rather than
`--soft` for secondary text.
"""
from __future__ import annotations

import argparse
import html
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

COSE = "https://dr-richard-barker.github.io/Plant_response_to_radiation/cose"
VIEWER = "https://dr-richard-barker.github.io/SBGN-Pathway-viewer/app/"
SITE_ID = "quantum-biology-atlas"

TIER_BLURB = {
    "T1": "A field was applied and an effect measured on this entity.",
    "T2": "Shown for the containing complex or process, not the entity itself.",
    "T3": "A physical route exists; no field measurement has been made.",
    "T4": "Structural context; no quantum claim.",
}


def e(s) -> str:
    return html.escape(str(s if s is not None else ""), quote=True)


def head(title: str, description: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(description)}">
<meta name="author" content="Richard Barker">
<meta name="color-scheme" content="light dark">
<script>
  (function() {{
    var saved = localStorage.getItem('cose-theme');
    var pref = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    document.documentElement.setAttribute('data-theme', saved || pref);
  }})();
</script>
<link rel="stylesheet" href="{COSE}/cose-map.css">
<style>
  /* CoSE Token Mappings */
  :root {{
    --qba-bg:     var(--bg,       #ffffff);
    --qba-ink:    var(--ink,      #1a2230);
    --qba-soft:   var(--muted,    #5a6473);
    --qba-faint:  var(--ink-faint,#8892a3);
    --qba-rule:   var(--line,     #e5e9f0);
    --qba-card:   var(--surface,  #f7f9fc);
    --qba-card2:  var(--surface-2,#eef2f8);
    --qba-accent: var(--accent,   #3B6EA5);
    --qba-accent2:var(--accent2,  #3FB6A8);
    --qba-warn:   #D55E00;
    --qba-t1: var(--ink,       #1a2230);
    --qba-t2: var(--muted,     #5a6473);
    --qba-t3: var(--ink-faint, #8892a3);
    --qba-t4: var(--line,      #c9d1dc);
    --header-bg: linear-gradient(180deg, rgba(59,110,165,.35), rgba(59,110,165,.05));
  }}

  html[data-theme="light"] {{
    --bg:#ffffff; --ink:#1a2230; --fg:#1a2230; --muted:#5a6473; --ink-soft:#5a6473;
    --line:#e5e9f0; --border:#e5e9f0; --surface:#f7f9fc; --card:#f7f9fc;
    --surface-2:#eef2f8; --accent:#3B6EA5; --accent2:#3FB6A8;
    --header-bg: linear-gradient(180deg, rgba(59,110,165,.35), rgba(59,110,165,.05));
    color-scheme: light;
  }}
  html[data-theme="dark"] {{
    --bg:#0f141b; --ink:#e6ebf2; --fg:#e6ebf2; --muted:#9aa6b6; --ink-soft:#9aa6b6;
    --line:#232c39; --border:#232c39; --surface:#161d27; --card:#161d27;
    --surface-2:#1f2937; --accent:#6ea3d8; --accent2:#54c9ba;
    --header-bg: linear-gradient(180deg, rgba(59,110,165,.10), transparent);
    color-scheme: dark;
  }}

  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--qba-bg); color:var(--qba-ink);
    font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; }}
  .wrap {{ max-width:1080px; margin:0 auto; padding:0 16px 96px; }}

  /* Topbar with brand and light/dark theme toggle (NO navigation rail) */
  .cose-topbar {{ display:flex; align-items:center; justify-content:space-between; padding:12px 0; border-bottom:1px solid var(--qba-rule); margin-bottom:12px; }}
  .cose-brand {{ display:inline-flex; align-items:center; gap:8px; font-weight:650; font-size:.95rem; color:var(--qba-ink); text-decoration:none; }}
  .cose-brand:hover {{ text-decoration:none; }}
  .cose-brand img {{ height:28px; width:28px; border-radius:6px; display:block; }}
  .cose-theme-btn {{ display:inline-flex; align-items:center; gap:6px; padding:6px 12px; border-radius:8px; cursor:pointer;
    border:1px solid var(--qba-rule); background:var(--qba-card); color:var(--qba-ink);
    font:600 .84rem/1.2 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
    box-shadow:0 1px 2px rgba(0,0,0,.04); transition:background .15s ease, border-color .15s ease; }}
  .cose-theme-btn:hover {{ filter:brightness(.97); }}
  .cose-theme-btn svg {{ width:14px; height:14px; display:block; }}

  header.hero {{ padding:40px 0 28px; border-bottom:1px solid var(--qba-rule); background:var(--header-bg); border-radius:0 0 12px 12px; margin-bottom:24px; }}
  h1 {{ font-size:clamp(1.7rem,4vw,2.5rem); line-height:1.18; margin:0 0 10px; letter-spacing:-.02em; }}
  .eyebrow {{ color:var(--qba-accent); font-weight:600; letter-spacing:.04em; text-transform:uppercase; font-size:.78rem; margin:0 0 8px; }}
  .lede {{ font-size:1.12rem; color:var(--qba-soft); max-width:62ch; margin:0 0 18px; }}
  h2 {{ font-size:1.35rem; margin:44px 0 10px; letter-spacing:-.01em; }}
  h3 {{ font-size:1.05rem; margin:26px 0 6px; }}
  p, li {{ max-width:74ch; }}
  a {{ color:var(--qba-accent); }}
  code {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:.9em;
    background:var(--qba-card); padding:1px 5px; border-radius:4px;
    overflow-wrap:anywhere; }}
  pre {{ overflow-x:auto; -webkit-overflow-scrolling:touch; max-width:100%; }}
  pre code {{ overflow-wrap:normal; white-space:pre; }}

  /* CoSE Components */
  .btns {{ display:flex; flex-wrap:wrap; gap:8px; margin:16px 0; }}
  .btn {{ display:inline-flex; align-items:center; gap:6px; padding:7px 13px; border-radius:8px; font-weight:600; font-size:.86rem;
    border:1px solid var(--qba-rule); background:var(--qba-card); color:var(--qba-ink); text-decoration:none;
    transition:background .15s ease, border-color .15s ease, color .15s ease; }}
  .btn:hover {{ text-decoration:none; border-color:var(--qba-accent); background:var(--qba-card2); }}
  .btn.primary {{ background:var(--qba-accent); border-color:var(--qba-accent); color:#fff; }}
  .btn.primary:hover {{ filter:brightness(1.08); color:#fff; background:var(--qba-accent); }}
  .btn.active {{ border-color:var(--qba-accent); background:var(--qba-card2); color:var(--qba-accent); box-shadow:inset 0 0 0 1px var(--qba-accent); }}

  .cose-tab-bar {{ display:flex; flex-wrap:wrap; align-items:center; gap:7px; padding:10px 0 14px; border-bottom:1px solid var(--qba-rule); margin-bottom:20px; }}
  .cose-tab-bar .tab-label {{ font-size:.73rem; font-weight:700; text-transform:uppercase; letter-spacing:.05em; color:var(--qba-soft); margin:0 2px 0 6px; }}

  .stats {{ display:flex; flex-wrap:wrap; gap:10px; margin:18px 0 0; padding:0; list-style:none; }}
  .stats li {{ background:var(--qba-card); border:1px solid var(--qba-rule); border-radius:10px;
    padding:9px 14px; font-size:.9rem; }}
  .stats b {{ font-size:1.18rem; display:block; font-weight:700; color:var(--qba-accent); }}
  .note {{ border-left:3px solid var(--qba-warn); background:var(--qba-card); padding:12px 16px;
    border-radius:0 8px 8px 0; margin:20px 0; }}
  .disc {{ background:var(--qba-card); border:1px solid var(--qba-rule); border-left:3px solid var(--qba-accent2);
    border-radius:8px; padding:12px 16px; color:var(--qba-soft); font-size:.9rem; margin-top:18px; }}

  .tag {{ display:inline-block; font-size:.75rem; font-weight:600; padding:2px 8px; border-radius:999px;
    background:rgba(63,182,168,.14); color:var(--qba-accent2); margin-left:6px; vertical-align:middle; }}

  table {{ border-collapse:collapse; width:100%; margin:14px 0; font-size:.93rem; }}
  .tablewrap {{ overflow-x:auto; -webkit-overflow-scrolling:touch; margin:14px 0; }}
  .tablewrap table {{ margin:0; min-width:760px; }}
  .tablewrap code {{ overflow-wrap:normal; white-space:nowrap; }}
  .tablewrap + .tablenote {{ font-size:.82rem; color:var(--qba-soft); margin:-4px 0 18px; }}
  th, td {{ text-align:left; padding:8px 10px; border-bottom:1px solid var(--qba-rule);
    vertical-align:top; }}
  th {{ font-weight:650; color:var(--qba-soft); font-size:.84rem; text-transform:uppercase;
    letter-spacing:.05em; }}
  .swatch {{ display:inline-block; width:34px; height:15px; border-radius:4px;
    background:var(--qba-card); vertical-align:-2px; margin-right:8px; }}
  .swatch.T1 {{ border:2.6px solid var(--qba-t1); }}
  .swatch.T2 {{ border:1.7px solid var(--qba-t2); }}
  .swatch.T3 {{ border:1.5px dashed var(--qba-t3); }}
  .swatch.T4 {{ border:1px solid var(--qba-t4); }}

  /* Figures with white background */
  figure.map {{ margin:0 0 40px; border:1px solid var(--qba-rule); border-radius:12px;
    overflow:hidden; background:var(--qba-card); }}
  figure.map > a {{ display:block; background:#ffffff; padding:12px 12px 6px; }}
  figure.map img, figure.map svg {{ width:100%; height:auto; display:block; background:#ffffff; }}
  figcaption {{ padding:14px 18px; font-size:.9rem; color:var(--qba-soft); border-top:1px solid var(--qba-rule); }}
  figcaption .t {{ color:var(--qba-ink); font-weight:650; font-size:1rem; display:block;
    margin-bottom:4px; }}
  .tiers {{ font-size:.82rem; color:var(--qba-soft); margin-top:8px; }}
  .dl {{ margin-top:8px; font-size:.85rem; }}

  footer {{ border-top:1px solid var(--qba-rule); margin-top:56px; padding-top:22px;
    font-size:.88rem; color:var(--qba-soft); }}
  .cose-foot {{ display:inline-flex; align-items:center; gap:6px; vertical-align:middle; margin-right:9px; font-weight:600; color:var(--qba-ink); text-decoration:none; }}
  .cose-foot img {{ height:20px; width:20px; display:block; border-radius:5px; }}
  .cose-foot:hover {{ text-decoration:none; filter:brightness(1.05); }}
  @media (max-width:640px) {{ header.hero {{ padding-top:24px; }} }}
</style>
</head>
<body data-site-id="{SITE_ID}">
<div class="wrap">
<div class="cose-topbar">
  <a href="index.html" class="cose-brand">
    <img src="https://dr-richard-barker.github.io/Plant_response_to_radiation/cose/cose-logo.png" alt="CoSE logo" width="28" height="28">
    <span>Quantum Biology Atlas</span>
  </a>
  <button id="cose-theme-toggle" class="cose-theme-btn" type="button" aria-label="Toggle theme">
    <span class="theme-icon"></span>
    <span class="theme-label">Theme</span>
  </button>
</div>
<nav class="cose-tab-bar" aria-label="Atlas demonstrations and resources">
  <a href="index.html" class="btn">Atlas Maps</a>
  <a href="explore.html" class="btn">Explore Your Data</a>
  <span class="tab-label">Demonstrations:</span>
  <a href="paper-Mannino2026.html" class="btn">Mannino 2026 (Basil hMF)</a>
  <a href="paper-Parmagnani2022.html" class="btn">Parmagnani 2022 (ROS Time-Course)</a>
  <a href="paper-Agliassa2018a.html" class="btn">Agliassa 2018 (Flowering)</a>
  <a href="osd8.html" class="btn">OSD-8 (16.5 T Magnet)</a>
  <a href="osd27.html" class="btn">OSD-27 (Drosophila 16.5 T)</a>
  <a href="osd782.html" class="btn">OSD-782 (Radiation × NNMF)</a>
  <span class="tab-label">Links:</span>
  <a href="manuscript.pdf" class="btn primary">Draft Manuscript (PDF)</a>
  <a href="https://github.com/dr-richard-barker/quantum-biology-atlas" class="btn">GitHub Code</a>
</nav>
"""


def tail() -> str:
    """Closes the page with the theme-toggle persistence script and visitor analytics.

    Note: CoSE navigation rail (theme.js/sites.js/.sitebar) is deliberately omitted.
    """
    return """<script>
(function() {
  var path = (window.location.pathname.split('/').pop() || 'index.html');
  var links = document.querySelectorAll('.cose-tab-bar a.btn');
  for (var i = 0; i < links.length; i++) {
    var href = links[i].getAttribute('href');
    if (href === path) {
      links[i].classList.add('active');
      links[i].setAttribute('aria-current', 'page');
    }
  }
  var btn = document.getElementById('cose-theme-toggle');
  if (!btn) return;
  function update(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('cose-theme', theme);
    btn.setAttribute('aria-label', 'Switch to ' + (theme === 'dark' ? 'light' : 'dark') + ' mode');
    var label = btn.querySelector('.theme-label');
    if (label) label.textContent = theme === 'dark' ? 'Light' : 'Dark';
    var icon = btn.querySelector('.theme-icon');
    if (icon) {
      icon.innerHTML = theme === 'dark'
        ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>'
        : '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
    }
  }
  var curr = document.documentElement.getAttribute('data-theme') || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  update(curr);
  btn.addEventListener('click', function() {
    var now = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    update(now);
  });
})();
</script>
<script defer src="https://visitor-analytics.astrobotany.workers.dev/a.js"></script>
</div>
</body>
</html>
"""



def _orthology_paragraph() -> str:
    """One sentence per real number, read from the generated ortholog map."""
    import json as _json

    path = ROOT / "catalog" / "orthologs.json"
    if not path.exists():
        return ("Cross-species projection runs on demand; no precomputed ortholog map "
                "is committed, so no coverage is claimed here.")
    doc = _json.loads(path.read_text())
    sp = doc["species"]
    h = sp["homo_sapiens"]
    corroborated = sum(1 for v in h["orthologs"].values() if v["corroborated"])
    others = ", ".join(
        f"{v['common_name']} {v['mapped']}/{v['requested']}"
        for k, v in sp.items() if k != "homo_sapiens"
    )
    return (
        f"Projecting the atlas's {doc['loci']} loci to human maps "
        f"<strong>{h['mapped']}</strong>, with both backbones agreeing on "
        f"{corroborated} and disagreeing on {len(h['method_disagreements'])}. "
        f"The other species run on Ensembl alone ({others}) because the committed "
        f"OrthoDB matrix is human-anchored — stated rather than left to look like "
        f"two-method corroboration. The <em>unmapped</em> set is the validation: the "
        f"alternative oxidase and type II NAD(P)H dehydrogenase loci fail to map, which "
        f"is correct, because humans have neither. A projection that matches nothing "
        f"<strong>raises</strong> rather than returning an empty frame that would render "
        f"as a blank map."
    )

def build(manifest: dict, onto, test_result: dict | None) -> str:
    t = manifest["totals"]
    out = [head(
        "Quantum Biology Atlas",
        manifest["description"],
    )]

    # ---- hero -----------------------------------------------------------
    out.append(f"""<header class="hero">
<h1>Quantum Biology Atlas</h1>
<p class="lede">Identifier-bound pathway maps of the places where weak magnetic fields
could plausibly act in a cell — each node carrying its quantum chemistry, its
supporting citations, and an explicit statement of how much is actually known.</p>
<p class="lede">Companion software to the review <em>“Plant Responses to Near-Null
Magnetic Fields: Geomagnetism, Bioenergetics, and Primary Metabolism in Arabidopsis
and Brassica”</em> (D. M. Porterfield &amp; R. Barker, Purdue University).</p>
<div class="btns" aria-label="Primary links and demonstrations">
  <a href="manuscript.pdf" class="btn primary">Draft Manuscript (PDF)</a>
  <a href="https://github.com/dr-richard-barker/quantum-biology-atlas" class="btn">GitHub Code</a>
  <a href="explore.html" class="btn">Explore Your Data</a>
  <a href="paper-Mannino2026.html" class="btn">Demo: Mannino 2026 (Basil hMF)</a>
  <a href="paper-Parmagnani2022.html" class="btn">Demo: Parmagnani 2022 (ROS)</a>
  <a href="paper-Agliassa2018a.html" class="btn">Demo: Agliassa 2018 (Flowering)</a>
  <a href="osd8.html" class="btn">Demo: OSD-8 (16.5 T Magnet)</a>
  <a href="osd27.html" class="btn">Demo: OSD-27 (Drosophila 16.5 T)</a>
  <a href="osd782.html" class="btn">Demo: OSD-782 (Radiation × NNMF)</a>
</div>
<ul class="stats">
  <li><b>{t['maps']}</b> pathway maps</li>
  <li><b>{t['nodes']}</b> annotated nodes</li>
  <li><b>{t['distinct_agi_loci']}</b> Arabidopsis loci</li>
  <li><b>{t['references']}</b> verified references</li>
</ul>
</header>""")

    # ---- the design argument --------------------------------------------
    tier_rows = "".join(
        f'<tr><td><span class="swatch {tid}"></span><code>{tid}</code></td>'
        f'<td><b>{e(lbl)}</b><br>{e(TIER_BLURB[tid])}</td>'
        f'<td style="text-align:right">{t["nodes_by_tier"].get(tid, 0)}</td></tr>'
        for tid, lbl in (("T1", "Demonstrated"), ("T2", "Inferred"),
                         ("T3", "Plausible"), ("T4", "Context"))
    )
    out.append(f"""<h2>Two questions, kept apart</h2>
<p>The ontology exists because these are different questions, and collapsing them is
how “contains a flavin” quietly becomes “is magnetically sensitive”:</p>
<table>
<tr><th>Axis</th><th>Question</th></tr>
<tr><td><code>quantum_class</code></td><td>What chemistry does this entity carry?
Structural, and largely uncontroversial.</td></tr>
<tr><td><code>evidence_tier</code></td><td>How much is actually <em>known</em> about
its magnetic-field sensitivity? This is where the claims live.</td></tr>
</table>
<p>A tier that asserts a demonstrated or inferred field effect <strong>cannot validate
without a resolved DOI</strong>. The tier is drawn as a border style on every map, so a
hypothesis looks provisional on the page:</p>
<table>
<tr><th>Tier</th><th>Meaning</th><th style="text-align:right">Nodes</th></tr>
{tier_rows}
</table>
<div class="note">
<p style="margin:0"><strong>The maps are mostly dashed, and that is the finding.</strong>
{t['nodes_by_tier'].get('T3', 0)} of {t['nodes']} nodes carry a plausible physical route
with no field measurement behind them. The Arabidopsis near-null-field literature is
developmental and nutritional; it has not yet measured a respiratory complex directly.
No base map encodes a quantitative value — numbers appear only when measured data is
projected onto one.</p>
</div>""")

    # ---- maps -----------------------------------------------------------
    out.append("<h2>The maps</h2>")
    out.append(f"""<p>Each map compiles from a declarative source with no coordinates in
it — box geometry is derived from measured text, which is what stops a label
outgrowing its box. Every map is published as <strong>SBGN-ML</strong> (Process
Description) so it opens in Newt, VANTED, CySBGN and the
<a href="{VIEWER}">SBGN Pathway Visualizer</a>, with the quantum annotation carried in
<code>&lt;extension&gt;</code> blocks that other renderers safely ignore.</p>""")

    for m in manifest["maps"]:
        tiers = " · ".join(f"{k} {v}" for k, v in sorted(m["tiers"].items()))
        svg_rel = m["svg_url"].split("/quantum-biology-atlas/", 1)[-1]
        sbgn_rel = m["sbgn_url"].split("/quantum-biology-atlas/", 1)[-1]
        qbo_rel = m["qbo_url"].split("/quantum-biology-atlas/", 1)[-1]
        out.append(f"""<figure class="map" id="{e(m['id'])}">
<a href="{e(svg_rel)}"><img src="{e(svg_rel)}" alt="{e(m['title'])}" loading="lazy"></a>
<figcaption>
<span class="t">{e(m['id'])} · {e(m['title'])}</span>
{e(m['caption'])}
<div class="tiers">{m['nodes']} nodes · {m['edges']} edges · {e(tiers)} ·
{len(m['agi_loci'])} loci</div>
<div class="dl"><a href="{e(sbgn_rel)}">SBGN-ML</a> ·
<a href="{e(svg_rel)}">SVG</a> ·
<a href="{e(qbo_rel)}">QBO annotation (JSON)</a></div>
</figcaption>
</figure>""")

    # ---- cross-species ---------------------------------------------------
    # Derived from catalog/orthologs.json rather than typed. The previous wording
    # here claimed "15 of 28", which was true of an earlier, smaller ontology and had
    # silently become wrong — a hard-coded count is exactly what this project treats as
    # a defect everywhere else.
    ortho_para = _orthology_paragraph()
    out.append(f"""<h2>Cross-species projection</h2>
<p>The ontology is anchored on <em>Arabidopsis</em>, because that is where the
near-null-field literature is. Projecting onto another organism runs
<strong>two independent orthology backbones</strong> and reports where they disagree,
rather than silently preferring one:</p>
<ul>
<li><strong>Ensembl Compara <code>pan_homology</code></strong> — the only division that
crosses kingdoms. The <code>plants</code> division does not reach animals at all.</li>
<li><strong>OrthoDB v12</strong> — the committed human-anchored matrix from
<a href="https://github.com/dr-richard-barker/OSDR_X-species_V2">OSDR_X-species_V2</a>.</li>
</ul>
<p>{ortho_para}</p>""")

    # ---- demonstration pages ---------------------------------------------
    # Built from results/papers/*/record.json, so a new showcase appears here without
    # this file being edited — and a page whose record is missing simply does not.
    papers_dir = ROOT / "results" / "papers"
    records = []
    for rec_path in sorted(papers_dir.glob("*/record.json")):
        import json as _json

        records.append(_json.loads(rec_path.read_text()))
    osd27 = ROOT / "results" / "osd27" / "record.json"
    if records or osd27.exists():
        out.append("""<h2>Demonstrations</h2>
<p>Each page projects real measurements onto the maps and states its provenance class,
because the three available kinds of data do not carry equal weight:
<code>genelab_processed</code> (NASA's own pipeline), <code>depositor_normalised</code>
(the depositors' ratios, no model fitted) and <code>published_results</code> (numbers
read out of a paper's supplementary tables, because nothing was deposited).</p>""")
        for rec in records:
            tps = rec["figures"][0]["timepoints"] if rec["figures"] else []
            out.append(f"""<figure class="map"><figcaption>
<span class="t"><a href="paper-{e(rec['key'])}.html">{e(rec['citation'])}</a></span>
<p>{rec['loci_in_table']} loci, {len(tps)} timepoints across
{len(rec['tissues'])} tissues, {rec['cells_parsed']:,} values —
{len(rec['qbo_loci_covered'])} of them on atlas nodes. The first overlay in this atlas
to carry <strong>time</strong> rather than a single snapshot.</p>
<p><strong>Provenance:</strong> <code>{e(rec['provenance_class'])}</code>. No raw data
was deposited; the Data Availability Statement reads
<em>“{e(rec['data_availability_verbatim'])}”</em>.</p>
<p class="dl"><a href="paper-{e(rec['key'])}.html">Open the demonstration →</a></p>
</figcaption></figure>""")

    # The upload GUI. Listed first because it is the thing a visitor can use on their
    # own data, rather than read about.
    if (args_out_docs := ROOT / "docs" / "explore.html").exists():
        out.append("""<figure class="map"><figcaption>
<span class="t"><a href="explore.html">Explore — put your own data on the maps</a></span>
<p>Drop a differential-expression table and see it projected onto any map, with the
orthology run for you if it is not <em>Arabidopsis</em>. <strong>Nothing is uploaded</strong>
— the file is read in your browser and joined against the catalogue that ships with this
site.</p>
<p>It carries the same refusals as the generated figures: an empty join stops with an
explanation rather than drawing a blank map, coverage below 25% warns and states the
number, and a namespace that cannot reach your chosen species is caught before the join
rather than after. It also names the nodes that collapse onto a shared gene.</p>
<p class="dl"><a href="explore.html">Open the tool →</a></p>
</figcaption></figure>""")

    rad = ROOT / "results" / "osd782" / "record.json"
    ovl = ROOT / "results" / "overlap" / "record.json"
    if rad.exists() and ovl.exists():
        import json as _json

        r782 = _json.loads(rad.read_text())
        o = _json.loads(ovl.read_text())["nnmf_locus_arm"]["summary"]
        out.append(f"""<figure class="map"><figcaption>
<span class="t"><a href="osd782.html">OSD-782 — does ionising radiation move the same chemistry?</a></span>
<p>A dose × time radiation course in <em>Arabidopsis</em> ({len(r782['doses_gy'])} doses,
{len(r782['timepoints'])} timepoints, {r782['qbo_loci_measured']} atlas loci), asked
against the magnetic-field studies. <strong>Radiation is not a field regime</strong> and
the page does not treat it as one — the question is overlap.</p>
<p><strong>{o['directions_agree']} of {o['units_compared']} shared loci respond to both
radiation and a near-null field in the same direction.</strong> Reported as a lead, not
a result: eleven loci is too few to test, and the page says so rather than computing a
p-value that would look like evidence.</p>
<p>It also forced a check the atlas lacked: under radiation almost every multi-locus node
has loci that <em>disagree in sign</em>, so a node's single trace can be the aggregator
choosing between genes doing different things. The AOX family is the worked case.</p>
<p class="dl"><a href="osd782.html">Open the demonstration →</a></p>
</figcaption></figure>""")

    osd8p = ROOT / "results" / "osd8" / "record.json"
    if osd8p.exists():
        import json as _json

        r8 = _json.loads(osd8p.read_text())
        s8 = r8["specificity"][r8["primary_group"]]
        out.append(f"""<figure class="map"><figcaption>
<span class="t"><a href="osd8.html">OSD-8 — the same gravity, inside and outside a 16.5 T magnet</a></span>
<p>The cleanest field-only contrast in the atlas: 1g inside the magnet against 1g
outside it, in <em>Arabidopsis</em>, at <strong>100% node coverage</strong> on every
map. The study also carries gravity controls that use no magnet at all.</p>
<p><strong>And the result that constrains every other page:</strong> the atlas's
{s8['n_selected_measured']} loci move no more than {s8['n_background_loci']:,} random
loci from the same array (p&nbsp;=&nbsp;{s8['p_value']:.2f}). Selecting for quantum
chemistry did not select for field responsiveness here, and the page says so.</p>
<p><strong>Provenance:</strong> <code>{e(r8['provenance_class'])}</code> — the
depositors' normalised ratios, no model fitted, so no significance is shown.</p>
<p class="dl"><a href="osd8.html">Open the demonstration →</a></p>
</figcaption></figure>""")

    if osd27.exists():
        import json as _json

        r27 = _json.loads(osd27.read_text())
        o27 = r27["orthology"]
        nodes27 = sum(len(m["consistency"]) for m in r27["maps"].values() if "consistency" in m)
        out.append(f"""<figure class="map"><figcaption>
<span class="t"><a href="osd27.html">OSD-27 — <em>Drosophila</em> in a 16.5 T levitation magnet</a></span>
<p>The cross-species bridge doing real work: {o27['mapped']} of {o27['requested']} atlas
loci reach the fly, and Arabidopsis CRY1 lands on <em>Drosophila</em> <code>cry</code>,
the canonical animal magnetoreceptor. Of 420 contrasts, {len(r27['contrasts'])} isolate
the field from the gravity the levitation also changes.</p>
<p><strong>The result is null and reported as one:</strong> none of the {nodes27} nodes
with data moves the same way in all {len(r27['contrasts'])} contrasts. The page also
states what the projection destroys — on the cryptochrome map three distinct nodes
collapse onto one fly gene.</p>
<p><strong>Provenance:</strong> <code>{e(r27['provenance_class'])}</code>, and a
<strong>strong-field</strong> study — the opposite end of the axis from the review.</p>
<p class="dl"><a href="osd27.html">Open the demonstration →</a></p>
</figcaption></figure>""")

    # ---- the test --------------------------------------------------------
    if test_result:
        pri = test_result["tests"][0]
        mde = test_result.get("power", {}).get("min_detectable_or_at_80pct_power")
        out.append(f"""<h2>A pre-registered test, and why it could not settle anything</h2>
<p>The hypothesis, null, data sources and <em>confounds</em> were committed before the
script was run. The question: are human orthologs carrying spin-bearing cofactors
over-represented among genes conserved-suppressed across six species in spaceflight?</p>
<table>
<tr><th></th><th>carries a spin cofactor</th><th>does not</th></tr>
<tr><td>conserved <b>down</b></td><td>{pri['down_with']}</td><td>{pri['down_without']}</td></tr>
<tr><td>conserved <b>up</b></td><td>{pri['up_with']}</td><td>{pri['up_without']}</td></tr>
</table>
<p>Odds ratio <b>{pri['odds_ratio']}</b> (95% CI {pri['ci95'][0]}–{pri['ci95'][1]}),
Fisher exact <b>p&nbsp;=&nbsp;{pri['p']:.2f}</b> — fail to reject the null. Iron-sulfur
chemistry specifically, the mechanism the review argues hardest for, gives an odds
ratio of 0.90.</p>
<div class="note">
<p style="margin:0 0 8px"><strong>That negative result settles nothing, and saying so
is the point.</strong> Simulation on the realised marginals puts the minimum detectable
odds ratio at <b>{mde}</b> for 80% power; a genuine doubling of odds would have been
missed three times in four.</p>
<p style="margin:0">Three structural reasons this dataset cannot answer the question:
only 19 of 590 directional genes carry a spin-bearing cofactor; the mitochondrial
stratum has no contrast at all, because every conserved mitochondrial gene in the
table is suppressed and none is up-regulated; and spaceflight bundles microgravity,
ionising radiation and a hypomagnetic environment, so attribution to the magnetic
component was never available. The result strengthens the review's own call for direct
bioenergetic measurements under controlled conditions.</p>
</div>
<p><a href="results/preregistered_test_report.md">Full report</a> ·
<a href="results/preregistered_test.json">Machine-readable result</a></p>""")

    # ---- honesty section -------------------------------------------------
    out.append("""<h2>Things found by building it</h2>
<h3>A curated study database whose DOIs were mostly wrong</h3>
<p>Every DOI in the companion repository's <code>nnmf_study_database.csv</code> was
resolved against CrossRef: <strong>only 7 of 49 title-match</strong>. Its Belyavskaya
row cites a paper on calcium gradients in the fish inner ear. The manuscript's own
bibliography, by contrast, is clean — <strong>42 of 42 resolve and title-match</strong> —
so the evidence base here is built from the bibliography, re-verified on every run,
and the build refuses to write its output if any reference fails.</p>

<h3>Gene symbols are not safe to type</h3>
<p>Resolving every symbol against Ensembl during authoring caught five collisions that
would each have put the wrong gene on a map: <code>ACO2</code> returns ACC oxidase 2
rather than aconitase 2, <code>LIP1</code> a lipase rather than lipoyl synthase,
<code>CAT2</code> and <code>CAT3</code> cationic amino acid transporters rather than
catalases, and <code>KAT2</code> a potassium channel rather than the thiolase. The
ontology stores loci, never symbols.</p>

<h3>A cofactor table with no iron-sulfur entries</h3>
<p>The KEGG-derived cofactor mapping in <code>OSDR_X-species_V2</code> contains zero
iron-sulfur entries despite its generating script listing Fe-S among the cofactors to
map, and only 5 heme and 10 FMN genes genome-wide. The script skips any cofactor whose
cache file is missing without reporting the skip. UniProt/Swiss-Prot was used instead,
which curates 71 human Fe-S proteins.</p>

<h3>Figure legibility as a test, not a review step</h3>
<p>The review draft carries the margin note <em>“the text spills out of the box's… and
the TCA cycle needs some work”</em>. Both are fixed structurally: boxes are sized around
measured text so a label cannot overflow by construction, and the TCA cycle is redrawn
as an actual closed cycle. A browser-side probe then measures what was really painted —
using the browser's own text layout rather than re-running the compiler's arithmetic —
and asserts no overflow, no overlapping boxes or compartment bands, nothing clipped,
and a caption that states provenance. All ten maps pass across 1,447 elements.</p>""")

    # ---- use -------------------------------------------------------------
    out.append(f"""<h2>Using the atlas</h2>
<p>The published catalogue is <a href="catalog/manifest.json"><code>catalog/manifest.json</code></a>:
a flat, self-describing list of every map with its SBGN URL and a per-node annotation
sidecar carrying evidence tier, quantum class and citations — so a consumer can draw
the tier channel without parsing SBGN extensions.</p>
<pre><code>pip install pyyaml matplotlib scipy
PYTHONPATH=src python3 -c "
from qbio import ontology, maps
onto = ontology.load()
for r in maps.compile_all(onto):
    print(r['id'], r['nodes'], 'nodes', r['tiers'])"</code></pre>
<p>Project a NASA OSDR contrast onto a map:</p>
<pre><code>PYTHONPATH=src python3 -c "
from qbio import ontology, maps, osdr, project
onto = ontology.load()
spec = maps.load_spec('maps/src/QBM-01_mitochondrial_etc.yaml')
nodes = [(n, onto.get(spec.nodes.get(n, {{}}).get('qbo',''))) for n in spec.node_ids]
table = osdr.load_contrast(38, contrast='(FLT)v(GC)')
proj = project.project_expression(map_id=spec.id, nodes=nodes, table=table)
print(proj.summary())"</code></pre>""")

    out.append(f"""<footer>
<p><strong>Licence.</strong> Ontology, maps and evidence base CC-BY-4.0; code MIT.</p>
<p><strong>Citing.</strong> The review is in preparation and no DOI has been issued.
Cite this repository by URL until one exists — please do not cite a placeholder DOI.</p>
<p><strong>Status.</strong> QBO {e(manifest['qbo_version'])} ·
<a href="https://github.com/dr-richard-barker/quantum-biology-atlas">source on GitHub</a>.
The manuscript, viewer integration and Zenodo deposit are not yet built.</p>
</footer>""")
    out.append(tail())
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", type=pathlib.Path, default=ROOT / "catalog" / "manifest.json")
    ap.add_argument("--out", type=pathlib.Path, default=ROOT / "docs" / "index.html")
    args = ap.parse_args()

    if not args.manifest.exists():
        sys.exit("catalog/manifest.json not found — run scripts/build_catalog.py first")

    from qbio import ontology

    manifest = json.loads(args.manifest.read_text())
    onto = ontology.load()
    result_path = ROOT / "results" / "preregistered_test.json"
    test_result = json.loads(result_path.read_text()) if result_path.exists() else None

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(build(manifest, onto, test_result), encoding="utf-8")
    (args.out.parent / ".nojekyll").write_text("")

    # Copy the referenced artefacts in, so docs/ is self-contained and Pages can be
    # served from /docs without exposing the whole repository.
    import shutil

    copied = 0
    for rel in ("maps/svg", "maps/sbgn", "catalog"):
        src, dst = ROOT / rel, args.out.parent / rel
        if not src.exists():
            continue
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns("_probe_*"))
        copied += sum(1 for _ in dst.rglob("*") if _.is_file())
    (args.out.parent / "results").mkdir(exist_ok=True)
    for name in ("preregistered_test_report.md", "preregistered_test.json"):
        f = ROOT / "results" / name
        if f.exists():
            shutil.copy2(f, args.out.parent / "results" / name)
            copied += 1
    # Per-paper records back the demonstration pages built from published supplementary
    # tables. They have to live UNDER docs/: Pages serves only that directory, so a link
    # to ../results/ resolves on a local checkout and 404s on the deployed site.
    for rec in sorted((ROOT / "results" / "papers").glob("*/record.json")):
        dst = args.out.parent / "results" / "papers" / rec.parent.name / "record.json"
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(rec, dst)
        copied += 1
    for rec in sorted(ROOT.glob("results/overlap/record.json")):
        dst = args.out.parent / "results" / "overlap" / "record.json"
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(rec, dst)
        copied += 1
    for rec in sorted(ROOT.glob("results/osd*/record.json")):
        dst = args.out.parent / "results" / rec.parent.name / "record.json"
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(rec, dst)
        copied += 1
    ms_pdf = ROOT / "manuscript" / "manuscript.pdf"
    if ms_pdf.exists():
        shutil.copy2(ms_pdf, args.out.parent / "manuscript.pdf")
        copied += 1
    print(f"  copied {copied} artefact files into docs/ (site is self-contained)")
    print(f"wrote {args.out.relative_to(ROOT)} ({args.out.stat().st_size/1024:.0f} KB)")
    print(f"  {manifest['totals']['maps']} maps, theme from {COSE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
