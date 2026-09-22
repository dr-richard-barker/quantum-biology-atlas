# Pre-registered test — result

**Question.** Is conserved spaceflight suppression associated with spin-bearing
cofactor chemistry?

**Answer.** No association was detected — and, more importantly, **this dataset could
not have detected one unless it were very large.** The honest conclusion is not "the
hypothesis is wrong" but "this is the wrong data to test it with."

The pre-registration (hypothesis, null, data, test and confounds) was committed in
`scripts/preregistered_test.py` before the script was run — commit `98e470a`, one
commit before the result. Nothing in it was edited afterwards.

---

## Result

**Primary test** — any spin-bearing cofactor (Fe-S, flavin or heme), conserved-down
versus conserved-up:

| | carries a spin cofactor | does not | rate |
|---|---|---|---|
| conserved **down** | 13 | 330 | 3.8 % |
| conserved **up** | 6 | 241 | 2.4 % |

**Odds ratio 1.58, 95 % CI 0.59–3.93, Fisher exact p = 0.48. Fail to reject H0.**

Per cofactor class:

| Class | down | up | OR | p |
|---|---|---|---|---|
| iron-sulfur | 5 / 343 | 4 / 247 | **0.90** | 1.0 |
| heme | 4 / 343 | 2 / 247 | 1.45 | 1.0 |
| flavoprotein | 4 in universe | — | — | underpowered, not tested |

Iron-sulfur chemistry — the mechanism the review argues hardest for — shows an odds
ratio of 0.90. That is not a weak signal; it is the absence of one.

No compartment stratum reached significance. Five of fourteen strata fell below the
pre-specified 20-gene threshold and were not tested.

---

## Why the negative result does not settle anything

A simulation on the realised marginals (343 down, 247 up, 2.4 % baseline exposure)
gives the effect size this design could actually have found:

| True odds ratio | Power |
|---|---|
| 1.5 | 0.09 |
| 2.0 | 0.26 |
| 2.5 | 0.49 |
| 3.0 | 0.69 |
| **4.0** | **0.93** |

**Minimum detectable odds ratio at 80 % power: 4.0.**

A genuine doubling of odds would have been missed three times in four. So `p = 0.48`
carries almost no information about whether a moderate effect exists. The confidence
interval says the same thing more directly: it spans 0.59 to 3.93, and is consistent
with anything from a modest protective association to a near-quadrupling.

Reporting this as "no evidence for the hypothesis" would be as wrong as reporting it
as support.

---

## Three reasons this dataset cannot answer the question

**1. Only 19 of 590 genes carry a spin-bearing cofactor.** The conservation table
retains 832 genes, of which 590 have an unambiguous direction. Nineteen of those are
annotated with an Fe-S cluster, a flavin or a heme. No test on nineteen exposed genes
can resolve a moderate effect.

**2. The mitochondrial stratum has no contrast.** All 51 conserved mitochondrial genes
in the table are suppressed; none are up-regulated. The compartment where the review's
hypothesis would apply most strongly is therefore untestable by this design — there is
nothing to compare against. This is itself a consequence of the source study's finding
(conserved mitochondrial suppression), which makes the two analyses structurally
unable to inform each other.

**3. Spaceflight is not a magnetic-field experiment.** It bundles microgravity,
ionising radiation and a hypomagnetic environment. Even a strongly positive result
could not have attributed an effect to the magnetic component. This was stated in the
pre-registration, and it remains the binding limitation.

A fourth point is worth recording because it cost time to discover: the KEGG-derived
cofactor table shipped with the source study
(`Table_S11_cofactor_gene_mapping.csv`) contains **zero iron-sulfur entries**, despite
its generating script listing Fe-S cluster (KEGG C20124) among the cofactors to map.
It also lists only 5 heme genes and 10 FMN genes for the entire human genome, which
cannot be right. The script skips any cofactor whose cached KEGG file is missing,
without reporting the skip. UniProt/Swiss-Prot was used instead, which has 71 curated
human Fe-S proteins.

---

## What this changes

The result strengthens, rather than weakens, the review's own methodological argument.
Section 10 of the manuscript already calls for direct bioenergetic measurements —
oxygen consumption, ATP/ADP, NAD(P)H ratios, membrane potential, cytochrome oxidase
and complex activities, aconitase, Fe/S assembly gene expression — under controlled
geomagnetic-versus-near-null conditions. This analysis is evidence for why that call
is necessary: the largest available cross-species spaceflight dataset, mined as
favourably as its structure allows, cannot distinguish the hypothesis from the null in
either direction.

**A concrete design implication.** The limiting factor was the number of
cofactor-annotated genes with a directional contrast, not the number of datasets. A
future test needs an experiment that produces both up- and down-regulated
cofactor-bearing genes in the same tissue — which a near-null-field time course
during imbibition (QBM-06) would, and an endpoint spaceflight comparison does not.

---

## Reproducing

```bash
python3 scripts/preregistered_test.py
```

Writes `results/preregistered_test.json` with the full pre-registration text, every
2×2 table, the power curve and the confound check. Requires network access for
UniProt (cached in `.uniprot_cache/` after the first run) and the conservation table
in `data/external/`.

## Sources

- Conservation data: `Table_S8_organelle_conservation_final.csv`,
  [dr-richard-barker/OSDR_X-species_V2](https://github.com/dr-richard-barker/OSDR_X-species_V2)
  — 22 NASA OSDR datasets, six species, OrthoDB v12. The 49 conserved mitochondrially
  suppressed orthologs reported in that repository's README were reproduced exactly
  from this table before it was used here (mitochondrial ∩ padj ≤ 0.05 ∩ down ∩
  ≥ 3 species = 49).
- Cofactor annotation: UniProt/Swiss-Prot reviewed human proteome, keywords KW-0411
  (iron-sulfur), KW-0285 (flavoprotein), KW-0349 (heme), KW-0496 (mitochondrion),
  KW-0249 (electron transport).
