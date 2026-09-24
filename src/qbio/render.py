"""
SVG rendering for QBM maps.

Two things drive every visual decision here.

**Evidence must be visible.** The evidence tier is a border channel, not a
footnote: T1 (demonstrated) draws solid and heavy, T2 (inferred) solid and light,
T3 (plausible) *dashed* — so a hypothesis literally looks provisional on the
page — and T4 (context) a thin grey hairline. A reader can tell at a glance how
much of a diagram is measured and how much is reasoned, without reading a legend.

**Colour must survive a colourblind reader and a dark background.** The palette
is Okabe-Ito throughout; the review's own figures used pure red/green, which is
the one pairing to avoid. Theming goes through a `<style>` block rather than
presentation attributes, because WebKit does not resolve `var()` inside an SVG
presentation attribute — `fill="var(--x)"` renders as nothing in Safari, while a
CSS rule `.qbm-node { fill: var(--x) }` works everywhere.
"""
from __future__ import annotations

import html
import re
import textwrap
from typing import Iterable, Sequence

from .layout import (
    LINE_SPACING,
    SVG_FONT_STACK,
    Box,
    LaidOutNode,
    edge_anchors,
    measure,
    text_block,
)

# Okabe-Ito, the portfolio's standing palette.
OKABE_ITO = {
    "orange": "#E69F00",
    "sky": "#56B4E9",
    "green": "#009E73",
    "yellow": "#F0E442",
    "blue": "#0072B2",
    "vermillion": "#D55E00",
    "purple": "#CC79A7",
    "black": "#000000",
}

#: Compartment fills. Deliberately low-saturation so node borders carry the signal.
COMPARTMENT_STYLE = {
    "mitochondrial_matrix": ("#7a4a12", "mito"),
    "mitochondrial_inner_membrane": ("#7a4a12", "mito"),
    "mitochondrial_intermembrane_space": ("#7a4a12", "mito"),
    "mitochondrion": ("#7a4a12", "mito"),
    "chloroplast_stroma": ("#0b5c46", "plastid"),
    "thylakoid_membrane": ("#0b5c46", "plastid"),
    "thylakoid_lumen": ("#0b5c46", "plastid"),
    "chloroplast": ("#0b5c46", "plastid"),
    "cytosol": ("#264b63", "cytosol"),
    "nucleus": ("#4a2a55", "nucleus"),
    "peroxisome": ("#6b5a06", "peroxisome"),
    "plasma_membrane": ("#264b63", "cytosol"),
    "apoplast": ("#3d3d3d", "apoplast"),
    "vacuole": ("#264b63", "cytosol"),
    "endoplasmic_reticulum": ("#264b63", "cytosol"),
    "cell": ("#3d3d3d", "cell"),
    "organism": ("#3d3d3d", "cell"),
    "environment": ("#3d3d3d", "environment"),
}

TIER_LABEL = {
    "T1": "Demonstrated",
    "T2": "Inferred",
    "T3": "Plausible",
    "T4": "Context",
}

TITLE_SIZE = 20.0
SUBTITLE_SIZE = 12.5
NODE_SIZE = 13.0
SUB_SIZE = 10.0
CAPTION_SIZE = 11.5
LEGEND_SIZE = 11.0


def esc(s: str) -> str:
    return html.escape(str(s), quote=True)


