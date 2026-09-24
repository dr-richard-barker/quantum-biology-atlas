"""
OSD-8: *Arabidopsis* callus in a diamagnetic levitation magnet, with non-magnetic
gravity controls.

*"Gravitational and magnetic field variations synergize to cause subtle variations in the
global transcriptional state of Arabidopsis in vitro callus cultures"* (Manzano et al.
2012, BMC Genomics 13:105, doi:10.1186/1471-2164-13-105). Note the first author is
Manzano, not Herranz — Herranz is the first author of the *fly* study behind OSD-27
(BMC Genomics 13:52), and the two are easy to swap.

**Why this study is worth more than its provenance suggests.** It declares `Magnetic
Field` and `Altered Gravity` as *separate* factors and includes gravity controls that
use no magnet at all — a random-positioning machine for simulated µg and a large-diameter
centrifuge for 2g. That makes it possible to hold gravity constant and vary only the
field, which almost nothing else in this literature allows. One group does it directly:

    MAG 1g*  —  1g inside the magnet (16.5 T) against 1g outside it (0 T)

Effective gravity is 1g in both channels. The field is the only thing that differs. In
the anchor species, so no orthology is needed.

**Three things about the provenance, all stated on the page.**

*No GeneLab differential expression exists.* There are 20 two-colour arrays and a
normalized archive, and no contrasts file. Values are the depositors' own normalized log
ratios (E-GEOD-29787 / GSE29787), not a NASA pipeline output, and no model was fitted —
so there is no adjusted p-value and none is invented.

*The dye swap is already handled — by them, not by us.* Arrays alternate `Ct-Cy3/Exp-Cy5`
and `Ct-Cy5/Exp-Cy3`, and GEO's own value definition reads *"normalized log2 ratio
representing test g / reference 1g"*. So VALUE is already oriented test-over-reference
regardless of dye. Had it been raw log(Cy5/Cy3) instead, averaging replicates would have
cancelled real signal to zero and the result would have looked like a clean null.

*The probe-to-gene join needs care.* The processed tables key on bare Agilent feature
numbers (`1`, `2`, `3`), so the GPL9020 platform table is required. Its `GENE_SYMBOL`
column holds an AGI locus only sometimes — often it is a trivial name like `AtATG18b` —
and reading only that column covers **17 of the atlas's 125 loci**. The authoritative
identifier is in `ACCESSION_STRING` as `tair|AT4G30510.1`, which covers **all 125**.
"""
from __future__ import annotations

import dataclasses
import pathlib
import re
import statistics
from typing import Iterable, Sequence

ACCESSION = "8"
PUBLICATION_DOI = "10.1186/1471-2164-13-105"
GEO_SERIES = "GSE29787"
PLATFORM = "GPL9020"

#: Field strengths quoted in the study record, in tesla. Strong-field, like OSD-27 —
#: the opposite end of the axis from the review's near-null work.
FIELD_TESLA = {"mg*": 10.1, "0.1g*": 14.7, "1g*": 16.5, "1.9g*": 14.7, "2g*": 10.1}

#: `tair|AT4G30510.1` — the authoritative AGI in the platform's ACCESSION_STRING.
_TAIR_RX = re.compile(r"tair\|(AT[1-5CM]G\d{5})", re.I)
_AGI_RX = re.compile(r"^AT[1-5CM]G\d{5}$", re.I)


class Osd8Error(Exception):
    """Raised when the OSD-8 join cannot be trusted. Never a warning."""


@dataclasses.dataclass(frozen=True)
class Group:
    """One experimental group: several arrays sharing a test and reference condition."""

    key: str
    label: str
    test: str
    reference: str
    samples: tuple[str, ...]
    field_tesla: float
    reference_field_tesla: float
    gravity: str
    reference_gravity: str

    @property
    def isolates_field(self) -> bool:
        """True when the two channels differ in field and in nothing else.

        This is the whole point of the study for the atlas's purposes, and it is
        computed rather than asserted so a mis-typed group cannot claim it.
        """
        return (
            self.gravity == self.reference_gravity
            and self.field_tesla != self.reference_field_tesla
        )

    @property
    def isolates_gravity(self) -> bool:
        """True when gravity changes and the field does not — the non-magnetic controls."""
        return (
            self.gravity != self.reference_gravity
            and self.field_tesla == self.reference_field_tesla
        )


