"""The manuscript's evidence discipline, asserted rather than trusted.

A manuscript is the artefact that gets cited, so it is where a stale number or an
invented citation does the most damage. Three properties are enforced here:

  * **No literal numbers in the body.** Every quantity is a macro defined from a build
    artefact, so a re-analysis that moves a result moves the manuscript with it.
  * **No DOI is asserted for work in preparation.** This portfolio's own history
    contains a fabricated npj DOI that reached a .cls file and was stamped onto every
    page of every document built from it.
  * **Every other DOI resolves at CrossRef**, and the reference list matches the
    evidence base rather than having been typed alongside it.
"""
from __future__ import annotations

import json
import pathlib
import re
import urllib.error
import urllib.request

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
MS = ROOT / "manuscript"
BODY = MS / "manuscript.tex"
NUMBERS = MS / "numbers.tex"
BIB = MS / "references.bib"

UA = "quantum-biology-atlas-test/1.0 (mailto:dr.richard.barker@gmail.com)"

#: Numbers that may legitimately appear as literals in the body: font sizes, section
#: cross-references, tier names, the coverage threshold that is a design constant, and
#: the study's own contrast count quoted from its record.
ALLOWED_LITERALS = {
    "1", "2", "3", "4", "5", "11", "25", "80", "420", "2026",
    "0", "1.2", "2.3", "0.25", "0.5", "0.6", "0.8", "0.41", "0.48", "0.56",
}


def _body() -> str:
    if not BODY.exists():
        pytest.skip("manuscript not present")
    return BODY.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# numbers
# ---------------------------------------------------------------------------


def test_numbers_are_macros_not_literals():
    """The body must not carry a quantity that cannot be re-derived.

    Scanning prose only: the preamble legitimately contains font sizes and lengths.
    """
    body = _body()
    prose = body.split(r"\begin{document}", 1)[-1]
    # Strip the things that legitimately carry digits.
    prose = re.sub(r"\\includegraphics\[[^\]]*\]\{[^}]*\}", " ", prose)
    prose = re.sub(r"\\begin\{minipage\}\{[^}]*\}", " ", prose)
    prose = re.sub(r"\\(?:vspace|hspace)\{[^}]*\}", " ", prose)
    prose = re.sub(r"\\\\\[[^\]]*\]", " ", prose)
    prose = re.sub(r"\\label\{[^}]*\}|\\ref\{[^}]*\}|\\cite\w*\{[^}]*\}", " ", prose)
    prose = re.sub(r"\$[^$]*\$", " ", prose)          # maths, incl. \ge 0.5 style
    prose = re.sub(r"\\[A-Za-z]+", " ", prose)        # macros, including ours
    prose = re.sub(r"\[\dFe-\dS\]|\$\[\$\dFe-\dS\$\]\$", " ", prose)
    # Identifiers are not quantities and may be literal: accessions, map ids, tier
    # names, a licence version. What must be a macro is anything that could go stale
    # when an analysis is re-run.
    prose = re.sub(r"\b(?:OSD|GLDS|QBM|QBO|GSE|GPL)-?\d+\w*", " ", prose)
    prose = re.sub(r"CC-BY-[\d.]+", " ", prose)
    prose = re.sub(r"\bT[1-4]\b", " ", prose)

    literals = {n for n in re.findall(r"\b\d+(?:\.\d+)?\b", prose)}
    offenders = sorted(literals - ALLOWED_LITERALS)
    assert not offenders, (
        f"literal number(s) in the manuscript body: {offenders}. Every quantity should "
        f"be a macro from numbers.tex so it cannot go stale."
    )


def test_every_number_macro_is_defined_and_used():
    body = _body()
    if not NUMBERS.exists():
        pytest.skip("numbers.tex not generated")
    defined = set(re.findall(r"\\newcommand\{\\(\w+)\}", NUMBERS.read_text()))
    used = set(re.findall(r"\\(\w+)", body))
    undefined = {
        m for m in re.findall(r"\\([A-Z]\w+)", body)
    } - defined - {"BibTeX", "LaTeX", "TeX"}
    assert not undefined, f"macro(s) used but not defined: {sorted(undefined)}"
    assert not (defined - used), (
        f"macro(s) defined but never used: {sorted(defined - used)} — a number computed "
        f"and not shown is dead weight in the build"
    )