def _stylesheet() -> str:
    """Theme tokens plus the tier/class rules. Light and dark both explicit."""
    return textwrap.dedent(
        f"""
        :root {{
          --qbm-bg: #ffffff;
          --qbm-ink: #16181d;
          --qbm-ink-soft: #55606e;
          --qbm-node-fill: #f7f8fa;
          --qbm-node-stroke: #16181d;
          --qbm-hairline: #9aa3b0;
          --qbm-edge: #55606e;
          --qbm-compartment-fill: rgba(0,0,0,0.035);
        }}
        @media (prefers-color-scheme: dark) {{
          :root:not([data-theme="light"]) {{
            --qbm-bg: #0f1115;
            --qbm-ink: #e8eaee;
            --qbm-ink-soft: #a3adbb;
            --qbm-node-fill: #191d24;
            --qbm-node-stroke: #e8eaee;
            --qbm-hairline: #5b6572;
            --qbm-edge: #a3adbb;
            --qbm-compartment-fill: rgba(255,255,255,0.045);
          }}
        }}
        :root[data-theme="dark"] {{
          --qbm-bg: #0f1115;
          --qbm-ink: #e8eaee;
          --qbm-ink-soft: #a3adbb;
          --qbm-node-fill: #191d24;
          --qbm-node-stroke: #e8eaee;
          --qbm-hairline: #5b6572;
          --qbm-edge: #a3adbb;
          --qbm-compartment-fill: rgba(255,255,255,0.045);
        }}

        .qbm-canvas {{ fill: var(--qbm-bg); }}
        text {{ font-family: {SVG_FONT_STACK}; fill: var(--qbm-ink); }}
        .qbm-title  {{ font-size: {TITLE_SIZE}px; font-weight: 700; }}
        .qbm-subtitle,.qbm-caption {{ font-size: {SUBTITLE_SIZE}px; fill: var(--qbm-ink-soft); }}
        .qbm-caption {{ font-size: {CAPTION_SIZE}px; }}
        .qbm-label  {{ font-size: {NODE_SIZE}px; font-weight: 600; }}
        .qbm-sub    {{ font-size: {SUB_SIZE}px; fill: var(--qbm-ink-soft); font-weight: 400; }}
        .qbm-legend {{ font-size: {LEGEND_SIZE}px; fill: var(--qbm-ink-soft); }}

        .qbm-node {{ fill: var(--qbm-node-fill); stroke: var(--qbm-node-stroke); }}
        .qbm-unit {{ fill: var(--qbm-bg); stroke: var(--qbm-hairline); stroke-width: 0.9; }}
        .qbm-unit-label {{ font-size: {UNIT_SIZE}px; fill: var(--qbm-ink-soft);
                           font-weight: 600; letter-spacing: 0.01em; }}
        /* Evidence tier is a border channel — a hypothesis looks provisional. */
        .tier-T1 {{ stroke-width: 2.6; }}
        .tier-T2 {{ stroke-width: 1.7; }}
        .tier-T3 {{ stroke-width: 1.5; stroke-dasharray: 7 5; }}
        .tier-T4 {{ stroke-width: 0.9; stroke: var(--qbm-hairline); }}

        .qbm-compartment {{ fill: var(--qbm-compartment-fill); stroke-width: 1.2;
                            stroke-dasharray: 3 4; }}
        .qbm-compartment-label {{ font-size: 11px; font-weight: 700;
                                  letter-spacing: 0.08em; text-transform: uppercase; }}
        .qbm-edge {{ fill: none; stroke: var(--qbm-edge); stroke-width: 1.6; }}
        .qbm-edge-inhibition {{ stroke: {OKABE_ITO['vermillion']}; }}
        .qbm-edge-electron_transfer {{ stroke: {OKABE_ITO['blue']}; stroke-width: 2.0; }}
        .qbm-edge-cofactor_insertion {{ stroke: {OKABE_ITO['purple']}; stroke-dasharray: 5 4; }}
        .qbm-edge-redox_feedback {{ stroke: {OKABE_ITO['orange']}; stroke-dasharray: 2 4; }}
        .qbm-edge-energy_feedback {{ stroke: {OKABE_ITO['green']}; stroke-dasharray: 2 4; }}
        .qbm-edge-circadian_feedback {{ stroke: {OKABE_ITO['purple']}; stroke-dasharray: 2 4; }}
        .qbm-edge-hormonal_feedback {{ stroke: {OKABE_ITO['sky']}; stroke-dasharray: 2 4; }}
        .qbm-edge-indirect_influence {{ stroke-dasharray: 6 4; }}
        .qbm-edge-label-bg {{ fill: var(--qbm-bg); stroke: none; }}
        .qbm-edge-label {{ font-size: {EDGE_LABEL_SIZE}px; fill: var(--qbm-ink-soft); }}

        /* Data overlay: transparent until qbio.project fills it. Declared as a class
           rule rather than an inline style="fill:none" — an inline style outranks every
           selector, so the per-node overlay rules would silently never apply. */
        .qbm-overlay {{ stroke: none; fill: none; }}

        /* Time-course sparklines. The zero line is a real reference, not decoration:
           without it an all-up series and an all-down one look identical. */
        .qbm-spark-zero {{ stroke: var(--qbm-hairline); stroke-width: 0.8; }}
        .qbm-spark-line {{ stroke-width: 1.4; stroke-linecap: round; fill: none; }}
        .qbm-spark-dot  {{ stroke: none; }}
        """
    ).strip()


