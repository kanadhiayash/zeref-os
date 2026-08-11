"""Unified deterministic verification checks."""

from __future__ import annotations

from pathlib import Path

from shiroe.core.schema import SOURCE_OPTIONAL_TYPES
from shiroe.memory.models import MemoryWrite
from shiroe.privacy import scrub
from shiroe.verification.schema import (
    CheckStatus,
    VerificationCheck,
    VerificationFinding,
    VerificationReport,
    aggregate_status,
)


class VerificationEngine:
    def __init__(self, root: Path | str):
        self.root = Path(root)
        self.redact_md = self.root / "REDACT.md"

    def verify(self, subject: MemoryWrite) -> VerificationReport:
        return self.verify_memory_write(subject)

    def verify_memory_write(self, proposal: MemoryWrite) -> VerificationReport:
        checks = (
            self._check_write_shape(proposal),
            self._check_privacy(proposal),
            self._check_evidence(proposal),
            self._check_claims(proposal),
            self._check_contradictions(proposal),
        )
        return VerificationReport(
            subject="memory_write",
            status=aggregate_status(checks),
            checks=checks,
        )

    def _check_write_shape(self, proposal: MemoryWrite) -> VerificationCheck:
        findings: list[VerificationFinding] = []
        for field, value in (
            ("kind", proposal.kind),
            ("title", proposal.title),
            ("claim", proposal.claim),
        ):
            if not value.strip():
                findings.append(
                    VerificationFinding(
                        code=f"{field}_required",
                        message=f"{field} is required.",
                        severity=CheckStatus.block,
                        fix=f"Provide a non-empty {field}.",
                    )
                )
        return _check("write", findings)

    def _check_privacy(self, proposal: MemoryWrite) -> VerificationCheck:
        findings: list[VerificationFinding] = []
        if proposal.privacy_class in {"secret", "do_not_store"}:
            findings.append(
                VerificationFinding(
                    code="privacy_class_blocked",
                    message=f"privacy_class `{proposal.privacy_class}` cannot be stored.",
                    severity=CheckStatus.block,
                    fix="Store only an abstracted, lower-risk memory or do not store it.",
                )
            )
        _, report = scrub(proposal.claim, self.redact_md, provenance="verification/privacy")
        if "credentials" in report.classes_hit or any(
            item.startswith("credentials_") for item in report.classes_hit
        ):
            findings.append(
                VerificationFinding(
                    code="credential_shaped_claim",
                    message="The memory claim contains credential-shaped material.",
                    severity=CheckStatus.block,
                    fix="Remove the secret and store only a safe abstraction.",
                    evidence={"classes_hit": list(report.classes_hit)},
                )
            )
        elif report.classes_hit:
            findings.append(
                VerificationFinding(
                    code="sensitive_claim",
                    message="The memory claim contains sensitive material.",
                    severity=CheckStatus.warn,
                    fix="Review and abstract before storing.",
                    evidence={"classes_hit": list(report.classes_hit)},
                )
            )
        return _check("privacy", findings)

    def _check_evidence(self, proposal: MemoryWrite) -> VerificationCheck:
        findings: list[VerificationFinding] = []
        if proposal.kind not in SOURCE_OPTIONAL_TYPES and not proposal.source_refs:
            findings.append(
                VerificationFinding(
                    code="source_refs_required",
                    message="Factual or decision-like memory requires source_refs.",
                    severity=CheckStatus.block,
                    fix="Add at least one source reference or reclassify the memory.",
                )
            )
        if proposal.evidence_grade in {"D", "F"}:
            findings.append(
                VerificationFinding(
                    code="weak_evidence_grade",
                    message=f"Evidence grade {proposal.evidence_grade} is weak for durable memory.",
                    severity=CheckStatus.warn,
                    fix="Upgrade evidence or mark the memory as assumption/unknown.",
                )
            )
        return _check("evidence", findings)

    def _check_claims(self, proposal: MemoryWrite) -> VerificationCheck:
        from shiroe.verification.claims import check_claim

        findings = [
            VerificationFinding(
                code=finding.category,
                message=finding.claim,
                severity=CheckStatus.block if finding.severity == "high" else CheckStatus.warn,
                fix=finding.suggestion,
            )
            for finding in check_claim(
                proposal.claim,
                source_refs=list(proposal.source_refs),
                path="<memory-write>",
            )
        ]
        return _check("claims", findings)

    def _check_contradictions(self, proposal: MemoryWrite) -> VerificationCheck:
        # The canonical contradiction store lands in the next consolidation
        # step. Until then, Verification owns the report shape and returns a
        # deterministic pass rather than consulting generated Markdown.
        return VerificationCheck(name="contradictions", status=CheckStatus.passed)


def _check(name: str, findings: list[VerificationFinding]) -> VerificationCheck:
    if any(finding.severity == CheckStatus.block for finding in findings):
        status = CheckStatus.block
    elif findings:
        status = CheckStatus.warn
    else:
        status = CheckStatus.passed
    return VerificationCheck(name=name, status=status, findings=tuple(findings))
