"""
NASA OSDR (Open Science Data Repository / GeneLab) ingestion.

The browser-side equivalent already exists in `SBGN-Pathway-viewer/services/osdr.ts`
and is live; this is the Python half, for building results and figures offline rather
than in a tab. The API shape is the same one that app uses:

    https://osdr.nasa.gov/osdr/data/osd/files/{n}/   -> the study's file listing

Three things this module refuses to do, each because the failure is silent:

  * **No synthetic fallback.** If a fetch fails, it raises. A module that quietly
    substitutes random numbers when the network is down will eventually publish those
    numbers as a result.
  * **No silent empty.** A differential-expression table that parses to zero usable
    rows raises rather than returning an empty frame.
  * **No guessing the organism or the contrast.** Both are read off the study record
    and reported; assuming either is how a wrong assumption propagates through a
    whole analysis.

Downloads are cached under `.osdr_cache/` so a re-run is cheap and an interrupted
job resumes — processed DE tables can be hundreds of megabytes.
"""
from __future__ import annotations

import csv
import dataclasses
import gzip
import io
import json
import pathlib
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Iterator, Sequence

OSDR = "https://osdr.nasa.gov"
FILES_API = OSDR + "/osdr/data/osd/files/{n}/"
META_API = OSDR + "/osdr/data/osd/meta/{n}"   # no trailing slash: /meta/38/ returns 404
UA = "quantum-biology-atlas/0.1 (mailto:dr.richard.barker@gmail.com)"
ROOT = pathlib.Path(__file__).resolve().parents[2]
CACHE_DIR = ROOT / ".osdr_cache"
RETRIABLE = (socket.timeout, TimeoutError, urllib.error.URLError, ConnectionError)

#: Refuse to pull a DE table larger than this into memory. OSD-120's is ~252 MB
#: across 132 contrasts; that belongs in a pipeline, not in a map overlay.
MAX_DE_BYTES = 120 * 1024 * 1024


class OsdrError(Exception):
    """Raised when OSDR data cannot be trusted or retrieved. Never a warning."""


@dataclasses.dataclass
class OsdrFile:
    file_name: str
    category: str
    subcategory: str
    remote_url: str
    size_bytes: int = 0

    @property
    def url(self) -> str:
        return self.remote_url if self.remote_url.startswith("http") else OSDR + self.remote_url


@dataclasses.dataclass
class OsdrStudy:
    number: str
    osd_id: str
    files: list[OsdrFile]
    organism: str | None = None
    title: str | None = None
    factors: tuple[str, ...] = ()

    def matching(self, *patterns: str) -> list[OsdrFile]:
        rx = [re.compile(p, re.I) for p in patterns]
        return [f for f in self.files if any(r.search(f.file_name) for r in rx)]

    @property
    def differential_expression_files(self) -> list[OsdrFile]:
        return self.matching(r"differential_expression", r"_DGE_", r"contrasts")

    def describe(self) -> str:
        return (
            f"{self.osd_id}: {self.title or '(no title in record)'}\n"
            f"  organism: {self.organism or 'NOT STATED IN RECORD — do not assume one'}\n"
            f"  factors : {', '.join(self.factors) or 'none stated'}\n"
            f"  files   : {len(self.files)} "
            f"({len(self.differential_expression_files)} DE/contrast)"
        )


def normalize_osd(value: str | int) -> str:
    """Accept 'OSD-120', 'osd 120', 'GLDS-120', 120 -> '120'."""
    m = re.search(r"(\d+)", str(value))
    if not m:
        raise OsdrError(f"cannot read an OSD accession from {value!r} — try 'OSD-120'")
    return m.group(1)


def _get(url: str, timeout: int = 90, binary: bool = False):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    last: Exception | None = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
            return raw if binary else raw.decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(3 + attempt * 3)
                last = e
                continue
            raise OsdrError(f"OSDR returned HTTP {e.code} for {url}") from e
        except RETRIABLE as e:
            last = e
            time.sleep(2 + attempt * 2)
    raise OsdrError(f"OSDR did not answer for {url} after 4 attempts ({last})")


