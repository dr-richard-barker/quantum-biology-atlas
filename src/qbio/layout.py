"""
Deterministic layout with measured text.

The review's figures were drawn by placing `FancyBboxPatch` rectangles at
hand-chosen coordinates and dropping text inside them, which is why the draft
carries the margin note *"The text spills out of the box's"*. Nudging
coordinates does not fix that class of bug; it just moves it.

So the box is never chosen first. Here the pipeline is always:

    text -> measure it -> wrap it -> size the box around it -> place the box

A node's rectangle is *derived* from its wrapped label plus padding, so a label
cannot overflow its box by construction. Placement then works on already-sized
boxes in a lane grid with enforced minimum gutters, so boxes cannot overlap
either. The canvas is sized from the union of placed boxes, so nothing clips.

Text is measured with matplotlib's `TextPath`, which gives real glyph outlines
rather than a character-count estimate. `tests/test_map_legibility.py` re-checks
the published SVG in a real browser via `getBBox()`, so the acceptance test does
not simply re-run this module's own arithmetic.
"""
from __future__ import annotations

import dataclasses
import functools
import math
from typing import Iterable, Sequence

from matplotlib.font_manager import FontProperties
from matplotlib.textpath import TextPath

#: Every glyph is measured in this family/weight. Changing it changes geometry,
#: so the rendered SVG declares the same stack.
FONT_FAMILY = "DejaVu Sans"
SVG_FONT_STACK = "'DejaVu Sans', 'Helvetica Neue', Helvetica, Arial, sans-serif"

# Geometry constants, in SVG user units (px at 1:1).
PAD_X = 12.0          # horizontal padding inside a node box
PAD_Y = 9.0           # vertical padding inside a node box
LINE_SPACING = 1.28   # multiple of font size
MIN_GUTTER_X = 34.0   # minimum horizontal gap between sibling boxes
MIN_GUTTER_Y = 30.0   # minimum vertical gap between rows
COMPARTMENT_PAD = 26.0
CANVAS_MARGIN = 28.0


@functools.lru_cache(maxsize=4096)
def measure(text: str, size: float, weight: str = "normal") -> tuple[float, float]:
    """Return (width, height) of a single text run, in user units.

    Cached because a map re-measures the same short strings many times during
    wrapping search.
    """
    if not text:
        return (0.0, size)
    fp = FontProperties(family=FONT_FAMILY, size=size, weight=weight)
    tp = TextPath((0, 0), text, prop=fp)
    bb = tp.get_extents()
    # TextPath's bbox is ink-only; use the nominal em height for line boxes so
    # that lines without ascenders/descenders do not shrink the row.
    return (float(bb.width), float(size))


def wrap(text: str, size: float, max_width: float, weight: str = "normal") -> list[str]:
    """Greedy word wrap against measured width. Explicit newlines are honoured.

    A single word longer than `max_width` is never split — the box widens for it
    instead (see `Node.size`). Silently truncating a gene name would be worse
    than a wide box.
    """
    lines: list[str] = []
    for paragraph in text.split("\n"):
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = words[0]
        for word in words[1:]:
            trial = f"{current} {word}"
            if measure(trial, size, weight)[0] <= max_width:
                current = trial
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines


def text_block(text: str, size: float, max_width: float, weight: str = "normal") -> tuple[list[str], float, float]:
    """Wrap `text` and return (lines, block_width, block_height)."""
    lines = wrap(text, size, max_width, weight)
    width = max((measure(ln, size, weight)[0] for ln in lines), default=0.0)
    height = len(lines) * size * LINE_SPACING
    return lines, width, height


