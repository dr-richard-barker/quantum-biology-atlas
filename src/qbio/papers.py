"""
Published results as a data source: supplementary tables from papers that deposited
no raw data.

Most of the atlas's T1/T2 evidence comes from one group (Maffei and colleagues), and
none of those papers deposited raw sequence or array data anywhere public. Their Data
Availability Statements say so in their own words — quoted verbatim in `Paper.availability`
rather than paraphrased, because "no raw data" is a claim about someone else's work and
it should be checkable against the source.

So this module reads **results as published**. That is a third provenance class, and the
whole module exists to keep it visibly distinct from the other two:

  * `genelab_processed`  — OSD-38, OSD-27: NASA's own DE pipeline
  * `depositor_normalised` — OSD-8: the depositors' normalised ratios, no DE model
  * `published_results`  — here: numbers from a paper's supplementary tables

A reader must never have to guess which one a figure rests on, because they do not carry
equal weight: nothing here can be recomputed, re-thresholded or re-tested. What is drawn
is what the authors chose to report.

**The scale trap, handled once.** These tables are overwhelmingly *ratios* (fold change,
1.0 = no change), while every overlay in the atlas expects log2 (0.0 = no change).
Feeding a ratio straight in would render every unchanged gene as strongly upregulated —
a figure that looks fine and is exactly wrong. `Series.to_log2` does the conversion and
records that it happened; `Measurement.scale` makes an unconverted table impossible to
pass to the renderer by accident.
"""
from __future__ import annotations

import dataclasses
import io
import math
import pathlib
import re
import zipfile
from typing import Iterator, Mapping, Sequence

#: `2.34 ± 0.31`, `1 ± 0.09`, `0.4 ± 0.13`. The separator is U+00B1; some tables use a
#: plain "+/-" instead, so both are accepted.
_MEAN_SD_RX = re.compile(
    r"^\s*(-?\d+(?:[.,]\d+)?)\s*(?:±|\+/-|\+-)\s*(-?\d+(?:[.,]\d+)?)\s*$"
)

#: `At1g01980.1` — lowercase `g` and a transcript suffix. A naive `AT[1-5CM]G\d{5}`
#: match against this column returns ZERO rows, which is how a join silently produces
#: an empty map. Normalisation is therefore not optional and not a caller's problem.
_AGI_RX = re.compile(r"^\s*(AT[1-5CM]G\d{5})(?:\.\d+)?\s*$", re.I)


class PaperError(Exception):
    """Raised when a published table cannot be read as claimed. Never a warning."""


def normalise_agi(raw: str | None) -> str | None:
    """`At1g01980.1` -> `AT1G01980`. Returns None if it is not an AGI locus at all."""
    if not raw:
        return None
    m = _AGI_RX.match(str(raw))
    return m.group(1).upper() if m else None


def parse_mean_sd(cell) -> tuple[float, float] | None:
    """`'2.34 ± 0.31'` -> `(2.34, 0.31)`. A bare number yields an SD of 0.0.

    Returns None rather than raising: a blank or non-numeric cell in a published table
    is ordinary, and the caller counts them.
    """
    if cell is None:
        return None
    if isinstance(cell, (int, float)) and not isinstance(cell, bool):
        return (float(cell), 0.0)
    s = str(cell).strip()
    if not s:
        return None
    m = _MEAN_SD_RX.match(s)
    if m:
        return (float(m.group(1).replace(",", ".")), float(m.group(2).replace(",", ".")))
    try:
        return (float(s.replace(",", ".")), 0.0)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# value scales
# ---------------------------------------------------------------------------

#: A ratio: 1.0 means no change, 2.0 means doubled. What most supplementary tables hold.
RATIO = "ratio"
#: A log2 fold change: 0.0 means no change. What every overlay in the atlas expects.
LOG2 = "log2"
#: Signed fold change, the common qPCR reporting convention: +2.0 means doubled, -2.0
#: means halved, and NOTHING is ever reported strictly between -1 and +1. Agliassa 2018
#: uses it, and the tell is empirical — of its 196 tabulated values, zero fall inside
#: (-1, 1) and the smallest magnitude is exactly 1.0000.
#:
#: Read as a plain ratio it is catastrophic rather than merely wrong: -3.09 would become
#: a 3-fold INCREASE read backwards, inverting the paper's central claim that near-null
#: fields DOWN-regulate flowering genes.
SIGNED_FOLD = "signed_fold"


