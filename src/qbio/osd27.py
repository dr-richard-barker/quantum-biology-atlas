"""
OSD-27: Drosophila in a diamagnetic levitation magnet.

The study is *"Transcription profiling of Drosophila exposed to a levitation magnet for
different lengths of time"* (Herranz et al. 2012, BMC Genomics 13:52,
doi:10.1186/1471-2164-13-52) — 54 arrays, flies held in a 16.5 T superconducting magnet.

Two things make this a careful dataset to use, and both are handled here rather than in
prose:

**It is a STRONG-field study.** Roughly 16.5 T, against the ~50 uT geomagnetic field. It
sits at the opposite end of the field-strength axis from the near-null work the atlas was
built around. QBO's `field_regimes` vocabulary already spans both, so the data is in
scope — but nothing here should let a reader treat the two regimes as interchangeable.

**Diamagnetic levitation confounds field with gravity.** Inside the bore, position
determines effective gravity: 0g*, 1g* and 2g* are all at high field. So most of the
study's 420 contrasts change field AND effective gravity together. `field_isolating_contrasts`
returns only those where the magnet is compared against Earth at matched effective
gravity, duration, temperature and sex — the comparisons that isolate the field.

The differential-expression table is ~623 MB across ~1,690 columns, far over
`qbio.osdr.MAX_DE_BYTES`. `slice_contrasts` streams it a row at a time and keeps only the
columns asked for, so memory stays flat and the output is a few hundred KB.
"""
from __future__ import annotations

import csv
import dataclasses
import io
import json
import pathlib
import re
import urllib.request
from typing import Iterator, Sequence

from .osdr import OSDR, OsdrError, OsdrFile, fetch_study, _choose_gene_column

ACCESSION = "27"
PUBLICATION_DOI = "10.1186/1471-2164-13-52"
#: Nominal field strength of the levitation magnet used in this study, for the record.
#: Stated in the source publication; the atlas does not measure it.
FIELD_TESLA_NOMINAL = 16.5

#: The factor value naming the magnet-vs-Earth axis.
MAGNET_1G = "1G by magnetic levitator"
EARTH_1G = "1G on Earth"


@dataclasses.dataclass(frozen=True)
class Contrast:
    """One column pair in the DE table, with its two sides parsed into factors."""

    label: str
    left: tuple[str, ...]
    right: tuple[str, ...]

    @property
    def differing(self) -> list[tuple[str, str]]:
        return [(a, b) for a, b in zip(self.left, self.right) if a != b]

    @property
    def is_single_factor(self) -> bool:
        return len(self.left) == len(self.right) and len(self.differing) == 1

    @property
    def isolates_field(self) -> bool:
        """Magnet vs Earth at the same effective gravity, everything else matched."""
        return self.is_single_factor and {MAGNET_1G, EARTH_1G} == set(self.differing[0])

    @property
    def shared_factors(self) -> tuple[str, ...]:
        return tuple(a for a, b in zip(self.left, self.right) if a == b)

    def describe(self) -> str:
        return " · ".join(self.shared_factors)


def _split(side: str) -> tuple[str, ...]:
    return tuple(p.strip() for p in side.strip("()").split("&"))


def parse_contrasts(text: str) -> list[Contrast]:
    """Parse the study's contrasts file into structured comparisons."""
    header = next(csv.reader(io.StringIO(text)))
    out = []
    for h in header[1:]:
        m = re.match(r"^\((.*?)\)v\((.*?)\)$", h)
        if not m:
            continue
        out.append(Contrast(label=h, left=_split(m.group(1)), right=_split(m.group(2))))
    if not out:
        raise OsdrError("parsed 0 contrasts from the contrasts file")
    return out


def field_isolating_contrasts(contrasts: Sequence[Contrast]) -> list[Contrast]:
    """The comparisons that isolate the magnetic field.

    Deduplicated by their matched factors: the file lists each comparison in both
    directions (A v B and B v A), and keeping both would double-count the evidence.
    The magnet-first orientation is kept so a positive log2 fold change means
    "higher in the magnet".
    """
    seen: dict[tuple[str, ...], Contrast] = {}
    for c in contrasts:
        if not c.isolates_field:
            continue
        key = c.shared_factors
        if key in seen and seen[key].left[1] == MAGNET_1G:
            continue                      # already have the magnet-first orientation
        if c.left[1] == MAGNET_1G or key not in seen:
            seen[key] = c
    return [seen[k] for k in sorted(seen)]