#: The design, read off the GEO sample titles and characteristics for all 20 arrays.
#: `oML` is outside the magnet; `1g*`, `mg*` etc. are effective gravities produced
#: inside it. RPM and LDC reach their gravities with no magnet at all.
GROUPS: tuple[Group, ...] = (
    Group("MAG_1g", "Magnet 1g* vs outside, 16.5 T", "MAG 1g*", "1g control outside the magnet",
          ("GSM738246", "GSM738247", "GSM738248"), 16.5, 0.0, "1g", "1g"),
    Group("MAG_mg", "Magnet simulated µg vs 1g outside", "MAG mg*", "1g control outside the magnet",
          ("GSM738240", "GSM738241", "GSM738242"), 10.1, 0.0, "µg", "1g"),
    Group("MAG_0.1g", "Magnet 0.1g* vs 1g outside", "MAG 0.1g*", "1g control outside the magnet",
          ("GSM738243", "GSM738244", "GSM738245"), 14.7, 0.0, "0.1g", "1g"),
    Group("MAG_1.9g", "Magnet 1.9g* vs 1g outside", "MAG 1.9g*", "1g control outside the magnet",
          ("GSM738249", "GSM738250"), 14.7, 0.0, "1.9g", "1g"),
    Group("MAG_2g", "Magnet 2g* vs 1g outside", "MAG 2g*", "1g control outside the magnet",
          ("GSM738251", "GSM738252", "GSM738253"), 10.1, 0.0, "2g", "1g"),
    Group("RPM_mg", "Random-positioning µg vs its 1g control (no magnet)", "RPM mg*",
          "RPM 1g control", ("GSM738254", "GSM738255", "GSM738256"), 0.0, 0.0, "µg", "1g"),
    Group("LDC_2g", "Centrifuge 2g vs its 1g control (no magnet)", "LDC 2g", "LDC 1g control",
          ("GSM738237", "GSM738238", "GSM738239"), 0.0, 0.0, "2g", "1g"),
)

#: GEO's own definition of the VALUE column, quoted so the page can show it.
VALUE_DEFINITION = "normalized log2 ratio representing test g /reference 1g"


# ---------------------------------------------------------------------------
# platform
# ---------------------------------------------------------------------------


def parse_platform(path: pathlib.Path) -> tuple[dict[str, list[str]], dict]:
    """GPL9020 -> {AGI locus: [reporter ids]}, plus a report of how it was derived.

    AGI comes from `ACCESSION_STRING` first and `GENE_SYMBOL` only when that column
    happens to hold an AGI itself. Reading `GENE_SYMBOL` alone is the obvious approach
    and it is wrong: it reaches 17 of the atlas's 125 loci rather than all 125, because
    the column often carries a trivial name (`AtATG18b`) instead of a locus.
    """
    rows: list[list[str]] = []
    started = False
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if line.startswith("!platform_table_begin"):
                started = True
                continue
            if line.startswith("!platform_table_end"):
                break
            if started:
                rows.append(line.rstrip("\n").split("\t"))
    if len(rows) < 2:
        raise Osd8Error(f"{path.name}: no platform table found")

    header = rows[0]
    try:
        i_id = header.index("ID")
        i_ctl = header.index("CONTROL_TYPE")
        i_sym = header.index("GENE_SYMBOL")
        i_acc = header.index("ACCESSION_STRING")
    except ValueError as exc:
        raise Osd8Error(f"{path.name}: missing expected column ({exc})") from None

    by_locus: dict[str, list[str]] = {}
    n_probes = n_control = n_unmapped = 0
    from_accession = from_symbol = 0
    for r in rows[1:]:
        if len(r) <= max(i_id, i_ctl, i_sym, i_acc):
            continue
        if r[i_ctl].strip().upper() != "FALSE":
            n_control += 1
            continue
        n_probes += 1
        pid = r[i_id].strip()
        loci = {g.upper() for g in _TAIR_RX.findall(r[i_acc] or "")}
        if loci:
            from_accession += 1
        sym = (r[i_sym] or "").strip()
        if _AGI_RX.match(sym):
            if sym.upper() not in loci:
                from_symbol += 1
            loci.add(sym.upper())
        if not loci:
            n_unmapped += 1
            continue
        for g in loci:
            by_locus.setdefault(g, []).append(pid)

    if not by_locus:
        raise Osd8Error(
            f"{path.name}: parsed 0 AGI loci from {n_probes} probes. Refusing to return "
            f"an empty platform map — every downstream join would silently match nothing."
        )
    report = {
        "platform": PLATFORM,
        "rows": len(rows) - 1,
        "probes": n_probes,
        "control_spots": n_control,
        "probes_without_agi": n_unmapped,
        "probes_with_agi_from_accession_string": from_accession,
        "probes_with_agi_only_from_gene_symbol": from_symbol,
        "distinct_loci": len(by_locus),
    }
    return by_locus, report


