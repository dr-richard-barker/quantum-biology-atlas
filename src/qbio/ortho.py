"""
Cross-species projection of QBO annotations.

QBO is anchored on *Arabidopsis thaliana*, because that is where the near-null-field
literature is. Projecting it onto mouse, human, fly, worm or yeast means asking, for
each Arabidopsis locus on a map, what the corresponding gene is in the target species.

Two independent backbones, because neither is trustworthy alone:

  **Ensembl Compara `pan_homology`** — live, current, covers any species Ensembl
  carries. Verified to cross kingdoms: human *NDUFS1* returns an *A. thaliana*
  ortholog, and At*CRY1* (AT4G08920) returns *D. melanogaster*. Note that the plant
  division (`compara=plants`) does NOT cross kingdoms — querying At*CRY1* there
  returns 118 species, all plants plus yeast — so `pan_homology` is the division that
  matters here and the default below.

  **OrthoDB v12** — the frozen, human-anchored matrix already computed for
  `OSDR_X-species_V2` across exactly the six species of interest. Offline and
  reproducible, but fixed at that version and that species set.

Where they disagree, the disagreement is REPORTED, not resolved by preferring one.
An ortholog call is a hypothesis about shared function; two methods disagreeing is
information the reader needs, and silently picking a winner would hide it.

**What this module will not do:** drop genes quietly. Every projection returns a
`Coverage` record naming what mapped, what did not, and what was ambiguous. A
projection with no hits raises rather than returning an empty frame that would render
as a blank map — an empty result is the single most dangerous silent failure here.
"""
from __future__ import annotations

import dataclasses
import json
import pathlib
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Iterable, Sequence

ENSEMBL = "https://rest.ensembl.org"
UA = "quantum-biology-atlas/0.1 (mailto:dr.richard.barker@gmail.com)"
ROOT = pathlib.Path(__file__).resolve().parents[2]
CACHE_DIR = ROOT / ".ortho_cache"
RETRIABLE = (socket.timeout, TimeoutError, urllib.error.URLError, ConnectionError)

#: Ensembl Compara divisions, from GET /info/comparas (checked, not assumed):
#: bacteria, plants, pan_homology, metazoa, protists, vertebrates, fungi.
#: Only `pan_homology` spans kingdoms.
DEFAULT_DIVISION = "pan_homology"

#: The species the review and OSDR_X-species_V2 both care about, as Ensembl
#: production names.
MODEL_SPECIES = {
    "arabidopsis": "arabidopsis_thaliana",
    "human": "homo_sapiens",
    "mouse": "mus_musculus",
    "fly": "drosophila_melanogaster",
    "worm": "caenorhabditis_elegans",
    "yeast": "saccharomyces_cerevisiae",
}


class OrthologyError(Exception):
    """Raised when a projection cannot be trusted. Never downgraded to a warning."""


@dataclasses.dataclass(frozen=True)
class Ortholog:
    source_id: str
    source_species: str
    target_id: str
    target_species: str
    target_symbol: str = ""
    homology_type: str = ""      # ortholog_one2one, ortholog_one2many, …
    method: str = ""             # "ensembl_pan_homology" | "orthodb_v12"

    @property
    def is_one_to_one(self) -> bool:
        return self.homology_type == "ortholog_one2one"


