"""Deterministic claim checks used by Verification Engine."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


BLOCKED_PATTERNS = {
    "unsupported_superlative": ["is the best", "best-in-class", "beats every", "beats all"],
    "benchmark_claim": ["10/10 on all benchmarks", "scores 10/10", "leaderboard"],
    "production_ready": ["production-ready", "production proven", "production-proven"],
    "success_without_evidence": ["all gates pass", "all checks pass", "fully verified", "unsupported claim"],
}


@dataclass(frozen=True)
class ClaimFinding:
    path: str
    line: int
    category: str
    severity: str
    claim: str
    suggestion: str


def classify_claim(claim: str, *, source_refs: list[str] | None = None) -> str:
    lowered = claim.lower()
    if matched_claim_category(lowered):
        return "unsupported_claim"
    if "unknown" in lowered:
        return "unknown"
    if any(word in lowered for word in ("assume", "assumption", "likely", "maybe")):
        return "assumption"
    if source_refs:
        return "verified_fact"
    return "user_provided_fact"


def check_claim(
    claim: str,
    *,
    source_refs: list[str] | None = None,
    path: str = "<claim>",
) -> list[ClaimFinding]:
    category = matched_claim_category(claim)
    if category:
        return [
            ClaimFinding(
                path=path,
                line=1,
                category=category,
                severity="high",
                claim=claim,
                suggestion=suggest_rewrite(claim),
            )
        ]
    if classify_claim(claim, source_refs=source_refs) == "user_provided_fact" and _looks_factual(claim):
        return [
            ClaimFinding(
                path=path,
                line=1,
                category="missing_source_ref",
                severity="medium",
                claim=claim,
                suggestion="Add a source reference or reclassify this as an assumption.",
            )
        ]
    return []


def scan_path(path: Path) -> list[ClaimFinding]:
    files = [path] if path.is_file() else sorted(p for p in path.rglob("*.md") if p.is_file())
    findings: list[ClaimFinding] = []
    for file in files:
        for line_no, line in enumerate(file.read_text(errors="ignore").splitlines(), start=1):
            category = matched_claim_category(line)
            if category:
                findings.append(
                    ClaimFinding(
                        path=str(file),
                        line=line_no,
                        category=category,
                        severity="high",
                        claim=line.strip(),
                        suggestion=suggest_rewrite(line),
                    )
                )
    return findings


def matched_claim_category(claim: str) -> str:
    lowered = claim.lower()
    for category, phrases in BLOCKED_PATTERNS.items():
        if any(phrase in lowered for phrase in phrases):
            return category
    return ""


def suggest_rewrite(claim: str) -> str:
    lowered = claim.lower()
    if "best" in lowered or "beats" in lowered:
        return "Use: Shiroe is designed as a local-first memory hardening layer for AI agents."
    if "benchmark" in lowered or "10/10" in lowered or "leaderboard" in lowered:
        return "State benchmark status only with a dated, reproducible source."
    if "production" in lowered:
        return "Use: Shiroe is being hardened for local-first AI memory workflows."
    return "Rewrite as a sourced, bounded claim."


def _looks_factual(claim: str) -> bool:
    lowered = claim.lower()
    return any(token in lowered for token in (" is ", " has ", " supports ", " ships ", " passes "))