def _defs() -> str:
    """Arrowheads, one per stroke role so an arrow's head matches its line."""
    heads = {
        "arrow": "var(--qbm-edge)",
        "arrow-electron": OKABE_ITO["blue"],
        "arrow-cofactor": OKABE_ITO["purple"],
        "arrow-inhibit": OKABE_ITO["vermillion"],
    }
    out = ["<defs>"]
    for name, colour in heads.items():
        out.append(
            f'<marker id="{name}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
            f'markerHeight="7" orient="auto-start-reverse">'
            f'<path d="M0,0 L10,5 L0,10 z" style="fill:{colour}"/></marker>'
        )
    # Inhibition uses a bar, per SBGN.
    out.append(
        '<marker id="bar" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="7" '
        'markerHeight="7" orient="auto-start-reverse">'
        f'<rect x="4" y="0.5" width="2" height="9" style="fill:{OKABE_ITO["vermillion"]}"/></marker>'
    )
    out.append("</defs>")
    return "".join(out)


def _marker_for(edge_class: str) -> str:
    return {
        "electron_transfer": "arrow-electron",
        "cofactor_insertion": "arrow-cofactor",
        "inhibition": "bar",
    }.get(edge_class, "arrow")


UNIT_SIZE = 9.0
UNIT_PAD_X = 5.0
UNIT_H = 14.0
UNIT_GAP = 4.0
#: Gap between a unit chip and the node box below it. Chips used to straddle the
#: border, which left ~0.2px between chip and first text line — technically not
#: an overlap, but far too tight to read.
UNIT_CLEARANCE = 3.0


def unit_chips_svg(n: LaidOutNode) -> str:
    """SBGN units-of-information as chips on the node's top edge.

    These carry the cofactor a reader needs ("FMN", "2Fe-2S", "radical SAM"), so
    they belong on the drawing, not only in the SBGN annotation. Each chip is
    sized from its own measured text, and the row is centred on the node; a row
    wider than the node overhangs symmetrically rather than being clipped.
    """
    units = list(n.payload.get("units") or ())
    if not units:
        return ""
    widths = [measure(u, UNIT_SIZE)[0] + 2 * UNIT_PAD_X for u in units]
    total = sum(widths) + UNIT_GAP * (len(units) - 1)
    x = n.box.cx - total / 2.0
    y = n.box.y - UNIT_H - UNIT_CLEARANCE
    out = [f'<g class="qbm-units" data-units-for="{esc(n.id)}">']
    for u, w in zip(units, widths):
        out.append(
            f'<rect class="qbm-unit" data-unit-for="{esc(n.id)}" x="{x:.2f}" y="{y:.2f}" '
            f'width="{w:.2f}" height="{UNIT_H}" rx="3"/>'
        )
        out.append(
            f'<text class="qbm-unit-label" x="{x + w / 2:.2f}" y="{y + UNIT_H - 4:.2f}" '
            f'text-anchor="middle">{esc(u)}</text>'
        )
        x += w + UNIT_GAP
    out.append("</g>")
    return "".join(out)


def unit_row_box(n: LaidOutNode) -> Box | None:
    """Bounding box of a node's unit chips, so layout can keep them clear."""
    units = list(n.payload.get("units") or ())
    if not units:
        return None
    widths = [measure(u, UNIT_SIZE)[0] + 2 * UNIT_PAD_X for u in units]
    total = sum(widths) + UNIT_GAP * (len(units) - 1)
    return Box(n.box.cx - total / 2.0, n.box.y - UNIT_H - UNIT_CLEARANCE, total, UNIT_H)


def node_svg(n: LaidOutNode) -> str:
    """One node: rounded rect sized by the layout, then its measured text lines."""
    tier = n.payload.get("evidence_tier", "T4")
    qbo_id = n.payload.get("qbo", "")
    kind = n.payload.get("kind", "macromolecule")
    rx = 16.0 if kind in ("simple_chemical", "cofactor") else 7.0

    parts = [f'<g class="qbm-node-group" data-node-id="{esc(n.id)}" data-tier="{esc(tier)}"'
             f' data-qbo="{esc(qbo_id)}">']
    parts.append(
        f'<title>{esc(n.payload.get("tooltip") or n.payload.get("label") or n.id)}</title>'
    )
    parts.append(
        f'<rect class="qbm-node tier-{esc(tier)}" data-node-rect="{esc(n.id)}" '
        f'x="{n.box.x:.2f}" y="{n.box.y:.2f}" width="{n.box.w:.2f}" height="{n.box.h:.2f}" '
        f'rx="{rx}" ry="{rx}"/>'
    )
    # A slot the overlay writes into; empty in the base map so nothing implies data.
    parts.append(
        f'<rect class="qbm-overlay" data-overlay-for="{esc(n.id)}" '
        f'x="{n.box.x:.2f}" y="{n.box.y:.2f}" width="{n.box.w:.2f}" height="{n.box.h:.2f}" '
        f'rx="{rx}" ry="{rx}"/>'
    )

    total_h = len(n.lines) * n.font_size * LINE_SPACING + (
        len(n.sublines) * n.sub_font_size * LINE_SPACING if n.sublines else 0.0
    )
    # Centre the text in the height NOT reserved for a sparkline, so reserving
    # space moves the label up instead of leaving it under the trace.
    text_cy = n.box.y + (n.box.h - n.reserve_bottom) / 2.0
    y = text_cy - total_h / 2.0 + n.font_size * 0.86
    for line in n.lines:
        parts.append(
            f'<text class="qbm-label" data-text-for="{esc(n.id)}" x="{n.box.cx:.2f}" '
            f'y="{y:.2f}" text-anchor="middle">{esc(line)}</text>'
        )
        y += n.font_size * LINE_SPACING
    for line in n.sublines:
        parts.append(
            f'<text class="qbm-sub" data-text-for="{esc(n.id)}" x="{n.box.cx:.2f}" '
            f'y="{y:.2f}" text-anchor="middle">{esc(line)}</text>'
        )
        y += n.sub_font_size * LINE_SPACING
    parts.append("</g>")
    return "".join(parts)


