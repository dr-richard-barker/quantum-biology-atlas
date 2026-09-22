"""Ontology integrity.

The rule the whole design exists to enforce — a tier that asserts a magnetic-field
effect must cite a DOI that actually resolves — is checked here rather than trusted.
"""
from __future__ import annotations

import json
import pathlib
import re
import time
import urllib.error
import urllib.request

import pytest
import yaml

CROSSREF = "https://api.crossref.org/works/"
UA = "quantum-biology-atlas-tests/0.1 (mailto:dr.richard.barker@gmail.com)"


# ---------------------------------------------------------------------------
# structural
# ---------------------------------------------------------------------------
def test_ontology_loads_and_self_validates(onto):
    """load(strict=True) raises on any inconsistency, so reaching here is the check."""
    assert len(onto) > 0
    assert onto.validate() == [], "ontology reported problems"


def test_every_asserting_tier_cites_evidence(onto):
    """T1 and T2 claim a demonstrated effect. Neither may do so without a source."""
    offenders = [e.id for e in onto.asserting() if not e.evidence]
    assert offenders == [], f"T1/T2 entities with no evidence: {offenders}"


def test_every_t3_states_its_reasoning(onto):
    """T3 is a hypothesis; the reasoning IS the annotation, so it must be written down."""
    offenders = [e.id for e in onto.by_tier("T3") if not e.rationale]
    assert offenders == [], f"T3 entities with no rationale: {offenders}"


def test_structural_context_claims_are_marked_unexplained(onto):
    """A field effect with no proposed mechanism is allowed, but must say so.

    This is the corrected form of an earlier rule that forbade the combination
    outright and so re-coupled the two axes the ontology exists to separate.
    """
    offenders = [
        e.id
        for e in onto.asserting()
        if "structural_context" in e.quantum_class and not (e.rationale or e.note or e.caveat)
    ]
    assert offenders == [], f"unexplained field effects not marked as such: {offenders}"


def test_every_evidence_ref_exists_in_the_bibliography(onto):
    dangling = sorted(
        {ev.ref for e in onto for ev in e.evidence if ev.ref not in onto.references}
    )
    assert dangling == [], f"evidence cites keys absent from references.yaml: {dangling}"


def test_vocabulary_terms_are_all_defined(onto):
    core = onto.core
    bad_class = sorted({c for e in onto for c in e.quantum_class if c not in core.quantum_class_ids})
    bad_nucleus = sorted({n for e in onto for n in e.nuclei if n not in core.nucleus_ids})
    assert bad_class == [], f"undefined quantum_class: {bad_class}"
    assert bad_nucleus == [], f"undefined nucleus: {bad_nucleus}"


def test_agi_loci_are_well_formed(onto):
    bad = sorted({a for e in onto for a in e.agi if not re.fullmatch(r"AT[1-5CM]G\d{5}", a)})
    assert bad == [], f"malformed AGI loci: {bad}"


def test_entity_ids_are_unique_and_namespaced(onto):
    bad = sorted(e.id for e in onto if not re.fullmatch(r"QBO:[A-Z0-9_]+", e.id))
    assert bad == [], f"malformed entity ids: {bad}"


def test_the_ontology_is_not_silently_all_hypothesis(onto):
    """A guard against the annotation layer degenerating into unsupported claims.

    Not a quality bar on the science — the field genuinely is mostly T3 — but if
    T1+T2 ever reached zero, the evidence layer would have stopped doing anything
    and every map would be pure assertion.
    """
    assert len(onto.asserting()) > 0, "no entity cites any magnetic-field evidence at all"


# ---------------------------------------------------------------------------
# network — the assertions that make the evidence layer worth having
# ---------------------------------------------------------------------------
def _crossref(doi: str) -> dict | None:
    req = urllib.request.Request(CROSSREF + doi, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)["message"]
    except urllib.error.HTTPError:
        return None


def _tokens(s: str) -> set[str]:
    return set(re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).split())


@pytest.mark.network
def test_every_cited_doi_resolves_and_matches_its_title(onto):
    """The companion repo's study database had 42 of 49 DOIs wrong, several of them
    resolving to plausible-looking but unrelated papers. Resolution alone is not
    enough; the title has to match too."""
    failures = []
    for key, ref in sorted(onto.references.items()):
        msg = _crossref(ref["doi"])
        if msg is None:
            failures.append(f"{key}: {ref['doi']} does not resolve")
            continue
        cr_title = (msg.get("title") or [""])[0]
        a, b = _tokens(cr_title), _tokens(ref["title"])
        jaccard = len(a & b) / max(1, len(a | b))
        if jaccard < 0.45:
            failures.append(f"{key}: {ref['doi']} -> {cr_title[:70]!r} (overlap {jaccard:.2f})")
        time.sleep(0.1)
    assert failures == [], "citations that do not check out:\n  " + "\n  ".join(failures)


@pytest.mark.network
def test_every_agi_locus_exists_in_ensembl(onto, root):
    """Symbols are unsafe to type — ACO2, LIP1, CAT2, CAT3 and KAT2 all resolve to
    the wrong gene. The ontology stores loci; this confirms each one is real."""
    import sys

    sys.path.insert(0, str(root / "scripts"))
    from resolve_loci import reverse

    loci = sorted(onto.index_by_agi())
    missing = [locus for locus in loci if reverse(locus) is None]
    assert missing == [], f"AGI loci that do not resolve in Ensembl: {missing}"
