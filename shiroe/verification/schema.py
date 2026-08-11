"""Verification Engine result schema."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CheckStatus(str, Enum):
    passed = "pass"
    warn = "warn"
    block = "block"


@dataclass(frozen=True)
class VerificationFinding:
    code: str = ""
    message: str = ""
    severity: CheckStatus = CheckStatus.warn
    fix: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VerificationCheck:
    name: str
    status: CheckStatus
    findings: tuple[VerificationFinding, ...] = ()
    required: bool = True


@dataclass(frozen=True)
class VerificationReport:
    subject: str
    status: CheckStatus
    checks: tuple[VerificationCheck, ...] = field(default_factory=tuple)


def aggregate_status(checks: tuple[VerificationCheck, ...]) -> CheckStatus:
    required = [check.status for check in checks if check.required]
    if CheckStatus.block in required:
        return CheckStatus.block
    if CheckStatus.warn in required:
        return CheckStatus.warn
    return CheckStatus.passed