@dataclasses.dataclass
class Coverage:
    """What a projection did and did not manage. Always reported, never suppressed."""

    source_species: str
    target_species: str
    requested: int = 0
    mapped: int = 0
    unmapped: tuple[str, ...] = ()
    one_to_one: int = 0
    one_to_many: int = 0
    methods_used: tuple[str, ...] = ()
    agreed: tuple[str, ...] = ()
    disagreed: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = ()
    only_ensembl: tuple[str, ...] = ()
    only_orthodb: tuple[str, ...] = ()

    @property
    def fraction_mapped(self) -> float:
        return self.mapped / self.requested if self.requested else 0.0

    def summary(self) -> str:
        lines = [
            f"{self.source_species} → {self.target_species}: "
            f"{self.mapped}/{self.requested} loci mapped ({self.fraction_mapped:.0%})",
            f"  one-to-one {self.one_to_one}, one-to-many {self.one_to_many}",
            f"  methods: {', '.join(self.methods_used) or 'none'}",
        ]
        if len(self.methods_used) > 1:
            lines.append(
                f"  agreement: {len(self.agreed)} agreed, {len(self.disagreed)} disagreed, "
                f"{len(self.only_ensembl)} Ensembl-only, {len(self.only_orthodb)} OrthoDB-only"
            )
        if self.unmapped:
            shown = ", ".join(self.unmapped[:8])
            more = f" (+{len(self.unmapped) - 8} more)" if len(self.unmapped) > 8 else ""
            lines.append(f"  UNMAPPED: {shown}{more}")
        for locus, ens, odb in self.disagreed[:5]:
            lines.append(f"  DISAGREE {locus}: ensembl={list(ens)} orthodb={list(odb)}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d["fraction_mapped"] = round(self.fraction_mapped, 4)
        return d


# ---------------------------------------------------------------------------
# Ensembl Compara
# ---------------------------------------------------------------------------
def _cache_path(gene_id: str, division: str) -> pathlib.Path:
    CACHE_DIR.mkdir(exist_ok=True)
    return CACHE_DIR / f"{division}__{gene_id.upper()}.json"


def _fetch_homology(
    gene_id: str,
    source_species: str,
    division: str,
    timeout: int = 45,
) -> list[dict]:
    """Fetch orthologues for one gene. Cached on disk; retries transient failures.

    Ensembl times out often enough that an uncached run of a whole map is unreliable;
    the cache makes a re-run cheap and lets an interrupted job resume.
    """
    cache = _cache_path(gene_id, division)
    if cache.exists():
        return json.loads(cache.read_text()).get("homologies", [])

    path = (
        f"/homology/id/{urllib.parse.quote(source_species)}/{urllib.parse.quote(gene_id)}"
        f"?compara={division};type=orthologues;format=condensed"
    )
    req = urllib.request.Request(
        ENSEMBL + path, headers={"Accept": "application/json", "User-Agent": UA}
    )
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                payload = json.load(r)
            data = payload.get("data") or []
            homologies = data[0].get("homologies", []) if data else []
            cache.write_text(json.dumps({"homologies": homologies}))
            return homologies
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(2 + attempt * 2)
                continue
            if e.code in (400, 404):
                # Definitively absent — cache it so we don't ask again.
                cache.write_text(json.dumps({"homologies": []}))
                return []
            time.sleep(1 + attempt)
        except RETRIABLE:
            time.sleep(1 + attempt * 2)
    raise OrthologyError(
        f"Ensembl did not answer for {gene_id} after 4 attempts. "
        f"Nothing was cached, so re-running will retry rather than treat it as absent."
    )


def ensembl_orthologs(
    loci: Sequence[str],
    target_species: str,
    source_species: str = "arabidopsis_thaliana",
    division: str = DEFAULT_DIVISION,
    pause: float = 0.12,
) -> list[Ortholog]:
    """Map loci to `target_species` via Ensembl Compara."""
    out: list[Ortholog] = []
    for locus in loci:
        for h in _fetch_homology(locus, source_species, division):
            if h.get("species") != target_species:
                continue
            out.append(
                Ortholog(
                    source_id=locus,
                    source_species=source_species,
                    target_id=h.get("id", ""),
                    target_species=target_species,
                    homology_type=h.get("type", ""),
                    method=f"ensembl_{division}",
                )
            )
        time.sleep(pause)
    return out


def available_divisions(timeout: int = 30) -> list[str]:
    """Ask Ensembl which Compara divisions exist. Used by the test, not assumed.

    Retries, because this endpoint is intermittently unavailable: it has been observed
    returning 500 and 503 for several minutes across every user agent and both URL
    spellings, then 200 again, while `/homology/...` kept working. A single attempt
    therefore reports "Ensembl has no pan_homology division", which is a claim about
    the data rather than about the network, and is the wrong thing to conclude.
    """
    # Six attempts with a widening gap. Four was not enough: the endpoint fails in
    # BURSTS rather than independently — 200, 200, 200, 500 across four consecutive
    # requests was observed, and four consecutive 500s inside one burst is ordinary.
    last: Exception | None = None
    for attempt in range(6):
        req = urllib.request.Request(
            ENSEMBL + "/info/comparas",
            headers={"Accept": "application/json", "User-Agent": UA},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return sorted(c["name"] for c in json.load(r).get("comparas", []))
        except (urllib.error.HTTPError, *RETRIABLE) as e:
            last = e
            time.sleep(2 + attempt * 4)
    raise OrthologyError(
        f"Ensembl /info/comparas did not answer after 6 attempts ({last}). "
        f"This is an availability failure, not evidence about which divisions exist."
    )


# ---------------------------------------------------------------------------
# OrthoDB v12 matrix (from OSDR_X-species_V2)
# ---------------------------------------------------------------------------
#: Where the committed matrix lives if the sibling repo is cloned alongside this one.
ORTHODB_CANDIDATES = (
    ROOT / "data" / "external" / "arabidopsis_to_human_orthologs.csv",
    ROOT.parent / "OSDR_X-species_V2" / "results" / "orthology" / "unified_orthology_matrix.csv",
    ROOT / "data" / "unified_orthology_matrix.csv",
)

#: Measured coverage of the committed Arabidopsis→human table, counted from the file
#: itself: 2,868 of 12,828 Arabidopsis rows (22.4%) carry a human ortholog, and some
#: loci are absent from the table altogether rather than present-with-no-ortholog.
#: Several well-conserved mitochondrial genes fall in those gaps — SDH1-1 (AT5G66760)
#: and lipoyl synthase (AT2G20860) both come back empty here despite having obvious
#: human counterparts. That is the concrete reason this module runs two backbones and
#: reports their disagreement rather than trusting either one.
ORTHODB_ARABIDOPSIS_HUMAN_COVERAGE = 0.224


def find_orthodb_matrix() -> pathlib.Path | None:
    for p in ORTHODB_CANDIDATES:
        if p.exists():
            return p
    return None


def orthodb_orthologs(
    loci: Sequence[str],
    target_species: str,
    matrix_path: pathlib.Path | None = None,
    source_species: str = "arabidopsis_thaliana",
) -> list[Ortholog]:
    """Map loci via the committed OrthoDB v12 matrix.

    Returns [] when the matrix is not available locally — the caller decides whether
    a single-method projection is acceptable, and `Coverage.methods_used` records
    that only one method ran, so a reader is never misled into thinking both agreed.
    """
    path = matrix_path or find_orthodb_matrix()
    if path is None:
        return []

    import csv

    want = {l.upper() for l in loci}
    out: list[Ortholog] = []
    with path.open(newline="", encoding="utf-8", errors="replace") as fh:
        reader = csv.DictReader(fh)
        cols = reader.fieldnames or []
        # "gene_id" is the source column in the committed Arabidopsis→human table;
        # the wider matrix uses an explicit species name. Try the specific hints first
        # so a file carrying both does not pick the wrong one.
        src_col = _pick_column(cols, ("arabidopsis", "athaliana", "at_gene", "tair", "gene_id"))
        tgt_col = _pick_column(cols, _species_column_hints(target_species))
        if not src_col:
            # No source column is a defect in the file itself, and every projection
            # through it is affected. That is worth stopping for.
            raise OrthologyError(
                f"{path.name}: could not find a {source_species} source column. "
                f"Columns present: {cols[:12]}"
            )
        if not tgt_col:
            # A missing TARGET column is different in kind: the committed matrix is
            # human-anchored, so it simply cannot reach fly, worm or yeast. That is a
            # known property of the file, not an error — raising here made
            # `build_ortholog_map.py` abandon four of its five species. Return nothing
            # and let the caller record that only one method could run.
            return []
        for row in reader:
            src = (row.get(src_col) or "").strip().upper()
            tgt = (row.get(tgt_col) or "").strip()
            if not src or not tgt or src not in want:
                continue
            for one in _split_ids(tgt):
                # Ensembl gene ids carry a version suffix in this table
                # (ENSG00000167792.13); strip it so ids compare across methods.
                one = one.split(".")[0]
                if not one:
                    continue
                out.append(
                    Ortholog(
                        source_id=src,
                        source_species=source_species,
                        target_id=one,
                        target_species=target_species,
                        method="orthodb_v12",
                    )
                )
    # The table repeats ids within a cell (A|B|A), which would otherwise inflate
    # the one-to-many count.
    return list(dict.fromkeys(out))


def _species_column_hints(species: str) -> tuple[str, ...]:
    return {
        "homo_sapiens": ("human", "hsap", "homo"),
        "mus_musculus": ("mouse", "mmus", "mus"),
        "drosophila_melanogaster": ("fly", "dmel", "drosophila"),
        "caenorhabditis_elegans": ("worm", "cele", "caenorhabditis"),
        "saccharomyces_cerevisiae": ("yeast", "scer", "saccharomyces"),
        "arabidopsis_thaliana": ("arabidopsis", "athal", "tair"),
    }.get(species, (species.split("_")[0],))


def _pick_column(cols: Iterable[str], hints: Iterable[str]) -> str | None:
    lowered = {c.lower(): c for c in cols}
    for hint in hints:
        for low, original in lowered.items():
            if hint in low:
                return original
    return None


def _split_ids(cell: str) -> list[str]:
    for sep in (";", ",", "|", " "):
        if sep in cell:
            return [p.strip() for p in cell.split(sep) if p.strip()]
    return [cell.strip()]


# ---------------------------------------------------------------------------
# combined projection
# ---------------------------------------------------------------------------
def project(
    loci: Sequence[str],
    target_species: str,
    *,
    source_species: str = "arabidopsis_thaliana",
    use_ensembl: bool = True,
    use_orthodb: bool = True,
    division: str = DEFAULT_DIVISION,
    allow_empty: bool = False,
) -> tuple[dict[str, list[Ortholog]], Coverage]:
    """Project `loci` onto `target_species` with both backbones.

    Returns (source_locus -> orthologs, coverage). Raises if nothing mapped, unless
    `allow_empty` — an empty projection rendering as a blank map is the worst
    available failure mode, so it has to be opted into explicitly.
    """
    loci = [l.upper() for l in dict.fromkeys(loci)]        # de-duplicate, keep order
    if target_species == source_species:
        raise OrthologyError(
            f"source and target species are both {source_species} — nothing to project"
        )

    methods: list[str] = []
    ens: list[Ortholog] = []
    odb: list[Ortholog] = []

    if use_ensembl:
        ens = ensembl_orthologs(loci, target_species, source_species, division)
        methods.append(f"ensembl_{division}")
    if use_orthodb:
        odb = orthodb_orthologs(loci, target_species, source_species=source_species)
        # Only claim OrthoDB as a method when it actually returned calls. The matrix
        # existing on disk is not the same as it being able to reach this species:
        # it is human-anchored, so for fly, worm and yeast it contributes nothing.
        # Listing it anyway put "via ensembl_pan_homology, orthodb_v12" into coverage
        # reports and figure captions for projections only one method could make,
        # which reads as corroboration that never happened.
        if odb:
            methods.append("orthodb_v12")

    by_locus: dict[str, list[Ortholog]] = {l: [] for l in loci}
    for o in ens + odb:
        by_locus.setdefault(o.source_id.upper(), []).append(o)

    ens_ids = _grouped_ids(ens)
    odb_ids = _grouped_ids(odb)
    agreed, disagreed, only_e, only_o = [], [], [], []
    if ens and odb:
        for locus in loci:
            e, o = ens_ids.get(locus, set()), odb_ids.get(locus, set())
            if e and o:
                (agreed if e & o else disagreed).append(
                    locus if e & o else (locus, tuple(sorted(e)), tuple(sorted(o)))
                )
            elif e:
                only_e.append(locus)
            elif o:
                only_o.append(locus)

    mapped = [l for l, v in by_locus.items() if v]
    unmapped = [l for l in loci if not by_locus[l]]

    coverage = Coverage(
        source_species=source_species,
        target_species=target_species,
        requested=len(loci),
        mapped=len(mapped),
        unmapped=tuple(unmapped),
        one_to_one=sum(1 for l in mapped if any(o.is_one_to_one for o in by_locus[l])),
        one_to_many=sum(1 for l in mapped if len(by_locus[l]) > 1),
        methods_used=tuple(methods),
        agreed=tuple(a for a in agreed if isinstance(a, str)),
        disagreed=tuple(d for d in disagreed if isinstance(d, tuple)),
        only_ensembl=tuple(only_e),
        only_orthodb=tuple(only_o),
    )

    if not mapped and not allow_empty:
        raise OrthologyError(
            f"no locus of {len(loci)} mapped from {source_species} to {target_species} "
            f"using {methods or ['no method']}. Refusing to return an empty projection — "
            f"it would render as a blank map. Pass allow_empty=True if a genuine zero "
            f"is the expected answer.\n{coverage.summary()}"
        )
    return by_locus, coverage


def _grouped_ids(orthologs: Iterable[Ortholog]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for o in orthologs:
        out.setdefault(o.source_id.upper(), set()).add(o.target_id)
    return out