# ---------------------------------------------------------------------------
# samples
# ---------------------------------------------------------------------------


def read_sample_table(path: pathlib.Path) -> dict[str, float]:
    """One GSM sample table -> {reporter id: log2 ratio}."""
    out: dict[str, float] = {}
    with path.open(encoding="utf-8", errors="replace") as fh:
        header = fh.readline().rstrip("\n").split("\t")
        if len(header) < 2 or "VALUE" not in [h.strip().upper() for h in header]:
            raise Osd8Error(f"{path.name}: expected a VALUE column, got {header}")
        i_val = [h.strip().upper() for h in header].index("VALUE")
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) <= i_val:
                continue
            rid = parts[0].strip()
            try:
                out[rid] = float(parts[i_val])
            except ValueError:
                continue
    if not out:
        raise Osd8Error(f"{path.name}: no usable values")
    return out


def group_values(
    group: Group,
    sample_dir: pathlib.Path,
    by_locus: dict[str, list[str]],
    *,
    probe_aggregator=statistics.median,
    replicate_aggregator=statistics.fmean,
) -> tuple[dict[str, float], dict]:
    """Average a group's replicate arrays and collapse probes onto loci.

    Probes for one locus are combined by **median**, not mean: a 45k-feature array
    carries several probes per gene and one bad spot should not drag the locus with it.
    Replicates are then combined by mean, which is what the depositors' own analysis
    does with these ratios.
    """
    per_sample: list[dict[str, float]] = []
    missing: list[str] = []
    for gsm in group.samples:
        p = sample_dir / f"{gsm}_sample_table.txt"
        if not p.exists():
            missing.append(gsm)
            continue
        per_sample.append(read_sample_table(p))
    if missing:
        raise Osd8Error(
            f"{group.key}: sample table(s) missing for {missing}. Refusing to average a "
            f"group with fewer replicates than declared — the page states n per group."
        )

    values: dict[str, float] = {}
    n_probes_used = 0
    for locus, probes in by_locus.items():
        per_rep: list[float] = []
        for table in per_sample:
            vals = [table[p] for p in probes if p in table]
            if vals:
                per_rep.append(float(probe_aggregator(vals)))
                n_probes_used += len(vals)
        if per_rep:
            values[locus] = float(replicate_aggregator(per_rep))
    if not values:
        raise Osd8Error(f"{group.key}: joined 0 loci — the reporter ids did not match")
    return values, {
        "group": group.key,
        "arrays": list(group.samples),
        "n_arrays": len(per_sample),
        "loci_with_values": len(values),
        "probe_observations": n_probes_used,
    }


def field_isolating_groups(groups: Sequence[Group] = GROUPS) -> list[Group]:
    return [g for g in groups if g.isolates_field]


def gravity_only_groups(groups: Sequence[Group] = GROUPS) -> list[Group]:
    return [g for g in groups if g.isolates_gravity]
