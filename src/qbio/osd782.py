"""
OSD-782: *Arabidopsis* under low-dose ionising radiation, as a dose × time factorial.

*"Multi-omics profiling reveals ethylene signalling as a key pathway underlying both
genetic and epigenetic responses to low-dose ionizing radiation"* — NASA OSDR
`OSD-782` / `GLDS-679`. Read off the study record: three declared factors,
`Ionizing Radiation`, `Absorbed Radiation Dose` and
`Time of Sample Collection After Treatment`; 36 samples; 3 doses × 4 timepoints ×
3 replicates.

**This is not a magnetic-field study and this module does not pretend otherwise.**
QBO's `field_regimes` vocabulary runs NNMF → hypomagnetic → GMF → static_MF → EMF, and
ionising radiation is not a point on that axis — it is a different perturbation
entirely. Nothing here writes to `qbio.ontology`, and the record carries its own
`PERTURBATION` block rather than borrowing a field regime.

**Why the atlas cares anyway.** Radiolysis produces radicals and ROS directly, and the
magnetic-field literature converges on the same redox machinery. So the question worth
asking is *overlap*: which QBO nodes move under radiation, and are they the ones that
move under field perturbation? A shared node is a lead — two perturbations converging on
chemistry the ontology already annotates — not evidence of magnetic sensitivity.

**The design subtlety that needs its own predicate.** The comparisons wanted are
irradiated-vs-control at matched time:

    (cesium-137 gamma radiation & 10 centigray & 1 hour)v(non-irradiated & 0 centigray & 1 hour)

These differ in **two** declared factors — radiation source *and* dose — because the two
are coupled by construction: there is no such thing as cesium-137 at 0 cGy. So
`osd27.Contrast.is_single_factor` is False for every one of them, and the OSD-27
field-isolating predicate would reject the entire set. `isolates_dose` below treats
{source, dose} as one coupled axis and requires everything else — here, time — to match.
"""
from __future__ import annotations

import dataclasses
import re
from typing import Sequence

from .osd27 import Contrast, parse_contrasts  # noqa: F401  (re-exported for callers)
from .osdr import OsdrError, fetch_study

ACCESSION = "782"
GLDS = "GLDS-679"
#: Verbatim from the OSDR study record. It ends "in Arabidopsis" — an earlier copy of
#: this constant was truncated because it was taken from a console probe that printed
#: only the first 140 characters, and a truncated study title is a wrong citation.
TITLE = (
    "Multi-omics profiling reveals ethylene signalling as a key pathway underlying "
    "both genetic and epigenetic responses to low-dose ionizing radiation in Arabidopsis"
)

#: The perturbation, recorded on its own terms. Deliberately NOT a QBO field regime.
PERTURBATION = {
    "kind": "ionising_radiation",
    "source": "cesium-137 gamma radiation",
    "doses_gy": [0.1, 1.0],
    "control": "non-irradiated",
    "note": (
        "Ionising radiation is a different perturbation axis from magnetic field "
        "strength, not a point on it. QBO's field_regimes vocabulary is not used here "
        "and is not extended."
    ),
}

IRRADIATED = "cesium-137 gamma radiation"
CONTROL = "non-irradiated"

#: The study labels dose in centigray; the atlas reports gray.
DOSE_GY = {"0 centigray": 0.0, "10 centigray": 0.1, "100 centigray": 1.0}

#: Ordered so a time course plots left to right rather than lexicographically, where
#: "24 hour" would precede "3 hour".
TIME_ORDER = ("1 hour", "3 hour", "24 hour", "72 hour")

_TIME_RX = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*hour", re.I)


class Osd782Error(Exception):
    """Raised when the OSD-782 design cannot be read as claimed. Never a warning."""


def hours(label: str) -> float:
    m = _TIME_RX.match(label)
    if not m:
        raise Osd782Error(f"cannot read a time from {label!r}")
    return float(m.group(1))


def _factor(side: Sequence[str], table: dict) -> str | None:
    for part in side:
        if part in table:
            return part
    return None


