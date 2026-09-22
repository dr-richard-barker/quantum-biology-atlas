#!/usr/bin/env python3
"""
Prepare a Zenodo deposit: `.zenodo.json`, `CITATION.cff`, a manifest and checksums.

Prepares only. It does not upload, because depositing mints a permanent public DOI and
that is a decision for a person, not a script.

Two rules this follows, both learned from the portfolio's own mistakes:

  * **No DOI is asserted for work in preparation.** The companion review has no DOI.
    The metadata says so in words and carries no placeholder, because a plausible-
    looking placeholder is how a fabricated citation gets into a bibliography and stays
    there.
  * **Large binaries go to Zenodo, the browsable material stays in git.** Everything
    here is small and text-shaped, so the deposit is the repository — but the manifest
    records sizes so that stops being true visibly rather than silently.

Everything in the generated metadata is derived from the repository: the file list from
git, the totals from the catalogue, the keywords from the ontology's own vocabulary.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

#: Verified against pub.orcid.org before use, not taken from a note — the portfolio
#: carries several wrong or placeholder ORCIDs.
AUTHOR = {
    "name": "Barker, Richard",
    "orcid": "0000-0001-5681-9857",
    "affiliation": "University of Wisconsin–Madison",
}
REPO_URL = "https://github.com/dr-richard-barker/quantum-biology-atlas"
PAGES_URL = "https://dr-richard-barker.github.io/quantum-biology-atlas/"


def tracked_files() -> list[pathlib.Path]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True)
    return [ROOT / f for f in out.stdout.split() if (ROOT / f).is_file()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=pathlib.Path, default=ROOT)
    args = ap.parse_args()

    from qbio import ontology

    onto = ontology.load()
    manifest = json.loads((ROOT / "catalog" / "manifest.json").read_text())
    t = manifest["totals"]

    description = f"""<p><strong>A cross-species ontology and SBGN pathway-map toolkit for
quantum-biological processes.</strong> Companion software to a review of plant responses
to near-null magnetic fields (Porterfield &amp; Barker, in preparation).</p>

<p>The atlas separates two questions that are routinely conflated: what quantum chemistry
a molecular entity carries, and how much is actually known about its magnetic-field
sensitivity. The first is structural and largely uncontroversial; the second is where the
claims live. An evidence tier that asserts a demonstrated or inferred field effect cannot
validate without a DOI resolved against CrossRef, and the tier is rendered as a border
style on every map, so a hypothesis looks provisional on the page.</p>

<p>Contents: {t['maps']} identifier-bound pathway maps ({t['nodes']} annotated nodes,
{t['edges']} edges, {t['distinct_agi_loci']} Arabidopsis loci) published as SBGN-ML
Process Description with quantum annotations in extension blocks; the QBO ontology
({t['entities']} entities); an evidence base of {t['references']} references, every one
CrossRef-resolved and title-matched; a Python package for cross-species orthology
projection and NASA OSDR data overlay; and a pre-registered statistical test whose null
result and power analysis are reported in full.</p>

<p>Node counts by evidence tier: {', '.join(f'{k} {v}' for k, v in sorted(t['nodes_by_tier'].items()))}.
The maps are mostly tier T3 — a plausible physical route with no field measurement behind
it — which is the finding rather than a defect: the near-null-field literature is
developmental and nutritional and has not yet measured a respiratory complex directly.</p>

