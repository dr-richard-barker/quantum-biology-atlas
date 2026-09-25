"""
Dedicated sub-map generator for the Phenylpropanoid and Volatilome Pathway in Ocimum basilicum.

Highlights the gene-metabolite decoupling paradox documented by Mannino, Caldo & Maffei (2026):
  * Every analysed phenylpropanoid / flavonoid biosynthetic transcript is downregulated (log2FC -0.70 to -1.65)
  * Downstream essential oil volatiles (eugenol, methyl eugenol, cis-ocimene) and total flavonoids accumulate to significantly higher levels (+28% to +119%)

Renders as a standalone SBGN-inspired SVG following the Okabe-Ito palette and typography of the Quantum Biology Atlas.
"""
from __future__ import annotations

import pathlib
from typing import Sequence

from .render import OKABE_ITO, esc

WIDTH = 960.0
HEIGHT = 715.0


def render_decoupling_svg(out_path: pathlib.Path | None = None) -> str:
    """Generate the dedicated Phenylpropanoid & Volatilome Decoupling Sub-Map SVG."""
    blue = OKABE_ITO["blue"]          # #0072B2 - transcript downregulation
    vermillion = OKABE_ITO["vermillion"]  # #D55E00 - metabolite accumulation
    ink = "#16181d"
    soft = "#55606e"
    bg = "#ffffff"
    card = "#f7f8fa"
    rule = "#e5e9f0"

    svg = []
    svg.append(f'<svg xmlns="http://www.w3.org/2000/svg" data-theme="light" viewBox="0 0 {WIDTH} {HEIGHT}" width="{WIDTH}" height="{HEIGHT}">')
    svg.append('<style>')
    svg.append(f"""
      .title {{ font: bold 20px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; fill: {ink}; }}
      .subtitle {{ font: 13px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; fill: {soft}; }}
      .provenance {{ font: italic 11px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; fill: {soft}; }}
      .box {{ fill: {card}; stroke: {ink}; stroke-width: 1.5; rx: 8px; }}
      .box-chem {{ fill: #ffffff; stroke: #3d3d3d; stroke-width: 1.2; rx: 6px; }}
      .box-transcript {{ fill: #f0f6fa; stroke: {blue}; stroke-width: 2.0; rx: 6px; }}
      .box-metabolite {{ fill: #fdf5f0; stroke: {vermillion}; stroke-width: 2.2; rx: 8px; }}
      .label-node {{ font: bold 12px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; fill: {ink}; text-anchor: middle; }}
      .label-sub {{ font: 10px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; fill: {soft}; text-anchor: middle; }}
      .label-stat-down {{ font: bold 11px ui-monospace, SFMono-Regular, Menlo, monospace; fill: {blue}; text-anchor: middle; }}
      .label-stat-up {{ font: bold 11px ui-monospace, SFMono-Regular, Menlo, monospace; fill: {vermillion}; text-anchor: middle; }}
      .arrow {{ stroke: #55606e; stroke-width: 1.5; fill: none; marker-end: url(#arrowhead); }}
      .arrow-dashed {{ stroke: #55606e; stroke-width: 1.5; stroke-dasharray: 4,3; fill: none; marker-end: url(#arrowhead); }}
      .band-label {{ font: bold 12px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; fill: {soft}; text-transform: uppercase; letter-spacing: 0.05em; }}
    """)
    svg.append('</style>')

    # Defs
    svg.append('<defs>')
    svg.append('<marker id="arrowhead" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">')
    svg.append(f'<polygon points="0 0, 8 3, 0 6" fill="{soft}"/>')
    svg.append('</marker>')
    svg.append('</defs>')

    # Background canvas
    svg.append(f'<rect width="{WIDTH}" height="{HEIGHT}" fill="{bg}"/>')

    # Header
    svg.append(f'<text class="title" x="24" y="36">Phenylpropanoid &amp; Volatilome Pathway: The Gene-Metabolite Decoupling</text>')
    svg.append(f'<text class="subtitle" x="24" y="58">Ocimum basilicum under hypomagnetic field (hMF &lt; 40 nT vs GMF ~44.4 µT) · 4-week exposure</text>')
    svg.append(f'<text class="provenance" x="24" y="76">Source: Mannino, Caldo &amp; Maffei (2026), Journal of Plant Physiology 326:154872 · doi:10.1016/j.jplph.2026.154872</text>')
    svg.append(f'<line x1="24" y1="88" x2="{WIDTH - 24}" y2="88" stroke="{rule}" stroke-width="1"/>')

    # Containers / Panels
    # Panel 1: Core Phenylpropanoid & Volatiles (x=24, y=100, w=440, h=450)
    svg.append(f'<rect x="24" y="100" width="440" height="450" fill="#fafbfc" stroke="{rule}" rx="10"/>')
    svg.append(f'<text class="band-label" x="38" y="122">Core Phenylpropanoid → Eugenol &amp; Methyl Eugenol</text>')

    # Panel 2: Flavonoid Branch (x=480, y=100, w=456, h=280)
    svg.append(f'<rect x="480" y="100" width="456" height="280" fill="#fafbfc" stroke="{rule}" rx="10"/>')
    svg.append(f'<text class="band-label" x="494" y="122">Flavonoid Biosynthesis &amp; Glycoside Remodelling</text>')

    # Panel 3: Terpene / Monoterpenes (x=480, y=396, w=456, h=164)
    svg.append(f'<rect x="480" y="396" width="456" height="164" fill="#fafbfc" stroke="{rule}" rx="10"/>')
    svg.append(f'<text class="band-label" x="494" y="418">Monoterpenes &amp; Sesquiterpenes (Volatilome)</text>')

    # Helper function for drawing chemical / metabolite nodes
    def draw_chem(cx: float, cy: float, w: float, h: float, label: str, sub: str = ""):
        x, y = cx - w / 2, cy - h / 2
        res = [f'<g class="node-chem">',
               f'<rect class="box-chem" x="{x}" y="{y}" width="{w}" height="{h}"/>',
               f'<text class="label-node" x="{cx}" y="{cy + (0 if sub else 4)}">{esc(label)}</text>']
        if sub:
            res.append(f'<text class="label-sub" x="{cx}" y="{cy + 13}">{esc(sub)}</text>')
        res.append('</g>')
        return "\n".join(res)

    def draw_transcript(cx: float, cy: float, w: float, h: float, enzyme: str, gene: str, locus: str, log2fc: str):
        x, y = cx - w / 2, cy - h / 2
        return "\n".join([
            f'<g class="node-transcript">',
            f'<rect class="box-transcript" x="{x}" y="{y}" width="{w}" height="{h}"/>',
            f'<text class="label-node" x="{cx}" y="{cy - 8}">{esc(enzyme)} ({esc(gene)})</text>',
            f'<text class="label-sub" x="{cx}" y="{cy + 5}">{esc(locus)}</text>',
            f'<text class="label-stat-down" x="{cx}" y="{cy + 19}">log2FC {esc(log2fc)}*</text>',
            f'</g>'
        ])

    def draw_metabolite(cx: float, cy: float, w: float, h: float, name: str, fc: str, abs_amt: str, p_sig: bool = True):
        x, y = cx - w / 2, cy - h / 2
        sig = "*" if p_sig else ""
        return "\n".join([
            f'<g class="node-metabolite">',
            f'<rect class="box-metabolite" x="{x}" y="{y}" width="{w}" height="{h}"/>',
            f'<text class="label-node" x="{cx}" y="{cy - 9}" style="fill:{vermillion}">{esc(name)}</text>',
            f'<text class="label-stat-up" x="{cx}" y="{cy + 5}">{esc(fc)}{sig}</text>',
            f'<text class="label-sub" x="{cx}" y="{cy + 18}">{esc(abs_amt)}</text>',
            f'</g>'
        ])

    # Left Column elements
    # 1. Phenylalanine
    svg.append(draw_chem(150, 155, 140, 36, "L-Phenylalanine", "Shikimate precursor"))
    # Arrow
    svg.append('<path d="M 150 173 L 150 197" class="arrow"/>')
    # PAL
    svg.append(draw_transcript(150, 222, 170, 50, "PAL", "ObPAL", "AT2G37040", "-1.05 ± 0.15"))
    # Arrow
    svg.append('<path d="M 150 247 L 150 270" class="arrow"/>')
    # trans-Cinnamate
    svg.append(draw_chem(150, 288, 140, 36, "trans-Cinnamate", "→ Caffeic acid"))
    # Arrow
    svg.append('<path d="M 150 306 L 150 328" class="arrow"/>')
    # COMT
    svg.append(draw_transcript(150, 353, 170, 50, "COMT", "ObCOMT", "AT5G54160", "-1.30 ± 0.20"))
    # Arrow
    svg.append('<path d="M 150 378 L 150 400" class="arrow"/>')
    # Ferulate -> 4CL
    svg.append(draw_transcript(150, 425, 170, 50, "4CL", "Ob4CL", "AT1G51680", "-0.70 ± 0.10"))
    # Arrow down to Coniferyl acetate
    svg.append('<path d="M 150 450 L 150 472" class="arrow"/>')
    # Coniferyl acetate
    svg.append(draw_chem(150, 490, 140, 36, "Coniferyl acetate", "CCR / CAD / CFAT"))
    # Arrow to EGS
    svg.append('<path d="M 220 490 L 260 490" class="arrow"/>')
    # EGS
    svg.append(draw_transcript(345, 490, 160, 50, "EGS", "ObEGS", "AT1G72680", "-0.80 ± 0.12"))
    # Arrow EGS -> Eugenol
    svg.append('<path d="M 345 465 L 345 390" class="arrow"/>')
    # EUGENOL metabolite
    svg.append(draw_metabolite(345, 355, 165, 54, "EUGENOL", "+28% (+1.28x)", "3.08 ± 0.15 mg/g d.w."))
    # Arrow Eugenol -> EOMT
    svg.append('<path d="M 345 328 L 345 272" class="arrow"/>')
    # EOMT
    svg.append(draw_transcript(345, 245, 160, 50, "EOMT", "ObEOMT", "AT1G21100", "-1.65 ± 0.15"))
    # Arrow EOMT -> Methyl Eugenol
    svg.append('<path d="M 345 220 L 345 178" class="arrow"/>')
    # METHYL EUGENOL metabolite
    svg.append(draw_metabolite(345, 150, 165, 54, "METHYL EUGENOL", "+79% (+1.79x)", "0.34 ± 0.05 mg/g d.w."))

    # Right Column: Flavonoids
    # Arrow from 4CL branching to Flavonoids
    svg.append('<path d="M 235 425 Q 480 425 560 270" class="arrow-dashed"/>')
    # CHS
    svg.append(draw_transcript(580, 175, 160, 50, "CHS", "ObCHS", "AT5G13930", "-1.45 ± 0.18"))
    # Arrow CHS -> CHI
    svg.append('<path d="M 660 175 L 720 175" class="arrow"/>')
    # CHI / CHIL
    svg.append("\n".join([
        f'<g class="node-transcript">',
        f'<rect class="box-transcript" x="720" y="150" width="180" height="50"/>',
        f'<text class="label-node" x="810" y="166">CHI / CHIL (ObCHI/CHIL)</text>',
        f'<text class="label-sub" x="810" y="179">AT3G55120 / AT5G05270</text>',
        f'<text class="label-stat-down" x="810" y="193">log2FC -0.95* / -1.35*</text>',
        f'</g>'
    ]))
    # Arrow down to Flavonoid outputs
    svg.append('<path d="M 580 200 L 580 235" class="arrow"/>')
    svg.append('<path d="M 810 200 L 810 235" class="arrow"/>')
    # Total Flavonoid Content (TFC)
    svg.append(draw_metabolite(580, 260, 170, 50, "TOTAL FLAVONOIDS", "+18% (+1.18x)", "130 vs 110 mg QE/g"))
    # Flavonoid Glycoside Remodelling (Cluster 1 vs Cluster 2)
    svg.append("\n".join([
        f'<g>',
        f'<rect x="680" y="235" width="236" height="125" fill="#ffffff" stroke="{rule}" rx="6"/>',
        f'<text class="label-node" x="798" y="254" style="fill:{ink}">LC-MS/MS Remodelling</text>',
        f'<text class="label-sub" x="798" y="270" style="fill:{vermillion};font-weight:600">▲ Glucuronides &amp; Rhamnosides</text>',
        f'<text class="label-sub" x="798" y="284">Cluster 1 (apigenin-, catechin-O-rham)</text>',
        f'<text class="label-sub" x="798" y="302" style="fill:{blue};font-weight:600">▼ Dihydroflavonols &amp; Aglycones</text>',
        f'<text class="label-sub" x="798" y="316">Cluster 2 (dihydroquercetin, catechin)</text>',
        f'<text class="label-sub" x="798" y="340" style="font-style:italic">Polar conjugates enhance vacuolar ROS buffer</text>',
        f'</g>'
    ]))

    # Panel 3: Terpenes
    # cis-Ocimene
    svg.append(draw_metabolite(580, 465, 170, 54, "cis-OCIMENE", "+119% (+2.19x)", "0.09 ± 0.01 mg/g d.w."))
    # 1,8-Cineole
    svg.append(draw_metabolite(780, 465, 170, 54, "1,8-CINEOLE", "+35% (+1.35x)", "0.57 ± 0.02 mg/g d.w."))
    # Total Essential Oil
    svg.append(draw_metabolite(680, 526, 290, 48, "TOTAL IDENTIFIED ESSENTIAL OIL", "+29% (+1.29x)", "5.75 ± 0.53 vs 4.44 ± 0.38 mg/g d.w."))

    # Bottom Callout: The Decoupling Paradox Banner
    svg.append(f'<rect x="24" y="574" width="{WIDTH - 48}" height="118" fill="#f4f6fa" stroke="{rule}" rx="8"/>')
    svg.append(f'<text class="label-node" x="40" y="596" style="text-anchor:start;fill:{ink};font-size:13px">THE GENE-METABOLITE DECOUPLING PARADOX UNDER NEAR-NULL MAGNETIC FIELDS</text>')
    desc_lines = [
        "• Transcriptional Repression (Blue): Every analysed phenylpropanoid & early flavonoid transcript (ObPAL, ObCOMT, ObEGS, ObEOMT, Ob4CL, ObCHS, ObCHI, ObCHIL)",
        "  is significantly downregulated under hMF (< 40 nT) compared with GMF controls (log2 fold change from -0.70 to -1.65, P < 0.05).",
        "• Physical Accumulation (Vermillion): In sharp contrast, volatile essential oils (eugenol +28%, methyl eugenol +79%, cis-ocimene +119%, total volatiles +26%)",
        "  and total flavonoids (+18%) increase significantly, accompanied by a shift toward more polar glucuronide and rhamnoside conjugates.",
        "• Biological Significance: Demonstrates that near-null magnetic field adaptation in aromatic crops involves post-transcriptional control, metabolic flux redirection,",
        "  and altered precursor allocation (shikimate pathway) rather than steady-state transcript abundance, critical for space agriculture (BLSS) optimization."
    ]
    dy = 614
    for line in desc_lines:
        svg.append(f'<text class="label-sub" x="40" y="{dy}" style="text-anchor:start;font-size:10px;fill:{ink}">{esc(line)}</text>')
        dy += 13

    svg.append('</svg>')
    content = "\n".join(svg)

    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content, encoding="utf-8")

    return content