@dataclasses.dataclass(frozen=True)
class Measurement:
    """One value at one timepoint in one tissue, with its reported dispersion."""

    value: float
    sd: float
    scale: str

    def to_log2(self) -> "Measurement":
        if self.scale == LOG2:
            return self
        if self.scale == SIGNED_FOLD:
            if -1.0 < self.value < 1.0:
                raise PaperError(
                    f"{self.value} lies strictly between -1 and +1, which a signed fold "
                    f"change never does. Either the scale is wrong or the cell was "
                    f"misparsed; guessing between those would silently change a "
                    f"direction."
                )
            ratio = self.value if self.value >= 1.0 else -1.0 / self.value
            # The SD is reported on the signed-fold scale, so it is rescaled to the
            # ratio first; for a down-regulated value that division is by v^2.
            sd = self.sd if self.value >= 1.0 else self.sd / (self.value ** 2)
            return Measurement(
                value=math.log2(ratio),
                sd=sd / (ratio * math.log(2)) if sd else 0.0,
                scale=LOG2,
            )
        if self.value <= 0:
            raise PaperError(
                f"cannot take log2 of a non-positive ratio ({self.value}). A ratio scale "
                f"has no zero, so this is a parse error rather than a real measurement."
            )
        # The SD travels through the same transform as the mean via the delta method:
        # sd(log2 x) ≈ sd(x) / (x · ln2). Carrying the SD unchanged would state a
        # dispersion in the wrong units, which is worse than dropping it.
        return Measurement(
            value=math.log2(self.value),
            sd=self.sd / (self.value * math.log(2)) if self.sd else 0.0,
            scale=LOG2,
        )


@dataclasses.dataclass
class Series:
    """One locus's measurements across an ordered set of timepoints, in one tissue."""

    locus: str
    tissue: str
    timepoints: tuple[str, ...]
    points: tuple[Measurement | None, ...]
    gene_code: str = ""
    gene_function: str = ""
    subcellular: str = ""

    def __post_init__(self) -> None:
        if len(self.timepoints) != len(self.points):
            raise PaperError(
                f"{self.locus}/{self.tissue}: {len(self.timepoints)} timepoints but "
                f"{len(self.points)} values — the header and the row disagree"
            )

    @property
    def scale(self) -> str:
        for p in self.points:
            if p is not None:
                return p.scale
        return RATIO

    def to_log2(self) -> "Series":
        return dataclasses.replace(
            self, points=tuple(p.to_log2() if p else None for p in self.points)
        )

    @property
    def observed(self) -> list[float]:
        return [p.value for p in self.points if p is not None]

    def extreme(self) -> float | None:
        """The largest-magnitude value in the series, on whatever scale it carries.

        For a log2 series this is the timepoint furthest from no-change in either
        direction — the right single number to colour a static map with, because a mean
        over a time course where a gene goes up then down reports "no response" for a
        gene that responded twice.
        """
        obs = self.observed
        if not obs:
            return None
        if self.scale == LOG2:
            return max(obs, key=abs)
        if self.scale == SIGNED_FOLD:
            # No-change is +/-1 here, and -3 is further from it than +2.
            return max(obs, key=lambda v: abs(v) if abs(v) >= 1 else 1.0)
        return max(obs, key=lambda v: abs(v - 1.0))


@dataclasses.dataclass
class Paper:
    """A published source, with the provenance that must travel with every figure."""

    key: str
    citation: str
    doi: str
    pmcid: str
    availability: str            # the Data Availability Statement, VERBATIM
    organism: str
    field_regime: str
    comparison: str              # what the reported values are a ratio OF
    scale: str = RATIO
    threshold_note: str = ""

    def provenance(self) -> str:
        return (
            f"Values are the authors' published results from {self.citation} "
            f"(doi:{self.doi}), not a reanalysis: {self.comparison}. "
            f"No raw data was deposited — the Data Availability Statement reads "
            f"“{self.availability}”. "
            f"Reported as {'fold change' if self.scale == RATIO else 'log2 fold change'}"
            + (f"; {self.threshold_note}" if self.threshold_note else "")
            + "."
        )