@dataclasses.dataclass
class Box:
    """An axis-aligned rectangle in SVG user units, origin top-left."""

    x: float = 0.0
    y: float = 0.0
    w: float = 0.0
    h: float = 0.0

    @property
    def x2(self) -> float:
        return self.x + self.w

    @property
    def y2(self) -> float:
        return self.y + self.h

    @property
    def cx(self) -> float:
        return self.x + self.w / 2.0

    @property
    def cy(self) -> float:
        return self.y + self.h / 2.0

    def overlaps(self, other: "Box", tol: float = 0.0) -> bool:
        return not (
            self.x2 <= other.x + tol
            or other.x2 <= self.x + tol
            or self.y2 <= other.y + tol
            or other.y2 <= self.y + tol
        )

    def contains(self, other: "Box", tol: float = 0.01) -> bool:
        return (
            self.x - tol <= other.x
            and self.y - tol <= other.y
            and other.x2 <= self.x2 + tol
            and other.y2 <= self.y2 + tol
        )

    def expanded(self, pad: float) -> "Box":
        return Box(self.x - pad, self.y - pad, self.w + 2 * pad, self.h + 2 * pad)


@dataclasses.dataclass
class LaidOutNode:
    """A node after measurement and placement."""

    id: str
    box: Box
    lines: list[str]
    font_size: float
    font_weight: str
    sublines: list[str] = dataclasses.field(default_factory=list)
    sub_font_size: float = 0.0
    lane: str | None = None
    row: int = 0
    col: int = 0
    payload: dict = dataclasses.field(default_factory=dict)
    #: Height at the bottom of the box reserved for something other than text — the
    #: time-course sparkline. Text is centred in the REMAINING height, so reserving
    #: space actually moves the label up rather than just making the box taller.
    reserve_bottom: float = 0.0

    def text_box(self) -> Box:
        """Bounding box of the laid-out text, used by the legibility assertions."""
        width = max((measure(ln, self.font_size, self.font_weight)[0] for ln in self.lines), default=0.0)
        height = len(self.lines) * self.font_size * LINE_SPACING
        if self.sublines:
            width = max(width, max(measure(s, self.sub_font_size)[0] for s in self.sublines))
            height += len(self.sublines) * self.sub_font_size * LINE_SPACING
        return Box(self.box.cx - width / 2.0, self.box.cy - height / 2.0, width, height)


def size_node(
    label: str,
    font_size: float,
    *,
    sublabel: str = "",
    sub_font_size: float = 0.0,
    preferred_width: float = 190.0,
    min_width: float = 96.0,
    weight: str = "normal",
) -> tuple[Box, list[str], list[str]]:
    """Size a box around its text. The box follows the text, never the reverse.

    `preferred_width` is a wrapping target, not a cap: a single unbreakable token
    wider than it widens the box rather than being clipped or truncated.
    """
    lines, w, h = text_block(label, font_size, preferred_width, weight)
    sublines: list[str] = []
    if sublabel:
        sub_size = sub_font_size or font_size * 0.8
        sublines, sw, sh = text_block(sublabel, sub_size, preferred_width)
        w = max(w, sw)
        h += sh

    # Widen for any single token that could not be wrapped.
    for token in label.replace("\n", " ").split() + (sublabel.split() if sublabel else []):
        w = max(w, measure(token, font_size, weight)[0])

    return (
        Box(0.0, 0.0, max(min_width, w + 2 * PAD_X), h + 2 * PAD_Y),
        lines,
        sublines,
    )


def place_rows(
    rows: Sequence[Sequence[LaidOutNode]],
    *,
    origin_x: float = 0.0,
    origin_y: float = 0.0,
    gutter_x: float = MIN_GUTTER_X,
    gutter_y: float | Sequence[float] = MIN_GUTTER_Y,
    align: str = "center",
) -> Box:
    """Place pre-sized nodes as centred rows. Returns the bounding box used.

    Gutters are minimums that are always honoured, so two boxes in the same row
    cannot touch, and two rows cannot touch.

    `gutter_y` may be a single value, or one value per gap between consecutive
    rows (so `len(rows) - 1` of them). The per-gap form exists because a gap where
    the compartment changes has to swallow two compartment paddings plus a label
    band, which is much more than a gap inside one compartment needs — using one
    value for both either overlaps the bands or wastes vertical space everywhere.
    """
    row_widths = [
        sum(n.box.w for n in row) + gutter_x * max(0, len(row) - 1) for row in rows
    ]
    total_width = max(row_widths, default=0.0)

    if isinstance(gutter_y, (int, float)):
        gutters = [float(gutter_y)] * max(0, len(rows) - 1)
    else:
        gutters = [float(g) for g in gutter_y]
        if len(gutters) != max(0, len(rows) - 1):
            raise ValueError(
                f"gutter_y has {len(gutters)} values but {len(rows)} rows need "
                f"{max(0, len(rows) - 1)}"
            )

    y = origin_y
    for i, (row, row_width) in enumerate(zip(rows, row_widths)):
        if not row:
            continue
        if align == "center":
            x = origin_x + (total_width - row_width) / 2.0
        elif align == "left":
            x = origin_x
        else:
            raise ValueError(f"unknown align {align!r}")
        row_height = max(n.box.h for n in row)
        for node in row:
            node.box.x = x
            node.box.y = y + (row_height - node.box.h) / 2.0   # vertically centre in the row
            x += node.box.w + gutter_x
        y += row_height
        if i < len(gutters):
            y += gutters[i]

    return Box(origin_x, origin_y, total_width, max(0.0, y - origin_y))


