"""Canonical memory-card schema tests."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from shiroe.core.errors import ValidationError
from shiroe.core.schema import MemoryCard, create_memory_card
from shiroe.memory import scaffold_project
from shiroe.memory.models import MemoryWrite
from shiroe.memory.service import MemoryService


def test_valid_memory_card_creation() -> None:
    card = create_memory_card(
        type="fact",
        title="public-safe copy preference",
        claim="User prefers public-safe copy by default.",
        privacy_class="internal",
        evidence_grade="B",
        source_refs=["memory/hot.md"],
        confidence="high",
        tags=["memory"],
        now=datetime(2026, 7, 9, tzinfo=timezone.utc),
    )

    assert card.id == "mem_2026_07_09_0001"
    assert card.status == "active"
    assert card.owner == "shiroe"


def test_invalid_memory_type_rejected() -> None:
    with pytest.raises(ValidationError, match="type must be one of"):
        create_memory_card(
            type="vibe",
            title="bad",
            claim="Bad type.",
            privacy_class="internal",
            evidence_grade="B",
            source_refs=["README.md"],
        )


def test_missing_privacy_class_rejected() -> None:
    with pytest.raises(ValidationError, match="privacy_class is required"):
        create_memory_card(
            type="fact",
            title="missing privacy",
            claim="A factual claim.",
            privacy_class="",
            evidence_grade="B",
            source_refs=["README.md"],
        )


def test_missing_evidence_grade_rejected() -> None:
    with pytest.raises(ValidationError, match="evidence_grade is required"):
        create_memory_card(
            type="fact",
            title="missing evidence",
            claim="A factual claim.",
            privacy_class="internal",
            evidence_grade="",
            source_refs=["README.md"],
        )


def test_missing_source_refs_rejected_for_facts() -> None:
    with pytest.raises(ValidationError, match="source_refs are required"):
        create_memory_card(
            type="fact",
            title="missing source",
            claim="A factual claim.",
            privacy_class="internal",
            evidence_grade="B",
        )


def test_source_refs_optional_for_unknown_and_assumption() -> None:
    unknown = create_memory_card(
        type="unknown",
        title="unknown state",
        claim="The deployment target is unknown.",
        privacy_class="internal",
        evidence_grade="D",
    )
    assumption = create_memory_card(
        type="assumption",
        title="assumed workflow",
        claim="Linear is the delivery source of truth.",
        privacy_class="internal",
        evidence_grade="C",
    )
    assert unknown.source_refs == []
    assert assumption.source_refs == []


def test_memory_store_archives_and_supersedes_cards(tmp_path) -> None:
    (tmp_path / "AGENTS.md").write_text("# AGENTS.md\n", encoding="utf-8")
    scaffold_project(tmp_path, name="cards", privacy="abstract", network_scope="device-only")
    store = MemoryService(tmp_path)

    old = store.write(
        MemoryWrite(
            kind="decision",
            title="old routing policy",
            claim="Use flagship models for all tasks.",
            privacy_class="internal",
            evidence_grade="C",
            source_refs=("AGENTS.md",),
        )
    )
    archived = store.archive(old.id)
    assert archived.status == "archived"

    replacement = store.write(
        MemoryWrite(
            kind="decision",
            title="risk-based routing policy",
            claim="Use flagship models only for critical tasks.",
            privacy_class="internal",
            evidence_grade="B",
            source_refs=("AGENTS.md",),
        )
    )
    superseded = store.supersede(replacement.id)

    assert superseded.status == "superseded"
    assert store.get(replacement.id).status == "superseded"
    assert replacement.kind == "decision"