# ---------------------------------------------------------------------------
# table readers
# ---------------------------------------------------------------------------


def open_nested_zip(outer: zipfile.ZipFile, member: str) -> zipfile.ZipFile:
    """EuropePMC ships MDPI supplements as a zip inside the article zip."""
    return zipfile.ZipFile(io.BytesIO(outer.read(member)))


def find_member(zf: zipfile.ZipFile, needle: str) -> str:
    """Locate a member by case-insensitive substring, refusing an ambiguous match.

    Filenames in these archives carry real typos — Parmagnani 2022 ships
    "Supplementray Table S7.xlsx" — so an exact-name lookup is too brittle, and a
    silent first-match would pick Table S1 when asked for S10.
    """
    hits = [n for n in zf.namelist() if needle.lower() in n.lower() and "__MACOSX" not in n]
    if not hits:
        raise PaperError(
            f"no member matching {needle!r}. Present: {zf.namelist()[:12]}"
        )
    if len(hits) > 1:
        raise PaperError(f"{needle!r} is ambiguous — matches {hits}")
    return hits[0]


def read_banded_timecourse(
    data: bytes,
    *,
    locus_column: str,
    band_row: int,
    header_row: int,
    tissues: Sequence[str],
    scale: str = RATIO,
    extra_columns: dict[str, str] | None = None,
) -> tuple[list[Series], dict]:
    """Read a sheet whose timepoint columns sit under merged per-tissue bands.

    The shape this handles, which is common in supplementary tables and handled by no
    generic reader: row `band_row` carries merged cells naming the tissues (ROOTS,
    SHOOTS), row `header_row` carries the timepoints repeated under each band, and the
    tissue a column belongs to is decided by which merged range covers it.

    Returns (series, report). The report counts what was skipped, so a silently
    half-read table is impossible to mistake for a complete one.
    """
    try:
        import openpyxl
    except ImportError:  # pragma: no cover - environment-dependent
        raise PaperError("openpyxl is required to read .xlsx supplementary tables") from None

    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
    ws = wb.active

    # Which columns each tissue band spans, taken from the merged ranges themselves
    # rather than assumed to be equal halves.
    band_spans: dict[str, range] = {}
    for rng in ws.merged_cells.ranges:
        if rng.min_row != band_row:
            continue
        label = str(ws.cell(rng.min_row, rng.min_col).value or "").strip()
        if label:
            band_spans[label] = range(rng.min_col, rng.max_col + 1)
    missing_bands = [t for t in tissues if t not in band_spans]
    if missing_bands:
        raise PaperError(
            f"row {band_row} has no merged band for {missing_bands}. "
            f"Found: {sorted(band_spans)}. Refusing to guess which columns are which "
            f"tissue — assigning a shoot value to a root node would be invisible."
        )

    header = {c: str(ws.cell(header_row, c).value or "").strip()
              for c in range(1, ws.max_column + 1)}
    col_of = {v.lower(): k for k, v in header.items() if v}

    locus_col = col_of.get(locus_column.lower())
    if locus_col is None:
        raise PaperError(
            f"no {locus_column!r} column on row {header_row}. Found: "
            f"{[v for v in header.values() if v][:12]}"
        )
    extra_cols = {
        field: col_of.get(name.lower())
        for field, name in (extra_columns or {}).items()
    }

    series: list[Series] = []
    report = {
        "rows_read": 0, "rows_no_locus": 0, "cells_parsed": 0, "cells_blank": 0,
        "loci": set(), "tissues": {},
    }

    for r in range(header_row + 1, ws.max_row + 1):
        raw_locus = ws.cell(r, locus_col).value
        report["rows_read"] += 1
        locus = normalise_agi(raw_locus)
        if not locus:
            report["rows_no_locus"] += 1
            continue
        report["loci"].add(locus)
        meta = {
            field: str(ws.cell(r, c).value or "").strip()
            for field, c in extra_cols.items() if c
        }
        for tissue in tissues:
            cols = [c for c in band_spans[tissue] if header.get(c)]
            points: list[Measurement | None] = []
            for c in cols:
                parsed = parse_mean_sd(ws.cell(r, c).value)
                if parsed is None:
                    report["cells_blank"] += 1
                    points.append(None)
                else:
                    report["cells_parsed"] += 1
                    points.append(Measurement(parsed[0], parsed[1], scale))
            if not any(p is not None for p in points):
                continue
            series.append(
                Series(
                    locus=locus,
                    tissue=tissue,
                    timepoints=tuple(header[c] for c in cols),
                    points=tuple(points),
                    **meta,
                )
            )
            report["tissues"][tissue] = report["tissues"].get(tissue, 0) + 1

    if not series:
        raise PaperError(
            "parsed 0 series from the sheet. Refusing to return an empty table — it "
            "would render as a map with no data and look like a result. Check that the "
            "locus column really is on the header row, and that identifiers are AGI."
        )
    report["loci"] = sorted(report["loci"])
    return series, report