def _cached(name: str, fetch, binary: bool = False):
    CACHE_DIR.mkdir(exist_ok=True)
    path = CACHE_DIR / name
    if path.exists():
        return path.read_bytes() if binary else path.read_text(encoding="utf-8")
    data = fetch()
    path.write_bytes(data) if binary else path.write_text(data, encoding="utf-8")
    return data


def fetch_study(accession: str | int) -> OsdrStudy:
    """Fetch a study's file listing. Organism is read off the record, never assumed."""
    n = normalize_osd(accession)
    raw = _cached(f"osd{n}_files.json", lambda: _get(FILES_API.format(n=n)))
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise OsdrError(f"OSD-{n}: file listing was not JSON ({e})") from e

    studies = data.get("studies") or {}
    if not studies:
        raise OsdrError(f"OSD-{n}: the file listing contains no studies")
    key = next(iter(studies))
    entries = studies[key].get("study_files") or []
    files = [
        OsdrFile(
            file_name=f.get("file_name", ""),
            category=f.get("category") or "",
            subcategory=f.get("subcategory") or "",
            remote_url=f.get("remote_url") or "",
            size_bytes=int(f.get("file_size") or 0),
        )
        for f in entries
    ]
    if not files:
        raise OsdrError(f"OSD-{n}: the study record lists no files")

    organism = None
    for field in ("organism", "Study Organism", "organisms"):
        v = studies[key].get(field)
        if v:
            organism = v if isinstance(v, str) else ", ".join(map(str, v))
            break

    title, factors = _fetch_study_description(n)
    if organism is None and title:
        organism = _organism_from_title(title)

    return OsdrStudy(
        number=n,
        osd_id=key if key.startswith("OSD") else f"OSD-{n}",
        files=files,
        organism=organism,
        title=title,
        factors=tuple(factors),
    )


def _fetch_study_description(n: str) -> tuple[str | None, list[str]]:
    """Read the study title and experimental factors off the ISA metadata record.

    The file listing does not carry the organism, and assuming it from an accession
    number is exactly the mistake that propagates through a whole analysis. The
    metadata endpoint states it, so read it there — and if it cannot be read, say so
    rather than filling in a guess.
    """
    try:
        raw = _cached(f"osd{n}_meta.json", lambda: _get(META_API.format(n=n)))
        doc = json.loads(raw)
    except (OsdrError, json.JSONDecodeError):
        return None, []

    container = doc.get("study") or {}
    if not container:
        return None, []
    inv = container[next(iter(container))]
    studies = inv.get("studies") or []
    if not studies:
        return None, []
    st = studies[0]
    title = st.get("title") or None
    factors = [f.get("factorName") for f in (st.get("factors") or []) if f.get("factorName")]
    return title, factors


#: Binomials we can recognise in a study title. Deliberately short: an unrecognised
#: organism is reported as unknown, not guessed at.
_KNOWN_ORGANISMS = (
    "Arabidopsis thaliana", "Arabidopsis", "Brassica", "Homo sapiens", "human",
    "Mus musculus", "mouse", "Drosophila", "Caenorhabditis elegans",
    "Saccharomyces cerevisiae", "yeast", "Oryza sativa", "rice", "Solanum lycopersicum",
)


def _organism_from_title(title: str) -> str | None:
    for name in _KNOWN_ORGANISMS:
        if re.search(rf"\b{re.escape(name)}\b", title, re.I):
            return name
    return None