EDGE_LABEL_SIZE = 9.5
EDGE_LABEL_H = 13.0


def _place_edge_label(
    label: str,
    sx: float,
    sy: float,
    ex: float,
    ey: float,
    obstacles: Iterable[Box],
) -> Box | None:
    """Find a spot on the edge where the label hits nothing. None = give up.

    Edge labels that land on top of a node box are exactly the defect the draft
    figures had, so an unplaceable label is DROPPED rather than drawn over a
    node. Callers are expected to count the drops — a map that loses many labels
    is a map that needs re-laning, and the build reports that instead of hiding it.
    """
    w = measure(label, EDGE_LABEL_SIZE)[0] + 6.0
    obstacles = list(obstacles)
    dx, dy = ex - sx, ey - sy
    length = max(1e-6, (dx * dx + dy * dy) ** 0.5)
    nx, ny = -dy / length, dx / length          # unit normal

    # Search along the edge AND well off to either side of it.
    #
    # Small offsets alone are not enough: when a third node sits between the two
    # endpoints — the ubiquinone pool and alternative oxidase have ubisemiquinone
    # between them — the entire straight path is blocked, and no amount of extra
    # lane width opens it, because the blocking node widens along with the lane.
    # Measured: going from ±20 to ±56 recovers labels that a 14% wider map did not.
    # The offset is capped so a label stays visibly associated with its own edge.
    offsets = (0.0, 12.0, -12.0, 22.0, -22.0, 34.0, -34.0, 46.0, -46.0, 56.0, -56.0)
    for t in (0.5, 0.38, 0.62, 0.28, 0.72, 0.18, 0.82):
        for offset in offsets:
            cx = sx + dx * t + nx * offset
            cy = sy + dy * t + ny * offset
            box = Box(cx - w / 2.0, cy - EDGE_LABEL_H / 2.0, w, EDGE_LABEL_H)
            if not any(box.overlaps(o, tol=-2.0) for o in obstacles):
                return box
    return None


def edge_svg(
    a: LaidOutNode,
    b: LaidOutNode,
    edge_class: str,
    label: str = "",
    obstacles: Iterable[Box] = (),
) -> tuple[str, bool]:
    """Render one edge. Returns (svg, label_was_drawn)."""
    (sx, sy), (ex, ey) = edge_anchors(a.box, b.box)
    marker = _marker_for(edge_class)
    out = [
        f'<g class="qbm-edge-group" data-edge="{esc(a.id)}-&gt;{esc(b.id)}" '
        f'data-edge-class="{esc(edge_class)}">',
        f'<path class="qbm-edge qbm-edge-{esc(edge_class)}" '
        f'd="M{sx:.2f},{sy:.2f} L{ex:.2f},{ey:.2f}" marker-end="url(#{marker})"/>',
    ]
    drawn = False
    if label:
        box = _place_edge_label(label, sx, sy, ex, ey, obstacles)
        if box is not None:
            drawn = True
            out.append(
                f'<rect class="qbm-edge-label-bg" data-edge-label="{esc(a.id)}-&gt;{esc(b.id)}" '
                f'x="{box.x:.2f}" y="{box.y:.2f}" width="{box.w:.2f}" '
                f'height="{box.h:.2f}" rx="3"/>'
            )
            out.append(
                f'<text class="qbm-edge-label" x="{box.cx:.2f}" y="{box.cy + 3.3:.2f}" '
                f'text-anchor="middle">{esc(label)}</text>'
            )
    out.append("</g>")
    return "".join(out), drawn


