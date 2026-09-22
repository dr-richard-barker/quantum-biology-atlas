"""Shared fixtures and network handling for the test suite.

Tests that reach the network (CrossRef, Ensembl, UniProt, OSDR) are marked
`@pytest.mark.network`. They are the point of several assertions here — a DOI that
resolves only in a cached copy is not a verified DOI — so they run by default, and
are skipped with `-m "not network"` for an offline or air-gapped run.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "network: test reaches an external API (skip with -m 'not network')"
    )


@pytest.fixture(scope="session")
def root() -> pathlib.Path:
    return ROOT


@pytest.fixture(scope="session")
def onto():
    from qbio import ontology

    return ontology.load()


@pytest.fixture(scope="session")
def map_records(onto):
    from qbio import maps

    return maps.compile_all(onto)