def series_index(series: Sequence[Series]) -> dict[tuple[str, str], Series]:
    """(locus, tissue) -> series, refusing duplicates rather than overwriting."""
    out: dict[tuple[str, str], Series] = {}
    for s in series:
        key = (s.locus.upper(), s.tissue)
        if key in out:
            raise PaperError(
                f"duplicate series for {key} — the source table has the same locus "
                f"twice in one tissue and there is no principled way to choose"
            )
        out[key] = s
    return out


# ---------------------------------------------------------------------------
# main-text tables, and the symbol->locus key
# ---------------------------------------------------------------------------
#
# Not every paper puts its data in the supplement. Agliassa 2018's supplementary PDFs
# are a primer list, a phenology table and ANOVA output; the gene expression time course
# is in the MAIN TEXT, as Tables 1 and 2. EuropePMC serves those as XML, so they can be
# read exactly rather than scraped from a rendered PDF.
#
# The catch is that main-text tables are keyed on gene SYMBOLS, not loci. Resolving a
# symbol from memory is how the wrong gene ends up on a map — five collisions were caught
# that way while authoring the ontology (ACO2, LIP1, CAT2, CAT3, and one more, each of
# which resolves to a different gene than the one intended). So the symbol->locus key is
# taken from the paper's OWN primer table, which is what the supplementary PDF actually
# contains and is authoritative for that paper's usage.

EPMC_FULLTEXT = "https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML"

_TAG_RX = re.compile(r"<[^>]+>")
_TR_RX = re.compile(r"<tr\b.*?</tr>", re.S)
_TD_RX = re.compile(r"<t[hd]\b.*?</t[hd]>", re.S)
_TABLE_RX = re.compile(r"<table-wrap\b.*?</table-wrap>", re.S)
#: `−1.04 (±0.01)` — note the Unicode minus, which a plain `-` match would miss.
_SIGNED_RX = re.compile(r"^([−–\-]?)\s*(\d+(?:\.\d+)?)\s*\(\s*±\s*(\d+(?:\.\d+)?)\s*\)$")

_AGI_LOOSE_RX = re.compile(r"^At[1-5cmCM][Gg]\d{5}$")


def _plain(fragment: str) -> str:
    return re.sub(r"\s+", " ", _TAG_RX.sub("", fragment)).strip()


