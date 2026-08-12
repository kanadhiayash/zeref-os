"""
Canonical-state contract (SHR-001, SHR-002, SHR-008).

ADR-0001 settled one question for the whole tree: SQLite holds canonical
current state, JSONL holds canonical append-only history, Markdown is a
generated view. ADR-0006 extends the same rule to graphs. These tests assert
that every *active* canon surface agrees with those two decisions, so a future
edit that reintroduces "canonical state is markdown on disk" fails here and
not six months later in a reader's head.

The prose detectors are imported from scripts/check-canon-consistency.py
rather than re-written. Two copies of a regex drift; one does not. This file
asserts the active canonical-state invariant holds.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest


ADR_0001 = "docs/adr/ADR-0001-canonical-store.md"
ADR_0006 = "docs/adr/ADR-0006-graph-projection-invariant.md"

# The rules that encode "Markdown/wiki is the record of truth". Any hit on an
# active surface is a contradiction of ADR-0001.
CANONICAL_STATE_RULES = {
    "markdown-canonical",
    "canonical-wiki",
    "markdown-source-of-truth",
}

# Findings PR 02 owns. Each must be gone from the tree AND retired from the
# acknowledgement ledger — an acknowledgement is a debt record, and leaving it
# behind after paying the debt is itself drift (the checker's DROPPED rule).
RESOLVED_BASELINE_IDS = {
    "AGENTS.md::markdown-canonical",
    "AGENTS.md::canonical-wiki",
    "SOUL.md::markdown-canonical",
    "PRIVACY.md::markdown-canonical",
    "skills/wiki-maintenance/SKILL.md::canonical-wiki",
}


@pytest.fixture(scope="module")
def canon(repo_root: Path):
    """The canon checker, loaded as a module from scripts/."""
    path = repo_root / "scripts" / "check-canon-consistency.py"
    assert path.exists(), f"canon checker missing: {path}"
    spec = importlib.util.spec_from_file_location("_canon_checker", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def active_surfaces(repo_root: Path, canon) -> dict[str, tuple[int, str]]:
    amap = canon.load_authority_map(repo_root)
    classification, _ = canon.classify(amap, canon.walk_files(repo_root))
    return classification.active


def _read(repo_root: Path, rel: str) -> str:
    path = repo_root / rel
    assert path.exists(), f"expected surface missing: {rel}"
    return path.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# SHR-002 — the invariant holds across every active surface
# --------------------------------------------------------------------------- #


def test_no_active_surface_claims_markdown_is_canonical_state(repo_root, canon, active_surfaces):
    """
    ADR-0001 is exempt (its Context has to quote the contradiction it retired).
    Every other active surface must be clean. Archived material is out of scope
    by design — that is what "superseded" means.
    """
    amap = canon.load_authority_map(repo_root)
    exempt = {rule["authority"] for rule in amap["conflict_rules"]}

    offenders: list[str] = []
    for rel in sorted(active_surfaces):
        if rel in exempt:
            continue
        text = canon.read_text(repo_root, rel)
        if text is None:
            continue
        for rule, pattern in canon.CONFLICT_RULES:
            if rule not in CANONICAL_STATE_RULES:
                continue
            for hit in canon._contradiction_hits(text, pattern):
                offenders.append(f"{rel} [{rule}]: {hit!r}")

    assert not offenders, (
        "active canon surface(s) contradict ADR-0001 (SQLite = canonical current "
        "state, JSONL = canonical history, Markdown = generated view):\n  "
        + "\n  ".join(offenders)
    )


def test_agents_md_is_behavioural_canon_not_storage_canon(repo_root):
    """
    SHR-001. AGENTS.md stays canonical for *behaviour*; it must not also claim
    to settle where state lives, and must point at the ADR that does.
    """
    text = _read(repo_root, "AGENTS.md")
    assert "ADR-0001" in text, (
        "AGENTS.md must defer the storage question to ADR-0001 rather than "
        "restating it (or contradicting it) in its own words"
    )


# --------------------------------------------------------------------------- #
# SHR-002 — the authority itself
# --------------------------------------------------------------------------- #


def test_adr_0001_is_accepted_and_states_the_three_way_split(repo_root):
    text = _read(repo_root, ADR_0001)
    assert "**Status:** Accepted" in text
    lowered = text.lower()
    for phrase in (
        "**sqlite** — canonical current state",
        "**jsonl** — canonical append-only history",
        "**markdown** — generated human-readable view",
    ):
        assert phrase in lowered, f"{ADR_0001} no longer states: {phrase}"


@pytest.mark.parametrize("rel", ["docs/GLOSSARY.md", "docs/wiki/Architecture.md"])
def test_vocabulary_surfaces_state_the_three_way_split(repo_root, rel):
    """The glossary fixes the words; Architecture.md draws the picture. Both
    must name all three stores with the same roles the ADR gives them."""
    lowered = _read(repo_root, rel).lower()
    assert "sqlite" in lowered and "jsonl" in lowered and "markdown" in lowered
    assert "canonical current state" in lowered
    assert "canonical append-only history" in lowered
    assert re.search(r"generated .{0,12}human-readable view", lowered), (
        f"{rel} must describe Markdown as a generated human-readable view"
    )
    assert "adr-0001" in lowered, f"{rel} must cite ADR-0001 as the authority"


# --------------------------------------------------------------------------- #
# SHR-008 — the graph projection invariant
# --------------------------------------------------------------------------- #


def test_adr_0006_exists_and_is_accepted(repo_root):
    text = _read(repo_root, ADR_0006)
    assert "**Status:** Accepted" in text
    assert "**Date:** 2026-08-04" in text


def test_adr_0006_declares_graphs_non_canonical(repo_root):
    """Every clause SHR-008 requires, asserted individually so a partial
    rewrite names the clause it dropped."""
    lowered = _read(repo_root, ADR_0006).lower()
    required = {
        "graphs are never canonical state": "never canonical",
        "a projection is deletable without data loss": "deletable",
        "projections are rebuildable": "rebuild",
        "task-graph topology is run-scoped": "run-scoped",
        "knowledge-graph output is candidate, not verified fact": "candidate",
        "every edge carries provenance": "provenance",
        "every cycle is bounded": "bounded",
        "irreversible paths carry a human gate": "human gate",
        "promotion uses the standard write path": "promotion",
        "core graph work is sqlite + stdlib": "stdlib",
        "hosted graph systems are optional adapters": "optional adapter",
    }
    missing = [clause for clause, token in required.items() if token not in lowered]
    assert not missing, f"{ADR_0006} does not establish: {missing}"


def test_adr_0006_is_registered_as_the_graph_authority(repo_root):
    """An ADR nobody points at is prose. The authority map must name it."""
    authority = _read(repo_root, "docs/canon/SOURCE_AUTHORITY.md")
    block = re.search(
        r"```json\s+shiroe\.source-authority/v1\s*\n(.*?)\n```", authority, re.DOTALL
    )
    assert block, "SOURCE_AUTHORITY.md authority block not found"
    amap = json.loads(block.group(1))
    authorities = {rule["authority"] for rule in amap["conflict_rules"]}
    assert ADR_0006 in authorities, (
        "ADR-0006 must be a registered conflict authority so the canon gate "
        "checks it is Accepted"
    )


# --------------------------------------------------------------------------- #
# The debt record is repaid
# --------------------------------------------------------------------------- #


def test_resolved_findings_are_retired_from_the_baseline(repo_root):
    baseline = json.loads(
        _read(repo_root, "docs/canon/canon-baseline.json")
    )
    still_listed = {
        entry["id"] for entry in baseline["findings"]
        if entry["id"] in RESOLVED_BASELINE_IDS
    }
    assert not still_listed, (
        "these findings are fixed in the tree but still acknowledged in "
        f"canon-baseline.json: {sorted(still_listed)}"
    )