def fetch_table(f: OsdrFile, max_bytes: int = MAX_DE_BYTES) -> str:
    """Download one file as text, honouring the size guard and gzip."""
    if f.size_bytes and f.size_bytes > max_bytes:
        raise OsdrError(
            f"{f.file_name} is {f.size_bytes/1e6:.0f} MB, over the {max_bytes/1e6:.0f} MB "
            f"guard. Slice it in a pipeline rather than loading it to overlay a map."
        )
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", f.file_name)
    raw = _cached(safe, lambda: _get(f.url, binary=True), binary=True)
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return raw.decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# parsing differential expression into something a map can consume
# ---------------------------------------------------------------------------
@dataclasses.dataclass
class ExpressionTable:
    """Per-gene statistics for one contrast. The unit a map overlay consumes."""

    source: str
    contrast: str
    gene_column: str
    values: dict[str, float]                    # gene id -> log2 fold change
    padj: dict[str, float] = dataclasses.field(default_factory=dict)
    organism: str | None = None

    def __len__(self) -> int:
        return len(self.values)

    def significant(self, alpha: float = 0.05) -> dict[str, float]:
        if not self.padj:
            raise OsdrError(
                f"{self.source}: no adjusted p-value column was found, so significance "
                f"cannot be filtered. Use the full `values` and say so, rather than "
                f"pretending a threshold was applied."
            )
        return {g: v for g, v in self.values.items() if self.padj.get(g, 1.0) <= alpha}


#: Candidate gene-identifier columns, best first. Order matters: a bare "gene" hint
#: matches GENENAME, which in OSDR's Arabidopsis tables holds a free-text DESCRIPTION
#: ("ENCODES A DICER HOMOLOG. DICER IS A RNA HELICASE…"), not an identifier. Picking it
#: would silently join descriptions against loci and map nothing.
_GENE_COL_HINTS = (
    "tair", "agi", "locus_tag", "gene_id", "geneid", "ensembl",
    "locus", "entrezid", "refseq", "symbol", "gene",
)

#: What an identifier looks like: no whitespace, not prose, reasonable length.
_ID_RX = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:\-]{1,30}$")

_LFC_RX = re.compile(r"log2\s*fold\s*change|log2foldchange|log2fc", re.I)
_PADJ_RX = re.compile(r"^(adj\.?p|padj|adjusted.*p|fdr|q[_.]?value)", re.I)


def _looks_like_identifiers(values: Sequence[str]) -> float:
    """Fraction of sampled values that look like identifiers rather than prose."""
    usable = [v.strip() for v in values if v and v.strip() and v.strip().upper() != "NA"]
    if not usable:
        return 0.0
    return sum(1 for v in usable if _ID_RX.match(v)) / len(usable)


def _choose_gene_column(cols: Sequence[str], sample: Sequence[dict]) -> str:
    """Pick the gene-identifier column by NAME HINT *and* by what it contains.

    Name matching alone is not safe (see _GENE_COL_HINTS). A column only wins if the
    values under it actually look like identifiers, so a well-named column full of
    prose loses to a correctly-populated one.
    """
    scored: list[tuple[float, int, str]] = []
    for col in cols:
        low = col.lower().strip()
        rank = next((i for i, h in enumerate(_GENE_COL_HINTS) if h in low), len(_GENE_COL_HINTS))
        idness = _looks_like_identifiers([r.get(col, "") for r in sample])
        if idness < 0.7:                       # mostly prose or mostly numbers-as-text
            continue
        scored.append((idness, -rank, col))
    if scored:
        scored.sort(reverse=True, key=lambda t: (t[1], t[0]))   # hint rank first
        return scored[0][2]

    raise OsdrError(
        "no column contains gene identifiers. Checked "
        f"{len(cols)} columns against {len(sample)} sampled rows; none was ≥70% "
        f"identifier-shaped. Columns: {list(cols)[:14]}"
    )