#: Vertical space reserved at the top of a compartment band for its own label.
#: Nodes are never placed here, so the label cannot land on a node or a unit chip.
COMPARTMENT_LABEL_BAND = 20.0


def compartment_svg(box: Box, compartment: str, label: str) -> str:
    """Draw a compartment band with its label in reserved space above the contents.

    The box passed in already clears its members; this extends it upward by
    COMPARTMENT_LABEL_BAND so the label has somewhere of its own to sit.
    """
    stroke, _slug = COMPARTMENT_STYLE.get(compartment, ("#3d3d3d", "other"))
    y = box.y - COMPARTMENT_LABEL_BAND
    h = box.h + COMPARTMENT_LABEL_BAND
    return (
        f'<g class="qbm-compartment-group" data-compartment="{esc(compartment)}">'
        f'<rect class="qbm-compartment" data-compartment-rect="{esc(compartment)}" '
        f'x="{box.x:.2f}" y="{y:.2f}" '
        f'width="{box.w:.2f}" height="{h:.2f}" rx="12" ry="12" '
        f'style="stroke:{stroke}"/>'
        f'<text class="qbm-compartment-label" x="{box.x + 14:.2f}" y="{y + 15:.2f}" '
        f'style="fill:{stroke}">{esc(label)}</text>'
        f"</g>"
    )


def compartment_tag_svg(n: LaidOutNode) -> str:
    """Tag a node that sits in a different compartment from its lane's band."""
    tag = n.payload.get("compartment_tag")
    if not tag:
        return ""
    w = measure(tag, UNIT_SIZE)[0] + 2 * UNIT_PAD_X
    x = n.box.cx - w / 2.0
    y = n.box.y2 + UNIT_CLEARANCE
    return (
        f'<g class="qbm-comp-tag" data-comp-tag-for="{esc(n.id)}">'
        f'<rect class="qbm-unit" x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" '
        f'height="{UNIT_H}" rx="7"/>'
        f'<text class="qbm-unit-label" x="{n.box.cx:.2f}" y="{y + UNIT_H - 4:.2f}" '
        f'text-anchor="middle">{esc(tag)}</text>'
        f"</g>"
    )


def tier_legend_svg(x: float, y: float, tiers_present: Sequence[str]) -> tuple[str, float]:
    """Legend for the tier border channel. Returns (svg, height consumed)."""
    rows = [t for t in ("T1", "T2", "T3", "T4") if t in tiers_present]
    if not rows:
        return "", 0.0
    out = [f'<g class="qbm-legend-group" transform="translate({x:.2f},{y:.2f})">']
    out.append('<text class="qbm-legend" x="0" y="0" style="font-weight:700">Evidence tier</text>')
    cy = 14.0
    for t in rows:
        out.append(
            f'<rect class="qbm-node tier-{t}" x="0" y="{cy:.2f}" width="26" height="14" rx="4"/>'
        )
        out.append(
            f'<text class="qbm-legend" x="34" y="{cy + 11:.2f}">'
            f"{t} — {esc(TIER_LABEL[t])}</text>"
        )
        cy += 21.0
    out.append("</g>")
    return "".join(out), cy + 6.0


