from __future__ import annotations

import pytest

from shiroe.memory.schemas import AtomValidationError, create_atom, make_atom_id, validate_atom


def test_create_atom_returns_valid_complete_atom() -> None:
    atom = create_atom(
        atom_type="decision",
        claim="Use deterministic token overlap before optional vector search.",
        summary="Prefer stdlib SQLite for local recall.",
        source="manual:test",
        source_type="manual",
        evidence="A",
        confidence="high",
        privacy="public-safe",
        provenance="unit-test",
        created_at="2026-07-09T10:00:00+00:00",
    )

    validate_atom(atom)
    assert atom["type"] == "decision"
    assert atom["id"] == make_atom_id(
        "decision",
        "Use deterministic token overlap before optional vector search.",
        "manual:test",
        "2026-07-09T10:00:00+00:00",
        "unit-test",
    )


def test_validate_atom_rejects_missing_required_fields() -> None:
    atom = create_atom(
        atom_type="fact",
        claim="Shiroe stores memory locally.",
        summary="Local-first memory claim.",
        source="manual:test",
    )
    del atom["created_at"]

    with pytest.raises(AtomValidationError) as exc:
        validate_atom(atom)

    assert "missing required field: created_at" in str(exc.value)


def test_validate_atom_rejects_invalid_enums_and_list_shapes() -> None:
    atom = create_atom(
        atom_type="risk",
        claim="Unsupported claims can leak into docs.",
        summary="Fact guard should flag unsupported claims.",
        source="manual:test",
    )
    atom["type"] = "not_a_real_atom_type"
    atom["evidence"] = "Z"
    atom["confidence"] = "certain"
    atom["status"] = "new"
    atom["entities"] = "Shiroe"

    with pytest.raises(AtomValidationError) as exc:
        validate_atom(atom)

    message = str(exc.value)
    assert "invalid type: not_a_real_atom_type" in message
    assert "invalid evidence: Z" in message
    assert "invalid confidence: certain" in message
    assert "invalid status: new" in message
    assert "entities must be a list" in message


def test_validate_atom_requires_created_at_iso_timestamp() -> None:
    atom = create_atom(
        atom_type="task",
        claim="Add atom store tests.",
        summary="Test append and patch behavior.",
        source="manual:test",
    )
    atom["created_at"] = "not-a-date"

    with pytest.raises(AtomValidationError) as exc:
        validate_atom(atom)

    assert "created_at must be ISO-8601 or null" in str(exc.value)
