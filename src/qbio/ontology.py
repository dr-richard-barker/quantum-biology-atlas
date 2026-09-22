"""
QBO — load, validate and query the Quantum Biology Ontology.

The ontology is two orthogonal axes (see ontology/qbo-core.yaml):

    quantum_class    what chemistry an entity carries — structural, uncontroversial
    evidence_tier    how much is actually known about its magnetic-field sensitivity

Everything in this module exists to stop those two collapsing into each other.
`Entity.is_magnetically_addressable` answers "could a weak field act here in
principle"; `Entity.asserts_sensitivity` answers "has anyone shown that it does".
They are deliberately different methods with deliberately different names.
"""
from __future__ import annotations

import dataclasses
import pathlib
from typing import Iterable, Iterator, Sequence

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
ONTOLOGY_DIR = ROOT / "ontology"
ENTITY_DIR = ONTOLOGY_DIR / "entities"
CORE_PATH = ONTOLOGY_DIR / "qbo-core.yaml"
REFERENCES_PATH = ROOT / "evidence" / "references.yaml"

#: Tiers that make a positive claim about magnetic-field sensitivity and must cite a DOI.
ASSERTING_TIERS = frozenset({"T1", "T2"})


class OntologyError(Exception):
    """Raised when the ontology is internally inconsistent. Never warned, always raised."""


@dataclasses.dataclass(frozen=True)
class Evidence:
    ref: str
    claim: str
    species: str | None = None
    field_regime: str | None = None
    field_uT: float | None = None
    direction: str | None = None
    tissue: str | None = None
    developmental_stage: str | None = None


@dataclasses.dataclass(frozen=True)
class Entity:
    id: str
    label: str
    kind: str
    quantum_class: tuple[str, ...]
    evidence_tier: str
    confidence: str
    description: str | None = None
    compartment: str | None = None
    nuclei: tuple[str, ...] = ()
    cofactors: tuple[str, ...] = ()
    xref: dict[str, tuple[str, ...]] = dataclasses.field(default_factory=dict)
    evidence: tuple[Evidence, ...] = ()
    rationale: str | None = None
    caveat: str | None = None
    note: str | None = None
    source_file: str | None = None

    # -- identifier access -------------------------------------------------
    @property
    def agi(self) -> tuple[str, ...]:
        return tuple(self.xref.get("agi", ()))

    def identifiers(self, namespace: str) -> tuple[str, ...]:
        return tuple(self.xref.get(namespace, ()))

    # -- the two axes, kept apart ------------------------------------------
    def is_magnetically_addressable(self, core: "QBOCore") -> bool:
        """Does any quantum_class provide a physical route for a weak field?

        A statement about mechanism availability. Says nothing about evidence.
        """
        return any(core.quantum_class(c).get("magnetically_addressable") for c in self.quantum_class)

    @property
    def asserts_sensitivity(self) -> bool:
        """Does this entity claim a magnetic-field effect has actually been shown?"""
        return self.evidence_tier in ASSERTING_TIERS

    @property
    def dois(self) -> tuple[str, ...]:
        return tuple(e.ref for e in self.evidence)


class QBOCore:
    """The controlled vocabulary: tiers, nuclei, quantum classes, regimes, edges."""

    def __init__(self, data: dict):
        self._data = data
        self.version: str = data.get("qbo_version", "0")
        self._quantum = {c["id"]: c for c in data.get("quantum_classes", [])}
        self._nuclei = {n["id"]: n for n in data.get("nuclei", [])}
        self._tiers = {t["id"]: t for t in data.get("evidence_tiers", [])}
        self._regimes = {r["id"]: r for r in data.get("field_regimes", [])}
        self._edges = {e["id"]: e for e in data.get("edge_classes", [])}
        self._confidence = {c["id"]: c for c in data.get("confidence_levels", [])}

    def quantum_class(self, cid: str) -> dict:
        try:
            return self._quantum[cid]
        except KeyError:
            raise OntologyError(f"unknown quantum_class {cid!r}") from None

    def nucleus(self, nid: str) -> dict:
        try:
            return self._nuclei[nid]
        except KeyError:
            raise OntologyError(f"unknown nucleus {nid!r}") from None

    def edge_class(self, eid: str) -> dict:
        try:
            return self._edges[eid]
        except KeyError:
            raise OntologyError(f"unknown edge_class {eid!r}") from None

    @property
    def quantum_class_ids(self) -> frozenset[str]:
        return frozenset(self._quantum)

    @property
    def nucleus_ids(self) -> frozenset[str]:
        return frozenset(self._nuclei)

    @property
    def tier_ids(self) -> frozenset[str]:
        return frozenset(self._tiers)

    @property
    def confidence_ids(self) -> frozenset[str]:
        return frozenset(self._confidence)

    @property
    def regime_ids(self) -> frozenset[str]:
        return frozenset(self._regimes)

    @property
    def edge_class_ids(self) -> frozenset[str]:
        return frozenset(self._edges)

    def tier(self, tid: str) -> dict:
        try:
            return self._tiers[tid]
        except KeyError:
            raise OntologyError(f"unknown evidence_tier {tid!r}") from None


