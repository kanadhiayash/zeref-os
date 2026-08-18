"""Verification is enforced at the canonical write boundary.

These tests pin that a DIRECT `MemoryService.write` (and the compatibility
`MemoryWriter.write_decision`) runs the full VerificationEngine before
persistence, so Python callers cannot bypass privacy/credential/contradiction
gates that previously lived only in the CLI wrapper.
"""

from __future__ import annotations

import pytest

from shiroe.memory.core import MemoryWriter
from shiroe.memory.models import MemoryWrite
from shiroe.memory.service import MemoryService

# Synthetic, non-functional credential shape used purely to trip the scrubber.
_CREDENTIAL_CLAIM = "Use token sk-proj-THIS_IS_SYNTHETIC_NOT_REAL_1234567890"


def test_write_rejects_credential_shaped_claim(tmp_path):
    svc = MemoryService(tmp_path)

    with pytest.raises(ValueError, match="credential"):
        svc.write(
            MemoryWrite(
                kind="decision",
                title="Store a token",
                claim=_CREDENTIAL_CLAIM,
                source_refs=("user-input",),
                privacy_class="internal",
                evidence_grade="C",
            )
        )

    assert svc.list(statuses=()) == ()


def test_write_rejects_blocked_privacy_class(tmp_path):
    # The engine blocks this at the verification boundary ("cannot be stored")
    # BEFORE persistence -- distinct from the storage-layer event validator,
    # which only rejects "secret" AFTER the write path has been entered.
    svc = MemoryService(tmp_path)

    with pytest.raises(ValueError, match="cannot be stored"):
        svc.write(
            MemoryWrite(
                kind="decision",
                title="Secret thing",
                claim="This should never be stored.",
                source_refs=("user-input",),
                privacy_class="secret",
                evidence_grade="C",
            )
        )

    assert svc.list(statuses=()) == ()


def test_write_rejects_contradiction_against_active_memory(tmp_path):
    svc = MemoryService(tmp_path)
    svc.write(
        MemoryWrite(
            kind="fact",
            title="Telemetry state",
            claim="Feature telemetry is disabled",
            source_refs=("docs/telemetry.md",),
            evidence_grade="A",
        )
    )

    with pytest.raises(ValueError, match="contradict"):
        svc.write(
            MemoryWrite(
                kind="fact",
                title="Telemetry state",
                claim="Feature telemetry is enabled",
                source_refs=("docs/telemetry.md",),
                evidence_grade="A",
            )
        )


def test_write_decision_rejects_contradiction_against_active_memory(tmp_path):
    (tmp_path / "AGENTS.md").write_text("# marker\n", encoding="utf-8")
    svc = MemoryService(tmp_path)
    svc.write(
        MemoryWrite(
            kind="fact",
            title="Telemetry state",
            claim="Feature telemetry is disabled",
            source_refs=("docs/telemetry.md",),
            evidence_grade="A",
        )
    )

    writer = MemoryWriter.from_root(tmp_path)
    with pytest.raises(ValueError, match="contradict"):
        writer.write_decision(
            title="Feature telemetry is enabled",
            why="We turned it on",
            evidence="user-input",
            grade="C",
        )