<p><strong>The companion review is in preparation and has no DOI.</strong> Please cite this
software by its own DOI and the review by URL until one is issued.</p>"""

    keywords = [
        "quantum biology", "magnetobiology", "radical pair mechanism",
        "iron-sulfur clusters", "cryptochrome", "near-null magnetic field",
        "hypomagnetic field", "SBGN", "pathway visualization", "ontology",
        "Arabidopsis thaliana", "NASA OSDR", "space biology", "FAIR data",
        "electron transport chain", "orthology",
    ]

    zenodo = {
        "title": "Quantum Biology Atlas: a cross-species ontology and SBGN pathway maps "
                 "for quantum-biological processes",
        "upload_type": "software",
        "description": description,
        "creators": [AUTHOR],
        "keywords": keywords,
        "license": "cc-by-4.0",
        "access_right": "open",
        "related_identifiers": [
            {"identifier": REPO_URL, "relation": "isSupplementTo", "scheme": "url"},
            {"identifier": PAGES_URL, "relation": "isDocumentedBy", "scheme": "url"},
            {
                "identifier": "https://github.com/dr-richard-barker/SBGN-Pathway-viewer",
                "relation": "isCompiledBy",
                "scheme": "url",
            },
            {
                "identifier": "https://github.com/dr-richard-barker/OSDR_X-species_V2",
                "relation": "references",
                "scheme": "url",
            },
        ],
        "notes": (
            "The companion review is in preparation and no DOI has been issued for it; "
            "no placeholder is recorded here deliberately. Code is MIT; the ontology, "
            "maps and evidence base are CC-BY-4.0."
        ),
    }
    (args.out / ".zenodo.json").write_text(json.dumps(zenodo, indent=2) + "\n")

    cff = f"""cff-version: 1.2.0
message: "If you use this software, please cite it as below."
title: "Quantum Biology Atlas: a cross-species ontology and SBGN pathway maps for quantum-biological processes"
type: software
authors:
  - family-names: Barker
    given-names: Richard
    orcid: "https://orcid.org/{AUTHOR['orcid']}"
    affiliation: "{AUTHOR['affiliation']}"
repository-code: "{REPO_URL}"
url: "{PAGES_URL}"
abstract: >-
  A cross-species ontology and SBGN-ML pathway-map toolkit for quantum-biological
  processes. Separates what quantum chemistry an entity carries from how much is known
  about its magnetic-field sensitivity, and refuses to record the latter without a
  CrossRef-resolved DOI. Includes {t['maps']} identifier-bound maps, the QBO ontology
  ({t['entities']} entities), {t['references']} verified references, cross-species
  orthology projection, NASA OSDR data overlay, and a pre-registered statistical test
  reported with its null result and power analysis.
keywords:
{chr(10).join(f'  - "{k}"' for k in keywords)}
license: CC-BY-4.0
# The companion review is in preparation. No DOI is asserted for it, and no placeholder
# is recorded, because a plausible-looking placeholder is how a fabricated citation
# enters a bibliography and stays there.
"""
    (args.out / "CITATION.cff").write_text(cff)

    # ---- manifest + checksums ---------------------------------------------
    files = tracked_files()
    lines = ["path\tbytes\tsha256"]
    total = 0
    sums = []
    for f in sorted(files):
        data = f.read_bytes()
        h = hashlib.sha256(data).hexdigest()
        rel = f.relative_to(ROOT)
        lines.append(f"{rel}\t{len(data)}\t{h}")
        sums.append(f"{h}  {rel}")
        total += len(data)
    (args.out / "MANIFEST.tsv").write_text("\n".join(lines) + "\n")
    (args.out / "CHECKSUMS.sha256").write_text("\n".join(sums) + "\n")

    biggest = sorted(files, key=lambda f: f.stat().st_size, reverse=True)[:3]
    print(f"prepared deposit metadata for {len(files)} tracked files, {total/1e6:.2f} MB total")
    print(f"  largest: " + ", ".join(f"{f.relative_to(ROOT)} ({f.stat().st_size/1024:.0f} KB)"
                                     for f in biggest))
    print("  wrote .zenodo.json, CITATION.cff, MANIFEST.tsv, CHECKSUMS.sha256")
    if total > 50e6:
        print("  NOTE: over 50 MB — check what belongs in Zenodo rather than git")
    print("\nNot uploaded. Depositing mints a permanent public DOI; run that deliberately.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