def document(
    *,
    title: str,
    subtitle: str,
    caption: str,
    body: str,
    canvas: Box,
    legend: str = "",
    legend_h: float = 0.0,
) -> str:
    """Assemble the SVG. The viewBox comes from the measured content, so nothing clips.

    The tier legend gets RESERVED height in the header rather than being drawn over
    whatever happens to be empty at the top-left of the drawing. QBM-01's left margin
    was empty so it looked fine there; QBM-03's is not, and the legend landed on a
    compartment label. Reserving the space makes that impossible on any map.
    """
    # Title and subtitle are WRAPPED against the page width and the header is sized
    # from the resulting line count. They used to be single unwrapped lines, which fit
    # on QBM-01 and ran off the right edge of the narrower QBM-02 — the same class of
    # bug as an unwrapped caption, just at the top of the page.
    page_w_provisional = max(canvas.w, 560.0)
    title_lines, _, _ = text_block(title, TITLE_SIZE, page_w_provisional - 32, weight="700")
    subtitle_lines, _, _ = (
        text_block(subtitle, SUBTITLE_SIZE, page_w_provisional - 32) if subtitle else ([], 0.0, 0.0)
    )
    text_header = (
        14.0
        + len(title_lines) * TITLE_SIZE * LINE_SPACING
        + (len(subtitle_lines) * SUBTITLE_SIZE * LINE_SPACING + 6.0 if subtitle_lines else 0.0)
        + 12.0
    )
    header_h = text_header + (legend_h + 10.0 if legend else 0.0)
    # Wrap the caption against the final canvas width, then take the footer height
    # from the number of lines that actually resulted — sizing the footer from an
    # estimate is how a caption ends up running off the bottom of the image.
    total_w = page_w_provisional
    caption_lines, _, _ = _caption_block(caption, total_w - 32)
    footer_h = len(caption_lines) * CAPTION_SIZE * LINE_SPACING + 34.0
    total_h = canvas.h + header_h + footer_h

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'viewBox="0 0 {total_w:.2f} {total_h:.2f}" width="{total_w:.2f}" height="{total_h:.2f}" '
        f'role="img" aria-label="{esc(title)}">',
        f"<style>{_stylesheet()}</style>",
        _defs(),
        f'<rect class="qbm-canvas" x="0" y="0" width="{total_w:.2f}" height="{total_h:.2f}"/>',
        f'<g class="qbm-body" transform="translate({-canvas.x:.2f},{header_h - canvas.y:.2f})">{body}</g>',
    ]

    hy = 14.0 + TITLE_SIZE * 0.86
    for line in title_lines:
        parts.insert(-1, f'<text class="qbm-title" x="16" y="{hy:.2f}">{esc(line)}</text>')
        hy += TITLE_SIZE * LINE_SPACING
    if subtitle_lines:
        hy += 2.0
        for line in subtitle_lines:
            parts.insert(-1, f'<text class="qbm-subtitle" x="16" y="{hy:.2f}">{esc(line)}</text>')
            hy += SUBTITLE_SIZE * LINE_SPACING
    if legend:
        # Inside the reserved header band, below the wrapped title block and above the
        # drawing — so it can collide with neither.
        parts.append(f'<g transform="translate(0,{text_header + 8.0:.2f})">{legend}</g>')

    y = canvas.h + header_h + 18.0
    for line in caption_lines:
        parts.append(f'<text class="qbm-caption" x="16" y="{y:.2f}">{esc(line)}</text>')
        y += CAPTION_SIZE * LINE_SPACING
    parts.append("</svg>")
    return "\n".join(parts)


def _caption_block(caption: str, width: float) -> tuple[list[str], float, float]:
    from .layout import text_block

    if not caption:
        return [], 0.0, 0.0
    return text_block(caption, CAPTION_SIZE, max(240.0, width))


# ---------------------------------------------------------------------------
# data overlay
# ---------------------------------------------------------------------------
#: Divergent scale for log2 fold change. Blue (down) ↔ orange (up), both Okabe-Ito,
#: distinguishable under every common form of colour vision. The review's own figures
#: used pure red/green, which is the one pairing to avoid.
OVERLAY_DOWN = OKABE_ITO["blue"]
OVERLAY_UP = OKABE_ITO["vermillion"]


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def diverging_fill(value: float, vmax: float) -> str:
    """Map a signed value to an rgba fill. Zero is transparent, not a colour.

    Returning transparency at zero matters: a node with a measured value of zero and
    a node with no measurement at all must not look the same as a node that is
    mid-scale on some arbitrary palette.
    """
    if vmax <= 0:
        return "rgba(0,0,0,0)"
    t = max(-1.0, min(1.0, value / vmax))
    r, g, b = _hex_to_rgb(OVERLAY_UP if t >= 0 else OVERLAY_DOWN)
    return f"rgba({r},{g},{b},{abs(t) * 0.78:.3f})"


def overlay_svg(node_values: dict, vmax: float) -> str:
    """CSS + markup patch that fills each node's reserved overlay slot.

    Written as a `<style>` block keyed on `data-overlay-for`, so the overlay is a
    separate layer over an unmodified base map — the geometry is never recomputed
    for a data run, and the same base map can carry different studies.
    """
    rules = []
    chips = []
    for nid, nv in node_values.items():
        rules.append(
            f'[data-overlay-for="{esc(nid)}"] {{ fill: {diverging_fill(nv.value, vmax)}; }}'
        )
        # A significant node gets a visible marker, not just a deeper colour —
        # colour alone cannot carry a boolean legibly.
        if nv.significant:
            chips.append(nid)
    css = "<style>" + "\n".join(rules) + "</style>"
    return css