def isolates_dose(c: Contrast) -> bool:
    """True when the two sides differ in radiation dose and in nothing else.

    Not `is_single_factor`: dose and radiation source move together by construction,
    since the zero-dose condition IS the non-irradiated one. Requiring a single
    differing factor — the rule the OSD-27 page uses for magnetic field — rejects every
    dose comparison in this study.

    So: exactly the source and the dose may differ, one side must be irradiated and the
    other not, and every remaining factor (time) must match.
    """
    if len(c.left) != len(c.right):
        return False
    differing = c.differing
    if len(differing) != 2:
        return False
    pairs = [set(p) for p in differing]
    if {IRRADIATED, CONTROL} not in pairs:
        return False
    dose_pair = next((p for p in pairs if p != {IRRADIATED, CONTROL}), None)
    if dose_pair is None or not dose_pair <= set(DOSE_GY):
        return False
    # The control side must genuinely be the zero-dose one.
    return "0 centigray" in dose_pair


@dataclasses.dataclass(frozen=True)
class DosePoint:
    """One irradiated-vs-control comparison at one dose and one time."""

    contrast: Contrast
    dose_gy: float
    dose_label: str
    time_label: str

    @property
    def hours(self) -> float:
        return hours(self.time_label)


def _describe(c: Contrast) -> DosePoint:
    """Read dose and time off the irradiated side, which is always `left` after dedup."""
    dose_label = _factor(c.left, DOSE_GY)
    time_label = next((p for p in c.left if _TIME_RX.match(p)), None)
    if dose_label is None or time_label is None:
        raise Osd782Error(f"cannot read dose and time from {c.label!r}")
    return DosePoint(
        contrast=c, dose_gy=DOSE_GY[dose_label],
        dose_label=dose_label, time_label=time_label,
    )


def dose_points(contrasts: Sequence[Contrast]) -> list[DosePoint]:
    """The dose-isolating comparisons, deduplicated to irradiated-first.

    The contrasts file lists each comparison in both directions. Keeping both would
    double-count; keeping the wrong one would invert the sign of every fold change. The
    irradiated-first orientation is kept so a positive log2 fold change means
    "higher after irradiation" — the same rule the OSD-27 page uses for the magnet.
    """
    seen: dict[tuple, Contrast] = {}
    for c in contrasts:
        if not isolates_dose(c):
            continue
        # Key on the unordered pair of sides, so A-v-B and B-v-A collapse together.
        key = tuple(sorted([c.left, c.right]))
        irradiated_first = c.left[0] == IRRADIATED if c.left else False
        if key not in seen or irradiated_first:
            if key in seen and seen[key].left and seen[key].left[0] == IRRADIATED:
                continue          # already have the orientation we want
            seen[key] = c
    points = [_describe(c) for c in seen.values()]
    bad = [p for p in points if p.contrast.left[0] != IRRADIATED]
    if bad:
        raise Osd782Error(
            f"{len(bad)} contrast(s) survived deduplication control-first; a positive "
            f"log2 fold change would then mean 'higher WITHOUT irradiation'. "
            f"First: {bad[0].contrast.label!r}"
        )
    return sorted(points, key=lambda p: (p.dose_gy, p.hours))


def dose_series(contrasts: Sequence[Contrast]) -> dict[float, list[DosePoint]]:
    """Dose (Gy) -> its time course, ordered in time.

    Raises if the doses do not share a timebase: two series plotted on one axis with
    different timepoints would misdate every value.
    """
    out: dict[float, list[DosePoint]] = {}
    for p in dose_points(contrasts):
        out.setdefault(p.dose_gy, []).append(p)
    timebases = {d: tuple(p.time_label for p in ps) for d, ps in out.items()}
    if len(set(timebases.values())) > 1:
        raise Osd782Error(
            f"doses do not share a timebase: {timebases}. Plotting them on one axis "
            f"would misdate values."
        )
    return out


def find_de_file(accession: str = ACCESSION):
    """The differential-expression table. ~255 MB, so callers must stream it."""
    study = fetch_study(accession)
    hits = [f for f in study.files
            if "differential_expression" in f.file_name and "rRNArm" not in f.file_name]
    if not hits:
        raise OsdrError(f"OSD-{accession}: no differential expression file")
    return max(hits, key=lambda f: f.size_bytes)


def find_contrasts_file(accession: str = ACCESSION):
    study = fetch_study(accession)
    hits = [f for f in study.files
            if "contrasts" in f.file_name.lower() and "rRNArm" not in f.file_name]
    if not hits:
        raise OsdrError(f"OSD-{accession}: no contrasts file")
    return hits[0]
