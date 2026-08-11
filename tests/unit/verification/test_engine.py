from __future__ import annotations

from shiroe.memory.models import MemoryWrite
from shiroe.verification import VerificationEngine


def test_verification_report_blocks_when_any_required_check_blocks(tmp_path):
    proposal = MemoryWrite(
        kind="decision",
        title="Credential",
        claim="Use token sk-proj-THIS_IS_SYNTHETIC_NOT_REAL_1234567890",
        source_refs=("user-input",),
        privacy_class="internal",
        evidence_grade="C",
    )

    report = VerificationEngine(tmp_path).verify_memory_write(proposal)

    assert report.status.value == "block"
    assert any(
        check.name == "privacy" and check.status.value == "block"
        for check in report.checks
    )
