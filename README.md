# Quantum Biology Atlas

**A cross-species ontology and pathway-map toolkit for quantum-biological processes —
built so omics data can be projected onto the molecular nodes where weak magnetic
fields could plausibly act.**

Companion software to the review *"Plant Responses to Near-Null Magnetic Fields:
Geomagnetism, Bioenergetics, and Primary Metabolism in Arabidopsis and Brassica"*
(D. M. Porterfield & R. Barker, Purdue University).

> **Status: in development.** The ontology, all ten maps, the map compiler, the
> orthology projection, OSDR ingestion and the legibility test are working and
> verified. The manuscript, the Pages site, the viewer integration and the Zenodo
> deposit are not yet built. Sections marked **(pending)** do not exist yet — this
> README describes only what is in the repository.

---

## The problem this solves

The review's central argument is that near-null magnetic field (NNMF) biology is not a
cryptochrome-only phenomenon: radical-pair and hyperfine processes could act across a
*distributed network* of flavins, Fe/S clusters, Rieske centres, heme-copper oxidases
and Fe/S assembly machinery — and therefore on primary metabolism itself.

That argument currently lives in eight static figures. It cannot be queried, tested
against data, or carried to another organism. This repository turns it into something
a computer can read and a reader can check.

## Design: two axes, deliberately kept apart

The ontology's whole reason for existing is that these two questions are different:

| Axis | Question | Example |
|---|---|---|
| `quantum_class` | What chemistry does this entity carry? | Complex III's Rieske centre is a [2Fe-2S] cluster |
| `evidence_tier` | How much is actually *known* about its field sensitivity? | Nobody has applied a null field and measured it |

Collapsing the two is how "contains a flavin" quietly becomes "is magnetically
sensitive". The schema makes that collapse impossible to express: a tier that asserts
a demonstrated or inferred field effect **cannot validate without a resolved DOI**.

**Evidence tiers**

| Tier | Meaning | DOI required |
|---|---|---|
| **T1** Demonstrated | A field was applied and an effect measured *on this entity* | yes |
| **T2** Inferred | Shown for the containing complex or process, not the entity | yes |
| **T3** Plausible | A physical route exists; no field measurement has been made | no — but a written `rationale` is required |
| **T4** Context | Structural only; no quantum claim | no |

The tier is rendered as a **border style** on every map: T1 solid heavy, T2 solid
light, T3 **dashed**, T4 hairline. A hypothesis literally looks provisional on the page.

**The current maps are almost entirely dashed, and that is the finding** — the
Arabidopsis NNMF literature is developmental and nutritional, and has not yet measured
a respiratory complex directly.

## What is in the repository

```
ontology/
  qbo-core.yaml              controlled vocabulary: tiers, nuclei, quantum classes,
                             field regimes, edge classes
  entities/*.yaml            the annotated entities
  schema/entity.schema.json  JSON Schema enforcing the tier/DOI rule
evidence/
  references.yaml            42 references, every one CrossRef-resolved (see below)
maps/
  src/*.yaml                 declarative map sources — no coordinates anywhere
  sbgn/*.sbgn                compiled SBGN-ML PD, QBO annotations in <extension>
  svg/*.svg                  compiled standalone SVG, light + dark
src/qbio/
  ontology.py   load, validate and query QBO
  layout.py     measured-text layout — box sizes derive from text, never the reverse
  render.py     SVG emitter, Okabe-Ito, tier-as-border-channel
  sbgn.py       SBGN-ML PD emitter with the QBO annotation extension
  maps.py       map model and compiler
scripts/
  build_evidence_base.py     builds references.yaml from the manuscript bibliography
  resolve_loci.py            resolves gene symbols to AGI loci via Ensembl Plants
tests/
  legibility_probe.js        browser-side figure legibility assertions
```

### Maps

All ten are built. 126 nodes, 168 edges, 125 distinct Arabidopsis loci.

| Map | Nodes | Derived from |
|---|---|---|
| QBM-01 Mitochondrial ETC & oxidative phosphorylation | 17 | Figures 1A, 4 |
| QBM-02 Photosynthetic electron transport & plastid redox | 14 | Figures 1B, 5 |
| QBM-03 Cryptochrome radical-pair photochemistry | 8 | Figure 3A |
| QBM-04 Fe/S biogenesis — ISC, SUF, CIA | 11 | Figure 3B |
| QBM-05 TCA cycle & the Fe/S-dependent steps | 13 | Figure 4, redrawn as a closed cycle |
| QBM-06 Germination before photosynthesis | 11 | Figure 6 |
| QBM-07 ROS production, scavenging & redox buffering | 12 | Figures 3C, 5 |
| QBM-08 Magnetic environment → phenotype (flagship) | 19 | Figure 7 |
| QBM-09 Iron uptake & sulfate assimilation | 10 | *new* — motivated, not drawn in the review |
| QBM-10 Hormone & circadian integration | 11 | *new* — motivated, not drawn in the review |