def find_de_file(accession: str = ACCESSION) -> OsdrFile:
    study = fetch_study(accession)
    hits = [f for f in study.files if "differential_expression" in f.file_name]
    if not hits:
        raise OsdrError(f"OSD-{accession}: no differential expression file")
    return max(hits, key=lambda f: f.size_bytes)


def find_contrasts_file(accession: str = ACCESSION) -> OsdrFile:
    study = fetch_study(accession)
    hits = [f for f in study.files if "contrasts" in f.file_name.lower()]
    if not hits:
        raise OsdrError(f"OSD-{accession}: no contrasts file")
    return hits[0]


def _stream_lines(url: str, chunk_bytes: int = 4 << 20) -> Iterator[str]:
    """Yield lines from a remote file without holding it in memory.

    The DE table is ~623 MB; reading it with `.read()` would be roughly that much RAM
    for a result of a few hundred KB.
    """
    req = urllib.request.Request(url, headers={"User-Agent": "quantum-biology-atlas/0.1"})
    with urllib.request.urlopen(req, timeout=300) as r:
        tail = ""
        while True:
            chunk = r.read(chunk_bytes)
            if not chunk:
                break
            text = tail + chunk.decode("utf-8", errors="replace")
            *lines, tail = text.split("\n")
            yield from lines
        if tail:
            yield tail


def slice_contrasts(
    de_file: OsdrFile,
    contrasts: Sequence[Contrast],
    out_path: pathlib.Path,
    *,
    id_column: str | None = None,
    progress_every: int = 5000,
) -> dict:
    """Stream the DE table, writing only the gene id and the named contrasts' columns.

    Returns a record of what was extracted. Raises if the output would be empty or if a
    requested contrast has no column — a silently missing contrast would produce a map
    that looks fine and shows the wrong comparison.
    """
    url = de_file.url
    lines = _stream_lines(url)
    try:
        header_line = next(lines)
    except StopIteration:
        raise OsdrError(f"{de_file.file_name}: file was empty") from None
    header = next(csv.reader(io.StringIO(header_line)))

    wanted: dict[str, dict[str, int]] = {}
    for c in contrasts:
        cols = {}
        for prefix, role in (("Log2fc_", "log2fc"), ("Adj.p.value_", "padj"), ("P.value_", "pvalue")):
            name = prefix + c.label
            if name in header:
                cols[role] = header.index(name)
        if "log2fc" not in cols:
            raise OsdrError(
                f"{de_file.file_name}: no Log2fc column for contrast {c.label!r}. "
                f"Refusing to continue — a missing contrast would silently change which "
                f"comparison the figure shows."
            )
        wanted[c.label] = cols

    out_path.parent.mkdir(parents=True, exist_ok=True)
    rows_written = 0
    sample: list[dict] = []

    # The gene column is chosen by CONTENT, not name: this file has a GENENAME column
    # holding free-text descriptions, exactly as OSD-38 does.
    reader = csv.reader(lines)
    buffered: list[list[str]] = []
    for row in reader:
        buffered.append(row)
        if len(buffered) >= 200:
            break
    if not buffered:
        raise OsdrError(f"{de_file.file_name}: header present but no data rows")
    sample_dicts = [dict(zip(header, r)) for r in buffered if len(r) == len(header)]
    gene_col = id_column or _choose_gene_column(header, sample_dicts)
    gene_idx = header.index(gene_col)

    fields = ["gene_id"] + [
        f"{role}__{c.label}" for c in contrasts for role in ("log2fc", "padj")
        if role in wanted[c.label]
    ]
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(fields)
        import itertools

        for row in itertools.chain(buffered, reader):
            if len(row) != len(header):
                continue
            gid = row[gene_idx].strip()
            if not gid:
                continue
            out = [gid]
            for c in contrasts:
                for role in ("log2fc", "padj"):
                    idx = wanted[c.label].get(role)
                    out.append(row[idx].strip() if idx is not None else "")
            w.writerow(out)
            rows_written += 1
            if len(sample) < 3:
                sample.append(dict(zip(fields, out)))

    if rows_written == 0:
        raise OsdrError(
            f"{de_file.file_name}: sliced 0 rows. Refusing to write an empty table."
        )

    return {
        "source_file": de_file.file_name,
        "source_bytes": de_file.size_bytes,
        "source_columns": len(header),
        "gene_column": gene_col,
        "contrasts": [c.label for c in contrasts],
        "rows": rows_written,
        "output": str(out_path),
        "output_bytes": out_path.stat().st_size,
        "sample": sample[:2],
    }
