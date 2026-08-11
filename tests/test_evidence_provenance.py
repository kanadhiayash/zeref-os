"""SHR-072 / SHR-081: negation and mismatched-hash evidence must fail hard.

Missing-spec note: SHIROE_FULL_FUNCTIONALITY_CLAUDE_HANDOFF.md,
SHR_BACKLOG_COVERAGE_MATRIX.csv, SHIROE_EXECUTION_PROGRAM.json are absent on
disk. Acceptance-gate wording is used as the sole spec:
    "Negation cases and mismatched source hashes fail deterministically."
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from shiroe.core.errors import GuardRejection
from shiroe.guards.evidence_guard import (
    _HASH_SUFFIX_RE,
    _hash_source_bytes,
    check_card,
    contradicts_claim,
    upgrade_evidence,
)
from shiroe.memory import scaffold_project
from shiroe.memory_state import MemoryStore


def _store(root: Path) -> MemoryStore:
    (root / "AGENTS.md").write_text("# AGENTS.md\n", encoding="utf-8")
    scaffold_project(root, name="evidence", privacy="abstract", tier="auto", parent="")
    return MemoryStore.from_root(root)


# ---------- SHR-072: negation detection ---------------------------------


def test_contradicts_claim_flags_explicit_negation() -> None:
    assert contradicts_claim(
        "The API is not available in region eu-west-1.",
        "The API is available in region eu-west-1.",
    )


def test_contradicts_claim_ignores_unrelated_negation() -> None:
    assert not contradicts_claim(
        "The migration is not scheduled until Q4.",
        "The API is available in region eu-west-1.",
    )


def test_contradicts_claim_returns_false_on_supporting_text() -> None:
    assert not contradicts_claim(
        "The API is available in all regions including eu-west-1.",
        "The API is available in region eu-west-1.",
    )


def test_contradicts_claim_returns_false_on_empty_inputs() -> None:
    assert not contradicts_claim("", "claim")
    assert not contradicts_claim("some text", "")


def test_upgrade_evidence_rejects_contradicting_source(tmp_path: Path) -> None:
    store = _store(tmp_path)
    card = store.add_card(
        type="fact",
        title="api availability",
        claim="The billing API is available in region eu-west-1.",
        privacy_class="internal",
        evidence_grade="C",
        source_refs=["initial"],
    )
    refuting = tmp_path / "refuting.md"
    refuting.write_text(
        "Status: the billing API is not available in region eu-west-1.\n",
        encoding="utf-8",
    )
    with pytest.raises(GuardRejection) as exc:
        upgrade_evidence(store, card.id, str(refuting))
    assert "EvidenceGuard" in str(exc.value)
    assert "contradicts" in str(exc.value)
    fresh = store.get_card(card.id)
    assert refuting.name not in " ".join(fresh.source_refs)
    assert fresh.evidence_grade == "C"


def test_upgrade_evidence_accepts_supporting_source(tmp_path: Path) -> None:
    store = _store(tmp_path)
    card = store.add_card(
        type="fact",
        title="api availability",
        claim="The billing API is available in region eu-west-1.",
        privacy_class="internal",
        evidence_grade="C",
        source_refs=["initial"],
    )
    supporting = tmp_path / "supporting.md"
    supporting.write_text(
        "The billing API is available in region eu-west-1 and eu-central-1.\n",
        encoding="utf-8",
    )
    updated = upgrade_evidence(store, card.id, str(supporting))
    assert updated.evidence_grade == "B"
    ref = updated.source_refs[-1]
    assert _HASH_SUFFIX_RE.match(ref), f"expected pinned hash, got {ref!r}"


# ---------- SHR-081: mismatched source hash ------------------------------


def test_check_card_flags_mismatched_source_hash(tmp_path: Path) -> None:
    store = _store(tmp_path)
    src = tmp_path / "source.md"
    src.write_text("original content that will be verified.\n", encoding="utf-8")
    card = store.add_card(
        type="fact",
        title="pinned source",
        claim="Original content is present.",
        privacy_class="internal",
        evidence_grade="C",
        source_refs=["initial"],
    )
    updated = upgrade_evidence(store, card.id, str(src))
    assert all("hash mismatch" not in f.reason for f in check_card(updated))
    src.write_text("tampered content that no longer matches.\n", encoding="utf-8")
    findings = check_card(updated)
    hash_findings = [f for f in findings if "hash mismatch" in f.reason]
    assert len(hash_findings) == 1
    only = hash_findings[0]
    assert only.severity == "high"
    assert str(src) in only.reason
    assert "re-pin" in only.fix.lower()


def test_check_card_flags_missing_pinned_source(tmp_path: Path) -> None:
    store = _store(tmp_path)
    src = tmp_path / "gone.md"
    src.write_text("evidence about to vanish.\n", encoding="utf-8")
    card = store.add_card(
        type="fact",
        title="disappearing source",
        claim="Evidence about to vanish is documented.",
        privacy_class="internal",
        evidence_grade="C",
        source_refs=["initial"],
    )
    updated = upgrade_evidence(store, card.id, str(src))
    src.unlink()
    findings = check_card(updated)
    unavailable = [f for f in findings if "unavailable" in f.reason]
    assert len(unavailable) == 1
    assert str(src) in unavailable[0].reason


def test_bare_source_ref_without_hash_is_ignored_by_hash_check(tmp_path: Path) -> None:
    store = _store(tmp_path)
    card = store.add_card(
        type="fact",
        title="legacy",
        claim="Legacy card with unpinned source ref.",
        privacy_class="internal",
        evidence_grade="C",
        source_refs=["docs/PLAN.md"],
    )
    findings = check_card(card)
    assert not any("mismatch" in f.reason or "unavailable" in f.reason for f in findings)


def test_url_source_ref_is_not_pinned(tmp_path: Path) -> None:
    store = _store(tmp_path)
    card = store.add_card(
        type="fact",
        title="external",
        claim="External URL evidence.",
        privacy_class="internal",
        evidence_grade="C",
        source_refs=["initial"],
    )
    updated = upgrade_evidence(store, card.id, "https://example.com/spec")
    assert updated.source_refs[-1] == "https://example.com/spec"
    assert not _HASH_SUFFIX_RE.match(updated.source_refs[-1])


def test_hash_pin_is_stable_across_reads(tmp_path: Path) -> None:
    store = _store(tmp_path)
    src = tmp_path / "stable.md"
    src.write_text("stable content.\n", encoding="utf-8")
    card = store.add_card(
        type="fact",
        title="stable",
        claim="Stable content is documented.",
        privacy_class="internal",
        evidence_grade="C",
        source_refs=["initial"],
    )
    updated = upgrade_evidence(store, card.id, str(src))
    m = _HASH_SUFFIX_RE.match(updated.source_refs[-1])
    assert m is not None
    expected = hashlib.sha256(src.read_bytes()).hexdigest()
    assert m.group("hex") == expected
    assert _hash_source_bytes(src.read_text()) == expected


def test_pinning_is_idempotent_when_ref_already_has_hash(tmp_path: Path) -> None:
    store = _store(tmp_path)
    src = tmp_path / "idempotent.md"
    src.write_text("payload.\n", encoding="utf-8")
    card = store.add_card(
        type="fact",
        title="idem",
        claim="Payload is documented.",
        privacy_class="internal",
        evidence_grade="C",
        source_refs=["initial"],
    )
    first = upgrade_evidence(store, card.id, str(src))
    pinned_ref = first.source_refs[-1]
    second = upgrade_evidence(store, card.id, pinned_ref)
    assert second.source_refs.count(pinned_ref) == 1
    assert "#sha256:" in second.source_refs[-1]
    assert second.source_refs[-1].count("#sha256:") == 1