def test_the_headline_numbers_match_the_artefacts():
    """Spot-check the macros against the records, so a broken generator is caught."""
    if not NUMBERS.exists():
        pytest.skip("numbers.tex not generated")
    macros = dict(re.findall(r"\\newcommand\{\\(\w+)\}\{([^}]*)\}", NUMBERS.read_text()))
    totals = json.loads((ROOT / "catalog" / "manifest.json").read_text())["totals"]
    assert macros["NMaps"] == str(totals["maps"])
    assert macros["NNodes"] == str(totals["nodes"])
    assert macros["NLoci"] == str(totals["distinct_agi_loci"])

    osd8 = json.loads((ROOT / "results" / "osd8" / "record.json").read_text())
    spec = osd8["specificity"][osd8["primary_group"]]
    assert macros["OsdEightP"] == f"{spec['p_value']:.3f}"


# ---------------------------------------------------------------------------
# citations
# ---------------------------------------------------------------------------


def _bib() -> str:
    if not BIB.exists():
        pytest.skip("references.bib not generated")
    return BIB.read_text(encoding="utf-8")


def test_the_in_preparation_review_asserts_no_doi():
    """The failure this portfolio has already made: a fabricated DOI in a template."""
    bib = _bib()
    m = re.search(r"@unpublished\{.*?\n\}", bib, re.S)
    assert m, "the companion review should be @unpublished"
    entry = m.group()
    for field in ("doi", "volume", "pages", "number"):
        assert not re.search(rf"\b{field}\s*=", entry, re.I), (
            f"the in-preparation review asserts a {field}; a plausible placeholder is "
            f"how a fabricated citation enters a bibliography and stays there"
        )


def test_no_blocklisted_string_in_the_manuscript():
    blocklist = ROOT.parent / "abai" / "kb" / "blocklist.txt"
    if not blocklist.exists():
        pytest.skip("ABAI blocklist not available")
    pats = [
        l.strip() for l in blocklist.read_text().splitlines()
        if l.strip() and not l.startswith("#")
    ]
    for path in (BODY, BIB, NUMBERS):
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for p in pats:
            assert not re.search(p, text), f"{path.name} matches blocklist pattern {p}"


def test_every_cited_key_exists_in_the_bibliography():
    body, bib = _body(), _bib()
    cited = set()
    for m in re.finditer(r"\\cite\w*\{([^}]*)\}", body):
        cited |= {k.strip() for k in m.group(1).split(",")}
    keys = set(re.findall(r"@\w+\{([^,]+),", bib))
    assert cited <= keys, f"cited but absent from the bib: {sorted(cited - keys)}"


def test_the_bibliography_matches_the_evidence_base():
    """The reference list is generated from the verified base, not typed beside it."""
    bib = _bib()
    ev = yaml.safe_load((ROOT / "evidence" / "references.yaml").read_text())
    keys = set(re.findall(r"@\w+\{([^,]+),", bib))
    for r in ev["references"]:
        assert r["key"] in keys, f"{r['key']} is in the evidence base but not the bib"
        assert r["doi"] in bib, f"{r['key']}'s DOI is not in the bib"