class Ontology:
    """Loaded QBO: the core vocabulary plus every annotated entity."""

    def __init__(self, core: QBOCore, entities: Sequence[Entity], references: dict[str, dict]):
        self.core = core
        self._entities = {e.id: e for e in entities}
        self.references = references
        if len(self._entities) != len(entities):
            dupes = [e.id for e in entities if list(x.id for x in entities).count(e.id) > 1]
            raise OntologyError(f"duplicate entity ids: {sorted(set(dupes))}")

    # -- access ------------------------------------------------------------
    def __len__(self) -> int:
        return len(self._entities)

    def __iter__(self) -> Iterator[Entity]:
        return iter(self._entities.values())

    def __contains__(self, eid: object) -> bool:
        return eid in self._entities

    def __getitem__(self, eid: str) -> Entity:
        try:
            return self._entities[eid]
        except KeyError:
            raise OntologyError(f"no QBO entity {eid!r}") from None

    def get(self, eid: str, default=None):
        return self._entities.get(eid, default)

    # -- queries -----------------------------------------------------------
    def by_quantum_class(self, *classes: str) -> list[Entity]:
        want = set(classes)
        unknown = want - self.core.quantum_class_ids
        if unknown:
            raise OntologyError(f"unknown quantum_class(es): {sorted(unknown)}")
        return [e for e in self if want & set(e.quantum_class)]

    def by_tier(self, *tiers: str) -> list[Entity]:
        want = set(tiers)
        unknown = want - self.core.tier_ids
        if unknown:
            raise OntologyError(f"unknown tier(s): {sorted(unknown)}")
        return [e for e in self if e.evidence_tier in want]

    def by_nucleus(self, nucleus: str) -> list[Entity]:
        self.core.nucleus(nucleus)
        return [e for e in self if nucleus in e.nuclei]

    def by_compartment(self, compartment: str) -> list[Entity]:
        return [e for e in self if e.compartment == compartment]

    def magnetically_addressable(self) -> list[Entity]:
        """Entities with a physical route, regardless of whether it has been tested."""
        return [e for e in self if e.is_magnetically_addressable(self.core)]

    def asserting(self) -> list[Entity]:
        """Entities claiming a demonstrated or inferred magnetic-field effect (T1/T2)."""
        return [e for e in self if e.asserts_sensitivity]

    def index_by_agi(self) -> dict[str, list[Entity]]:
        """AGI locus -> entities. One locus can appear on several maps."""
        idx: dict[str, list[Entity]] = {}
        for e in self:
            for locus in e.agi:
                idx.setdefault(locus.upper(), []).append(e)
        return idx

    # -- integrity ---------------------------------------------------------
    def validate(self) -> list[str]:
        """Return a list of problems. Empty list means the ontology is coherent.

        Callers decide whether to raise; `tests/test_ontology.py` asserts empty.
        """
        problems: list[str] = []
        for e in self:
            where = f"{e.id} ({e.source_file})"

            for c in e.quantum_class:
                if c not in self.core.quantum_class_ids:
                    problems.append(f"{where}: unknown quantum_class {c!r}")
            for n in e.nuclei:
                if n not in self.core.nucleus_ids:
                    problems.append(f"{where}: unknown nucleus {n!r}")
            if e.evidence_tier not in self.core.tier_ids:
                problems.append(f"{where}: unknown evidence_tier {e.evidence_tier!r}")
            if e.confidence not in self.core.confidence_ids:
                problems.append(f"{where}: unknown confidence {e.confidence!r}")

            # The rule the ontology exists to enforce.
            if e.asserts_sensitivity and not e.evidence:
                problems.append(
                    f"{where}: tier {e.evidence_tier} asserts a magnetic-field effect "
                    f"but cites no evidence"
                )
            # structural_context + T1/T2 is ALLOWED, and is a category the field
            # genuinely needs: a demonstrated magnetic-field effect on something with
            # no proposed quantum route. Arabidopsis iron uptake is exactly that —
            # Islam 2020 measured it, and nobody claims a spin mechanism for a
            # nutrient pool. An earlier version of this rule forbade the combination,
            # which quietly re-coupled the two axes the ontology exists to separate
            # and would have forced such findings to be mislabelled as mechanism.
            #
            # What it must not do is pass silently: an unexplained effect has to be
            # marked as unexplained, so it cannot be read as mechanistic support.
            if (
                "structural_context" in e.quantum_class
                and e.asserts_sensitivity
                and not (e.caveat or e.note or e.rationale)
            ):
                problems.append(
                    f"{where}: tier {e.evidence_tier} asserts a magnetic-field effect on an "
                    f"entity classed structural_context, i.e. with no proposed quantum route. "
                    f"That is a legitimate finding but it must say so — add a `rationale`, "
                    f"`note` or `caveat` stating that no mechanism is claimed"
                )
            # T3 is a hypothesis; the reasoning is the annotation, so say it out loud.
            if e.evidence_tier == "T3" and not e.rationale:
                problems.append(f"{where}: tier T3 requires a `rationale` stating the reasoning")

            for ev in e.evidence:
                if ev.ref not in self.references:
                    problems.append(
                        f"{where}: evidence cites {ev.ref!r}, which is not in "
                        f"evidence/references.yaml"
                    )
                if ev.field_regime and ev.field_regime not in self.core.regime_ids:
                    problems.append(f"{where}: unknown field_regime {ev.field_regime!r}")
        return problems