def bounding_box(nodes: Iterable[LaidOutNode], pad: float = CANVAS_MARGIN) -> Box:
    """Union of every node box, padded. The canvas is sized from this, so nothing clips."""
    boxes = [n.box for n in nodes]
    if not boxes:
        return Box(0, 0, pad * 2, pad * 2)
    x1 = min(b.x for b in boxes) - pad
    y1 = min(b.y for b in boxes) - pad
    x2 = max(b.x2 for b in boxes) + pad
    y2 = max(b.y2 for b in boxes) + pad
    return Box(x1, y1, x2 - x1, y2 - y1)


def resolve_collisions(nodes: Sequence[LaidOutNode], gutter: float = 8.0, max_passes: int = 64) -> int:
    """Nudge overlapping boxes apart along the axis of least displacement.

    Row placement already prevents overlap within the grid; this is the backstop
    for nodes positioned by explicit coordinates. Returns the number of moves
    made, so a caller can assert it converged.
    """
    moves = 0
    for _ in range(max_passes):
        collided = False
        for i, a in enumerate(nodes):
            for b in nodes[i + 1 :]:
                if not a.box.overlaps(b.box, tol=-gutter):
                    continue
                collided = True
                moves += 1
                dx = (b.box.cx - a.box.cx) or 1e-6
                dy = (b.box.cy - a.box.cy) or 1e-6
                overlap_x = (a.box.w + b.box.w) / 2.0 + gutter - abs(dx)
                overlap_y = (a.box.h + b.box.h) / 2.0 + gutter - abs(dy)
                if overlap_x < overlap_y:
                    shift = math.copysign(overlap_x / 2.0, dx)
                    a.box.x -= shift
                    b.box.x += shift
                else:
                    shift = math.copysign(overlap_y / 2.0, dy)
                    a.box.y -= shift
                    b.box.y += shift
        if not collided:
            return moves
    raise RuntimeError(
        f"layout did not converge after {max_passes} passes ({moves} moves) — "
        "the map declares more nodes than its lanes can hold without overlap"
    )


def edge_anchors(a: Box, b: Box) -> tuple[tuple[float, float], tuple[float, float]]:
    """Pick the two box-edge points for an arrow between `a` and `b`.

    Anchors sit on the box border rather than the centre, so an arrowhead lands
    on the edge instead of disappearing under the node.
    """
    dx = b.cx - a.cx
    dy = b.cy - a.cy
    if abs(dx) * a.h >= abs(dy) * a.w:          # leaves through a vertical edge
        sx = a.x2 if dx > 0 else a.x
        sy = a.cy + (dy / dx * (sx - a.cx) if dx else 0.0)
        ex = b.x if dx > 0 else b.x2
        ey = b.cy + (dy / dx * (ex - b.cx) if dx else 0.0)
    else:                                        # leaves through a horizontal edge
        sy = a.y2 if dy > 0 else a.y
        sx = a.cx + (dx / dy * (sy - a.cy) if dy else 0.0)
        ey = b.y if dy > 0 else b.y2
        ex = b.cx + (dx / dy * (ey - b.cy) if dy else 0.0)
    return (sx, sy), (ex, ey)