@pytest.mark.network
@pytest.mark.parametrize("key,doi", [
    ("Ge2020", "10.1093/bioinformatics/btz931"),
    ("LeNovere2009", "10.1038/nbt.1558"),
    ("Cunningham2022", "10.1093/nar/gkab1049"),
    ("Kuznetsov2022", "10.1093/nar/gkac998"),
    ("Berrios2021", "10.1093/nar/gkaa887"),
])
def test_method_citations_resolve_at_crossref(key, doi):
    """The method citations are not in the evidence base, so nothing else checks them.

    Three DOIs guessed from memory while drafting this manuscript resolved to papers on
    HIV RNA methylation, metagenomics and sequencing error models. None would have
    looked wrong in a reference list.
    """
    bib = _bib()
    assert doi in bib, f"{key} ({doi}) is not in the bibliography"
    req = urllib.request.Request(
        "https://api.crossref.org/works/" + doi, headers={"User-Agent": UA}
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as fh:
            msg = json.load(fh)["message"]
    except urllib.error.HTTPError as e:
        pytest.fail(f"{key}: {doi} does not resolve (HTTP {e.code})")
    except Exception as e:
        pytest.skip(f"CrossRef unavailable, which is not evidence about the DOI: {e}")
    assert msg.get("title"), f"{doi} resolved with no title"


# ---------------------------------------------------------------------------
# the build
# ---------------------------------------------------------------------------


def test_the_build_left_no_undefined_macro_or_citation():
    log = MS / "manuscript.log"
    if not log.exists():
        pytest.skip("manuscript has not been built")
    text = log.read_text(encoding="utf-8", errors="replace")
    assert "Undefined control sequence" not in text
    assert not re.search(r"Citation.*undefined", text, re.I)
    assert not re.search(r"Reference.*undefined", text, re.I)


def test_the_figure_panels_all_trace_to_generated_files():
    """Every panel is a file the repository produced; none was drawn."""
    script = (ROOT / "scripts" / "build_manuscript_figure.py").read_text()
    sources = re.findall(r'\("([A-E])", "([^"]+)", "', script)
    assert sources, "no panel sources declared"
    for letter, rel in sources:
        assert (ROOT / rel).exists(), f"panel {letter} source missing: {rel}"
        assert rel.startswith("maps/"), (
            f"panel {letter} comes from {rel}, which is not a generated map"
        )


def test_the_committed_pdf_is_not_older_than_its_sources():
    """Guards the failure where a corrected .tex ships beside an uncorrected PDF.

    That has happened in this portfolio: a manuscript source was fixed and the compiled
    PDF beside it still carried the old claim, because nothing checked.
    """
    pdf = MS / "manuscript.pdf"
    if not pdf.exists():
        pytest.skip("manuscript.pdf not built")
    built = pdf.stat().st_mtime
    sources = [BODY, NUMBERS, BIB, MS / "Makefile"]
    sources += sorted((MS / "figures").glob("panel*"))
    stale = [
        p.name for p in sources
        if p.exists() and p.stat().st_mtime > built + 1
    ]
    assert not stale, (
        f"manuscript.pdf is older than {stale}. Run `make pdf` — a committed PDF that "
        f"does not match its source ships the old claim."
    )


def test_the_compiled_pdf_does_not_assert_a_doi_for_the_review():
    """The check that matters, made precise.

    A loose regex over the PDF first reported a DOI here; it was matching the DOI of the
    reference printed immediately BEFORE the review. The assertion is therefore scoped to
    the review's own entry text, not to a window around its author name.
    """
    pdf = MS / "manuscript.pdf"
    if not pdf.exists():
        pytest.skip("manuscript.pdf not built")
    try:
        from pypdf import PdfReader
    except ImportError:  # pragma: no cover
        try:
            from PyPDF2 import PdfReader
        except ImportError:
            pytest.skip("no PDF reader available")
    text = re.sub(r"\s+", " ", "".join(
        (p.extract_text() or "") for p in PdfReader(str(pdf)).pages
    ))
    i = text.find("Porterfield")
    assert i > 0, "the companion review does not appear in the reference list"
    # From its author name to the end of that entry.
    entry = text[i:i + 400].split("]")[0]
    assert "Manuscript in prepara" in entry
    assert "No DOI has been issued" in entry
    assert not re.search(r"doi:\s*10\.", entry), (
        f"the in-preparation review is printed with a DOI: {entry[:200]}"
    )