# ---------------------------------------------------------------------------
# loading
# ---------------------------------------------------------------------------
def _as_tuple(v) -> tuple:
    if v is None:
        return ()
    if isinstance(v, (list, tuple)):
        return tuple(v)
    return (v,)


def _entity_from_dict(d: dict, source: str) -> Entity:
    missing = {"id", "label", "kind", "quantum_class", "evidence_tier", "confidence"} - set(d)
    if missing:
        raise OntologyError(f"{source}: entity missing required field(s) {sorted(missing)}: {d.get('id', d)!r}")
    xref = {k: _as_tuple(v) for k, v in (d.get("xref") or {}).items()}
    evidence = tuple(
        Evidence(
            ref=e["ref"],
            claim=e["claim"],
            species=e.get("species"),
            field_regime=e.get("field_regime"),
            field_uT=e.get("field_uT"),
            direction=e.get("direction"),
            tissue=e.get("tissue"),
            developmental_stage=e.get("developmental_stage"),
        )
        for e in (d.get("evidence") or [])
    )
    return Entity(
        id=d["id"],
        label=d["label"],
        kind=d["kind"],
        quantum_class=_as_tuple(d["quantum_class"]),
        evidence_tier=d["evidence_tier"],
        confidence=d["confidence"],
        description=d.get("description"),
        compartment=d.get("compartment"),
        nuclei=_as_tuple(d.get("nuclei")),
        cofactors=_as_tuple(d.get("cofactors")),
        xref=xref,
        evidence=evidence,
        rationale=d.get("rationale"),
        caveat=d.get("caveat"),
        note=d.get("note"),
        source_file=source,
    )


def load_references(path: pathlib.Path = REFERENCES_PATH) -> dict[str, dict]:
    """Load the CrossRef-verified bibliography, keyed by citation key."""
    if not path.exists():
        raise OntologyError(
            f"{path} not found — run scripts/build_evidence_base.py first. "
            "The ontology may not cite anything that has not been resolved."
        )
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {r["key"]: r for r in data.get("references", [])}


def load(
    entity_dir: pathlib.Path = ENTITY_DIR,
    core_path: pathlib.Path = CORE_PATH,
    references_path: pathlib.Path = REFERENCES_PATH,
    strict: bool = True,
) -> Ontology:
    """Load the whole ontology. With strict=True (default) an inconsistency raises."""
    core = QBOCore(yaml.safe_load(core_path.read_text(encoding="utf-8")))
    references = load_references(references_path)

    entities: list[Entity] = []
    for f in sorted(entity_dir.glob("*.yaml")):
        doc = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        for raw in doc.get("entities", []):
            entities.append(_entity_from_dict(raw, f.name))

    onto = Ontology(core, entities, references)
    if strict:
        problems = onto.validate()
        if problems:
            raise OntologyError(
                f"{len(problems)} ontology problem(s):\n  " + "\n  ".join(problems)
            )
    return onto