def overlay_legend_svg(x: float, y: float, vmax: float, label: str) -> tuple[str, float]:
    """Colour bar for the overlay, with the scale stated in real units."""
    w, h = 150.0, 11.0
    stops = 24
    out = [f'<g class="qbm-overlay-legend" transform="translate({x:.2f},{y:.2f})">']
    out.append(f'<text class="qbm-legend" x="0" y="0" style="font-weight:700">{esc(label)}</text>')
    for i in range(stops):
        t = -1.0 + 2.0 * i / (stops - 1)
        out.append(
            f'<rect x="{i * w / stops:.2f}" y="8" width="{w / stops + 0.6:.2f}" height="{h}" '
            f'style="fill:{diverging_fill(t * vmax, vmax)};stroke:none"/>'
        )
    out.append(f'<rect x="0" y="8" width="{w:.2f}" height="{h}" class="qbm-unit" style="fill:none"/>')
    out.append(f'<text class="qbm-legend" x="0" y="{8 + h + 11:.2f}">−{vmax:.2f}</text>')
    out.append(f'<text class="qbm-legend" x="{w:.2f}" y="{8 + h + 11:.2f}" text-anchor="end">+{vmax:.2f}</text>')
    out.append(f'<text class="qbm-legend" x="{w/2:.2f}" y="{8 + h + 11:.2f}" text-anchor="middle">0</text>')
    out.append("</g>")
    return "".join(out), 8 + h + 18


# ---------------------------------------------------------------------------
# time series: sparklines
# ---------------------------------------------------------------------------

SPARK_W = 58.0
SPARK_H = 17.0
SPARK_PAD_X = 4.0
#: Gap between the sparkline and the node's lower border.
SPARK_INSET = 3.0
#: What `layout_map(reserve_bottom=...)` must be given for the strip to fit.
SPARK_RESERVE = 17.0 + 3.0 + 2.0
#: Sparkline dot radius. Small enough that seven points on 58px stay distinguishable.
SPARK_DOT = 1.5


def sparkline_svg(
    node_boxes: dict,
    node_series: dict,
    vmax: float,
) -> tuple[str, list[str]]:
    """Draw one sparkline per node, straddling the node's bottom edge.

    A single-contrast overlay colours a node by one number. A time course has no single
    number that is honest: a gene that rises early and falls late averages to nothing,
    and colouring by the mean would report "no response" for a gene that responded
    twice. So the node is tinted by its most extreme timepoint and the whole trajectory
    is drawn beside it — the colour says how far it moved, the line says when.

    The sparkline sits in the same band the value chip already uses (centred on the
    node's lower border) rather than inside the box, because node boxes are sized to
    their text and a strip inside would land on the label.

    Returns (svg, collisions) where `collisions` names any sparkline that overlaps
    another node's box. It is returned rather than logged so the caller can assert it
    is empty — an overlapping sparkline is legible-looking and wrong, and the
    compartment-band bug got shipped precisely because nothing asserted on overlap.
    """
    if vmax <= 0:
        raise ValueError(
            "sparkline vmax must be positive; a degenerate scale means the join failed"
        )

    out: list[str] = []
    placed: list[tuple[str, float, float, float, float]] = []

    for nid, ns in node_series.items():
        box = node_boxes.get(nid)
        if box is None:
            continue
        peak = f"{ns.extreme():+.2f}"
        label_w = measure(peak, UNIT_SIZE)[0]
        total_w = SPARK_W + SPARK_PAD_X * 3 + label_w
        x = box.cx - total_w / 2.0
        # Sit INSIDE the strip the layout reserved at the bottom of the box. Straddling
        # the border — which is fine for the narrow value chip — put a 58px-wide trace
        # across the node's own AGI sublabel and over the compartment tag below it.
        y = box.y2 - SPARK_H - SPARK_INSET
        placed.append((nid, x, y, total_w, SPARK_H))

        g = [f'<g class="qbm-spark" data-spark-for="{esc(nid)}">']
        g.append(
            f'<rect class="qbm-unit" x="{x:.2f}" y="{y:.2f}" width="{total_w:.2f}" '
            f'height="{SPARK_H:.2f}" rx="{SPARK_H / 2:.2f}"/>'
        )

        # Plot area, with the zero line drawn: without it a reader cannot tell an
        # all-up series from an all-down one, since the trace is scaled either way.
        px = x + SPARK_PAD_X
        py = y + 2.5
        ph = SPARK_H - 5.0
        zero_y = py + ph / 2.0
        g.append(
            f'<line class="qbm-spark-zero" x1="{px:.2f}" y1="{zero_y:.2f}" '
            f'x2="{px + SPARK_W:.2f}" y2="{zero_y:.2f}"/>'
        )

        n = len(ns.points)
        step = SPARK_W / max(1, n - 1)
        pts: list[tuple[float, float, float]] = []
        for i, v in enumerate(ns.points):
            if v is None:
                continue
            t = max(-1.0, min(1.0, v / vmax))
            pts.append((px + i * step, zero_y - t * (ph / 2.0), v))

        # Segments are drawn individually and coloured by sign, so a crossing of the
        # zero line is visible as a colour change rather than only as a slope.
        for (x1, y1, v1), (x2, y2, _) in zip(pts, pts[1:]):
            colour = OKABE_ITO["vermillion"] if v1 >= 0 else OKABE_ITO["blue"]
            g.append(
                f'<line class="qbm-spark-line" x1="{x1:.2f}" y1="{y1:.2f}" '
                f'x2="{x2:.2f}" y2="{y2:.2f}" style="stroke:{colour}"/>'
            )
        for xi, yi, v in pts:
            colour = OKABE_ITO["vermillion"] if v >= 0 else OKABE_ITO["blue"]
            g.append(
                f'<circle class="qbm-spark-dot" cx="{xi:.2f}" cy="{yi:.2f}" '
                f'r="{SPARK_DOT}" style="fill:{colour}"/>'
            )

        g.append(
            f'<text class="qbm-unit-label" x="{x + total_w - SPARK_PAD_X:.2f}" '
            f'y="{y + SPARK_H - 5:.2f}" text-anchor="end">{esc(peak)}</text>'
        )
        g.append("</g>")
        out.append("".join(g))

    collisions = []
    for nid, x, y, w, h in placed:
        for other, ob in node_boxes.items():
            if other == nid:
                continue
            if x < ob.x2 and x + w > ob.x and y < ob.y2 and y + h > ob.y:
                collisions.append(f"{nid} sparkline overlaps node {other}")
    return "".join(out), collisions