QBM-09 and QBM-10 cover the two areas where the direct Arabidopsis evidence is
strongest — mineral nutrition and flowering-time control — and neither has a figure
in the manuscript.

## Two findings from building it

**1. The companion repo's study database has unusable DOIs.** Every DOI in
`magnetobiology-nnmf-review/data/nnmf_study_database.csv` was resolved against
CrossRef: **only 7 of 49 title-match.** Its `Belyavskaya2004` row cites
`10.1016/j.asr.2003.09.043`, which is a paper on calcium gradients in the fish inner
ear. Seven further rows cite work absent from the manuscript's bibliography with
unresolvable DOIs.

The manuscript's **own** bibliography is clean — **42/42 resolve and title-match** — so
this repository's evidence base is built from the bibliography and not from that CSV.
`scripts/build_evidence_base.py` re-verifies all 42 on every run and refuses to write
its output if any fails.

**2. Gene symbols are not safe to type from memory.** Resolving every symbol during
authoring caught five collisions that would each have put the wrong gene on a map:

| Symbol | Resolves to | The gene actually wanted |
|---|---|---|
| `ACO2` | ACC oxidase 2 (AT1G62380) | aconitase 2 (AT4G26970) |
| `LIP1` | a lipase (AT2G15230) | lipoyl synthase (AT2G20860) |
| `CAT2` | cationic amino acid transporter 2 (AT1G58030) | catalase 2 (AT4G35090) |
| `CAT3` | cationic amino acid transporter 3 (AT5G36940) | catalase 3 (AT1G20620) |
| `KAT2` | a potassium channel (AT4G18290) | 3-ketoacyl-CoA thiolase (AT2G33150) |

The ontology therefore stores AGI loci, never symbols, and every locus is re-checked
against Ensembl by the tests.

## Figure legibility is a test, not a review step

The draft review's figures carry the margin note *"The text spills out of the box's…
and the TCA cycle needs some work"*. Rendering them confirmed it: Figure 4's TCA cycle
is drawn as a linear chain with no OAA→citrate closure, and its six "data" panels are
`1.0` vs `1.0 ± 0.4` from a hand-written direction list — the identical 40% effect six
times, with no underlying measurement.

Both are fixed structurally rather than by nudging:

* **Boxes are sized around measured text**, so a label cannot overflow its box by
  construction. An unbreakable token widens the box rather than being clipped.
* **`tests/legibility_probe.js` measures what a browser actually painted**, in screen
  space, using the browser's own text layout — not a re-run of the compiler's
  arithmetic. It asserts no text overflow, no overlapping node boxes, nothing clipped
  by the canvas, no edge label covering a node, and a caption that states provenance.
* An edge label that cannot be placed without covering a node is **dropped and
  reported in the build record**, not drawn on top of one.

Each assertion was verified non-vacuous by injecting the matching defect into a clean
map and confirming the probe fires.

**No quantitative value is encoded in a base map.** Numbers appear only when measured
data is projected onto one.

## Usage

```bash
python3 -m pip install pyyaml matplotlib
PYTHONPATH=src python3 -c "
from qbio import ontology, maps
onto = ontology.load()
for rec in maps.compile_all(onto):
    print(rec['id'], rec['nodes'], 'nodes', rec['tiers'])
"
```

Rebuild the evidence base (network, ~30 s):

```bash
python3 scripts/build_evidence_base.py --manuscript data/manuscript_text.txt --out evidence/references.yaml
```

## Cross-species projection

`qbio.ortho` runs two independent backbones and reports their disagreement rather than
picking a winner:

- **Ensembl Compara `pan_homology`** — the only division that crosses kingdoms
  (`plants` does not), confirmed live: human *NDUFS1* returns an *A. thaliana*
  ortholog, At*CRY1* returns *D. melanogaster*.
- **OrthoDB v12** — the committed human-anchored matrix from `OSDR_X-species_V2`.

Projecting the QBO loci to human maps 15 of 28, with the two methods agreeing on 6 and
disagreeing on 0. The unmapped set is itself the validation: every alternative-oxidase
and type II NAD(P)H dehydrogenase locus fails to map, which is correct — humans have
neither.

Every projection reports coverage, and a projection that matches nothing **raises**
rather than returning an empty frame that would render as a blank map.

## Pending

- **(pending)** The pre-registered enrichment test against `OSDR_X-species_V2`'s
  conserved mitochondrial suppression
- **(pending)** Integration with the
  [SBGN Pathway Visualizer](https://dr-richard-barker.github.io/SBGN-Pathway-viewer/app/)
  via a published map catalogue
- **(pending)** GitHub Pages site, manuscript, Zenodo deposit
- **(pending)** Repair of the 49 DOIs in `magnetobiology-nnmf-review`

## Licensing

Code in `src/` and `scripts/` is MIT. The ontology (`ontology/`), maps (`maps/`) and
evidence base (`evidence/`) are CC-BY-4.0.

## Citing

The review is in preparation; no DOI has been issued. Cite this repository by URL until
one exists — do not cite a placeholder DOI.