def parse_expression(
    text: str,
    *,
    source: str,
    contrast: str | None = None,
    organism: str | None = None,
) -> ExpressionTable:
    """Parse a DE table into one contrast's log2 fold changes.

    OSDR's processed DE tables are wide: one row per gene, and a log2-fold-change
    column per contrast, named e.g. `Log2fc_(Space Flight)v(Ground Control)`. When
    `contrast` is None and there is exactly one such column it is used; when there are
    several, this RAISES and lists them rather than silently picking the first — which
    would attach the wrong comparison to a map and be almost impossible to notice.
    """
    sniff = text[:8192]
    delimiter = "\t" if sniff.count("\t") > sniff.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    cols = reader.fieldnames or []
    if not cols:
        raise OsdrError(f"{source}: no header row found")

    # Sample real rows so the gene column is chosen on its CONTENTS, not just its name.
    sample = []
    for row in reader:
        sample.append(row)
        if len(sample) >= 200:
            break
    if not sample:
        raise OsdrError(f"{source}: header present but no data rows")
    try:
        gene_col = _choose_gene_column(cols, sample)
    except OsdrError as e:
        raise OsdrError(f"{source}: {e}") from None
    lfc_cols = [c for c in cols if _LFC_RX.search(c)]
    if not lfc_cols:
        raise OsdrError(
            f"{source}: no log2-fold-change column found. Columns: {cols[:14]}"
        )

    if contrast:
        chosen = [c for c in lfc_cols if contrast.lower() in c.lower()]
        if not chosen:
            raise OsdrError(
                f"{source}: no column matches contrast {contrast!r}. Available:\n  "
                + "\n  ".join(lfc_cols[:25])
            )
        lfc_col = chosen[0]
    elif len(lfc_cols) == 1:
        lfc_col = lfc_cols[0]
    else:
        raise OsdrError(
            f"{source}: {len(lfc_cols)} contrasts present and none was chosen. "
            f"Pass `contrast=` explicitly — picking one silently would attach the "
            f"wrong comparison to the map. Available:\n  "
            + "\n  ".join(lfc_cols[:25])
        )

    padj_col = next((c for c in cols if _PADJ_RX.search(c.strip())
                     and _contrast_key(c) == _contrast_key(lfc_col)), None)
    if padj_col is None:
        padj_col = next((c for c in cols if _PADJ_RX.search(c.strip())), None)

    values: dict[str, float] = {}
    padj: dict[str, float] = {}
    skipped = 0
    import itertools

    for row in itertools.chain(sample, reader):
        gene = (row.get(gene_col) or "").strip()
        if not gene:
            skipped += 1
            continue
        try:
            values[gene.upper()] = float(row[lfc_col])
        except (TypeError, ValueError, KeyError):
            skipped += 1
            continue
        if padj_col:
            try:
                padj[gene.upper()] = float(row[padj_col])
            except (TypeError, ValueError, KeyError):
                pass

    if not values:
        raise OsdrError(
            f"{source}: parsed 0 usable rows from {len(text)} characters "
            f"(gene column {gene_col!r}, value column {lfc_col!r}, {skipped} rows skipped). "
            f"Refusing to return an empty table."
        )
    return ExpressionTable(
        source=source,
        contrast=lfc_col,
        gene_column=gene_col,
        values=values,
        padj=padj,
        organism=organism,
    )


def _contrast_key(column: str) -> str:
    """Strip the statistic prefix so Log2fc_(A)v(B) and Adj.p.value_(A)v(B) match."""
    return re.sub(r"^[^_(]*[_.]?", "", column.strip(), count=1).lower()


def load_contrast(
    accession: str | int,
    *,
    contrast: str | None = None,
    file_pattern: str = r"differential_expression",
) -> ExpressionTable:
    """Fetch a study and parse one contrast out of its DE table. End to end."""
    study = fetch_study(accession)
    candidates = study.matching(file_pattern)
    if not candidates:
        raise OsdrError(
            f"{study.osd_id}: no file matching {file_pattern!r}. "
            f"Files present include: "
            + ", ".join(f.file_name for f in study.files[:8])
        )
    f = min(candidates, key=lambda x: x.size_bytes or 1 << 62)
    return parse_expression(
        fetch_table(f),
        source=f"{study.osd_id}/{f.file_name}",
        contrast=contrast,
        organism=study.organism,
    )