def sparkline_legend_svg(x: float, y: float, timepoints, vmax: float) -> tuple[str, float]:
    """Explain the sparkline: what the axis is, and what the colour change means."""
    out = [f'<g class="qbm-spark-legend" transform="translate({x:.2f},{y:.2f})">']
    out.append(
        f'<text class="qbm-legend" x="0" y="0" style="font-weight:700">'
        f'Time course ({len(timepoints)} points: {esc(", ".join(timepoints))})</text>'
    )
    demo = [0.35, 0.75, 0.2, -0.4, -0.75, -0.3, 0.15]
    px, py, ph = 0.0, 10.0, 14.0
    zero_y = py + ph / 2.0
    out.append(
        f'<rect class="qbm-unit" x="-4" y="{py - 2:.2f}" width="{SPARK_W + 8:.2f}" '
        f'height="{ph + 4:.2f}" rx="{(ph + 4) / 2:.2f}"/>'
    )
    out.append(
        f'<line class="qbm-spark-zero" x1="{px:.2f}" y1="{zero_y:.2f}" '
        f'x2="{px + SPARK_W:.2f}" y2="{zero_y:.2f}"/>'
    )
    step = SPARK_W / (len(demo) - 1)
    dp = [(px + i * step, zero_y - v * ph / 2.0, v) for i, v in enumerate(demo)]
    for (x1, y1, v1), (x2, y2, _) in zip(dp, dp[1:]):
        c = OKABE_ITO["vermillion"] if v1 >= 0 else OKABE_ITO["blue"]
        out.append(
            f'<line class="qbm-spark-line" x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" '
            f'y2="{y2:.2f}" style="stroke:{c}"/>'
        )
    out.append(
        f'<text class="qbm-legend" x="{SPARK_W + 12:.2f}" y="{zero_y + 3:.2f}">'
        f'earliest → latest; the flat line is no change (log2 0); '
        f'vermillion above it, blue below; scale ±{vmax:.2f}</text>'
    )
    out.append("</g>")
    return "".join(out), ph + 16.0

#: The drawing is translated below the header, so anything appended to the finished
#: document in raw layout coordinates lands offset by exactly that amount. Overlay
#: marks are therefore emitted as a sibling group carrying the SAME transform.
_BODY_TF_RX = re.compile(r'<g class="qbm-body" transform="(translate\([^"]+\))"')


def body_transform(svg: str) -> str:
    """The body group's transform, for placing appended overlay marks in map space.

    Appending a mark directly before `</svg>` puts it in document coordinates while
    every node box is in layout coordinates — the two differ by the header height and
    the canvas origin. That silently detached every measured value from its node in the
    first published OSD-38 overlay: the numbers were correct and sat next to the wrong
    boxes, which is worse than no numbers at all.
    """
    m = _BODY_TF_RX.search(svg)
    if not m:
        raise ValueError(
            "no qbm-body group found — cannot place overlay marks in map coordinates"
        )
    return m.group(1)