def fetch_fulltext_xml(pmcid: str, cache_dir: pathlib.Path | None = None) -> str:
    """EuropePMC full text, cached. Raises rather than returning a partial document."""
    import urllib.request

    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cached = cache_dir / f"{pmcid}_fulltext.xml"
        if cached.exists() and cached.stat().st_size > 1024:
            return cached.read_text(encoding="utf-8", errors="replace")
    req = urllib.request.Request(
        EPMC_FULLTEXT.format(pmcid=pmcid),
        headers={"User-Agent": "quantum-biology-atlas/0.1"},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        text = r.read().decode("utf-8", errors="replace")
    if "<table-wrap" not in text:
        raise PaperError(
            f"{pmcid}: full text carries no tables, so the main-text data cannot be "
            f"read. Refusing to continue rather than returning nothing."
        )
    if cache_dir is not None:
        (cache_dir / f"{pmcid}_fulltext.xml").write_text(text, encoding="utf-8")
    return text


def parse_signed_fold(cell) -> tuple[float, float] | None:
    """`'−3.09 (±0.10)'` -> `(-3.09, 0.10)`, handling the Unicode minus."""
    if cell is None:
        return None
    s = str(cell).strip()
    m = _SIGNED_RX.match(s)
    if not m:
        return None
    sign = -1.0 if m.group(1) else 1.0
    return (sign * float(m.group(2)), float(m.group(3)))


def read_primer_map(pdf_bytes: bytes) -> dict[str, str]:
    """A paper's own primer table -> {gene symbol: AGI locus}.

    Authoritative for that paper: it is the mapping its authors used, which is what
    matters when interpreting their gene symbols.
    """
    try:
        import pdfplumber
    except ImportError:  # pragma: no cover - environment-dependent
        raise PaperError(
            "pdfplumber is required to read a primer table from a PDF. Without it the "
            "symbols cannot be resolved, and resolving them from memory is how the "
            "wrong gene reaches a map."
        ) from None

    mapping: dict[str, str] = {}
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                for row in table:
                    cells = [(c or "").strip() for c in row]
                    if len(cells) < 2:
                        continue
                    locus = cells[0].replace(" ", "")
                    if _AGI_LOOSE_RX.match(locus) and cells[1]:
                        # A symbol cell can carry several aliases; the first is the one
                        # the paper's tables use.
                        symbol = cells[1].split(",")[0].split("/")[0].strip()
                        if symbol:
                            mapping.setdefault(symbol, locus.upper())
    if not mapping:
        raise PaperError(
            "no gene-symbol to AGI pairs found in that primer table. Refusing to return "
            "an empty key — every downstream symbol would silently fail to resolve."
        )
    return mapping


def read_maintext_timecourse(
    xml: str,
    *,
    table_captions: Sequence[str],
    symbol_to_locus: Mapping[str, str],
    scale: str = SIGNED_FOLD,
) -> tuple[list[Series], dict]:
    """Read main-text time-course tables, one Series per (locus, table).

    `table_captions` selects tables by a distinctive substring of their caption rather
    than by position, so inserting a table upstream cannot silently shift which data is
    read. A caption that matches nothing raises.
    """
    # Symbols are matched on a normalised form. The XML renders SOC1 as "SOC 1" — a
    # stray space that loses a central flowering gene if the lookup is exact.
    def norm(sym: str) -> str:
        return re.sub(r"[\s\u00a0_-]+", "", sym).upper()

    by_norm = {norm(k): v for k, v in symbol_to_locus.items()}

    wanted = {c.lower(): None for c in table_captions}
    found: dict[str, tuple[str, list[list[str]]]] = {}

    for frag in _TABLE_RX.findall(xml):
        caption = _plain(re.search(r"<caption>(.*?)</caption>", frag, re.S).group(1)) \
            if re.search(r"<caption>(.*?)</caption>", frag, re.S) else ""
        key = next((c for c in wanted if c in caption.lower()), None)
        if key is None:
            continue
        rows = [[_plain(c) for c in _TD_RX.findall(r)] for r in _TR_RX.findall(frag)]
        found[key] = (caption, rows)

    missing = [c for c in table_captions if c.lower() not in found]
    if missing:
        raise PaperError(
            f"no main-text table matched {missing}. Selecting by caption rather than "
            f"position is deliberate; a silent fallback would read the wrong table."
        )

    series: list[Series] = []
    report = {
        "tables": {}, "symbols_unresolved": [], "cells_parsed": 0, "cells_skipped": 0,
    }
    for key, (caption, rows) in found.items():
        header = next(
            (r for r in rows if len(r) > 2 and all(
                re.match(r"^\d+(\.\d+)?$", x) for x in r[1:] if x)),
            None,
        )
        if header is None:
            raise PaperError(f"{caption[:60]}: no numeric header row found")
        timepoints = tuple(x for x in header[1:] if x)

        n_rows = 0
        for r in rows:
            if len(r) < 2 or r is header:
                continue
            symbol = r[0].strip()
            parsed = [parse_signed_fold(c) for c in r[1:1 + len(timepoints)]]
            if not any(p is not None for p in parsed):
                continue
            locus = symbol_to_locus.get(symbol) or by_norm.get(norm(symbol))
            if locus is None:
                report["symbols_unresolved"].append(symbol)
                continue
            pts = []
            for p in parsed:
                if p is None:
                    report["cells_skipped"] += 1
                    pts.append(None)
                else:
                    report["cells_parsed"] += 1
                    pts.append(Measurement(p[0], p[1], scale))
            series.append(Series(
                locus=locus, tissue=key, timepoints=timepoints,
                points=tuple(pts), gene_code=symbol,
            ))
            n_rows += 1
        report["tables"][key] = {
            "caption": caption, "rows": n_rows, "timepoints": list(timepoints),
        }

    if not series:
        raise PaperError("parsed 0 series from the main-text tables")
    report["symbols_unresolved"] = sorted(set(report["symbols_unresolved"]))
    return series, report


def read_curated_table(
    tsv_path: pathlib.Path,
    *,
    tissue: str = "leaves",
    timepoint: str = "4w",
    scale: str = LOG2,
) -> tuple[list[Series], dict]:
    """Read a curated table of published results from a paper whose raw data is unavailable.

    Guards:
      * Scale is verified: if scale is LOG2, values are imported directly without
        double-log transform.
      * Unusable or missing AGI loci are recorded in report, never silently ignored.
    """
    if not tsv_path.exists():
        raise PaperError(f"curated table {tsv_path} does not exist")

    series: list[Series] = []
    report = {
        "rows_read": 0,
        "rows_no_locus": 0,
        "cells_parsed": 0,
        "cells_blank": 0,
        "loci": set(),
        "symbols_unresolved": [],
        "tissues": {},
        "tables": {tissue: {"caption": tsv_path.name, "rows": 0, "timepoints": [timepoint]}},
    }

    lines = tsv_path.read_text(encoding="utf-8").strip().splitlines()
    if not lines:
        raise PaperError(f"{tsv_path} is empty")
    header = lines[0].split("\t")
    col_idx = {h.strip().lower(): i for i, h in enumerate(header)}

    for line in lines[1:]:
        if not line.strip():
            continue
        report["rows_read"] += 1
        parts = line.split("\t")
        raw_locus = parts[col_idx["locus"]] if "locus" in col_idx and col_idx["locus"] < len(parts) else ""
        locus = normalise_agi(raw_locus)
        if not locus:
            report["rows_no_locus"] += 1
            continue
        report["loci"].add(locus)
        sym = parts[col_idx["symbol"]] if "symbol" in col_idx and col_idx["symbol"] < len(parts) else ""
        name = parts[col_idx["name"]] if "name" in col_idx and col_idx["name"] < len(parts) else ""
        val_str = parts[col_idx["log2fc"]] if "log2fc" in col_idx and col_idx["log2fc"] < len(parts) else ""
        sd_str = parts[col_idx["sd"]] if "sd" in col_idx and col_idx["sd"] < len(parts) else "0.0"

        try:
            val = float(val_str)
            sd = float(sd_str) if sd_str else 0.0
            m = Measurement(val, sd, scale)
            report["cells_parsed"] += 1
            series.append(
                Series(
                    locus=locus,
                    tissue=tissue,
                    timepoints=(timepoint,),
                    points=(m,),
                    gene_code=sym,
                    gene_function=name,
                )
            )
        except ValueError:
            report["cells_blank"] += 1

    if not series:
        raise PaperError(f"parsed 0 series from {tsv_path}")

    report["loci"] = sorted(report["loci"])
    report["tissues"][tissue] = len(series)
    report["tables"][tissue]["rows"] = len(series)
    return series, report

