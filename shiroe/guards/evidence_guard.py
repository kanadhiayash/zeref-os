"""EvidenceGuard: evidence quality checks for memory cards and docs."""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from shiroe.core.errors import GuardRejection
from shiroe.core.schema import EVIDENCE_GRADES, SOURCE_OPTIONAL_TYPES, MemoryCard
from shiroe.memory_state import MemoryStore


# SHR-072: negation tokens that indicate a source refutes rather than supports.
_NEGATION_TOKENS = (
    "not ", "no ", "never ", "false", "isn't", "aren't", "wasn't", "weren't",
    "doesn't", "don't", "didn't", "cannot", "can't", "won't",
    "refuted", "contradicts", "disproved", "debunked", "disagrees",
)

# SHR-081: source_ref format is either bare "<ref>" or "<ref>#sha256:<hex>".
_HASH_SUFFIX_RE = re.compile(r"^(?P<ref>.+?)#sha256:(?P<hex>[0-9a-f]{64})$")


def _extract_key_terms(text: str) -> set[str]:
    stopwords = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "of", "in", "on", "at", "to", "for", "with", "by", "from", "as",
        "and", "or", "but", "if", "then", "that", "this", "these", "those",
        "it", "its", "we", "you", "they", "he", "she", "i", "our", "their",
        "not", "no",
    }
    tokens = re.findall(r"[a-z0-9][a-z0-9_-]{2,}", text.lower())
    return {t for t in tokens if t not in stopwords}


def _source_text(source: str) -> str | None:
    ref = source.split("#sha256:", 1)[0]
    if ref.startswith(("http://", "https://")):
        return None
    p = Path(ref)
    if not p.is_file():
        return None
    try:
        if p.stat().st_size > 2 * 1024 * 1024:
            return None
    except OSError:
        return None
    try:
        return p.read_text(errors="ignore")
    except OSError:
        return None


def _hash_source_bytes(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def contradicts_claim(source_text: str, claim: str) -> bool:
    if not source_text or not claim:
        return False
    claim_terms = _extract_key_terms(claim)
    if not claim_terms:
        return False
    lowered = source_text.lower()
    if not any(tok in lowered for tok in _NEGATION_TOKENS):
        return False
    for line in lowered.splitlines():
        if not any(tok in line for tok in _NEGATION_TOKENS):
            continue
        line_terms = _extract_key_terms(line)
        if claim_terms & line_terms:
            return True
    return False


GRADE_DESCRIPTIONS = {
    "A": "Direct primary source, exact, current",
    "B": "Repo file, project doc, or user-confirmed source",
    "C": "User-provided claim, not independently verified",
    "D": "Model inference from partial context",
    "F": "Unsupported, contradicted, or unsafe",
}


@dataclass(frozen=True)
class EvidenceFinding:
    memory_id: str
    severity: str
    reason: str
    fix: str

    def to_dict(self) -> dict:
        return asdict(self)


def grade_text(text: str) -> str:
    lowered = text.lower()
    if any(token in lowered for token in ("source:", "https://", "docs/", "readme.md", "agents.md")):
        return "B"
    if any(token in lowered for token in ("unsupported", "contradicted", "unsafe")):
        return "F"
    if any(token in lowered for token in ("assume", "maybe", "partial context", "inference")):
        return "D"
    return "C"


def check_store(store: MemoryStore) -> list[EvidenceFinding]:
    findings: list[EvidenceFinding] = []
    for card in store.list_cards(limit=1000):
        findings.extend(check_card(card))
    return findings


def check_card(card: MemoryCard) -> list[EvidenceFinding]:
    findings: list[EvidenceFinding] = []
    if card.evidence_grade not in EVIDENCE_GRADES:
        findings.append(EvidenceFinding(card.id, "high", "invalid evidence grade", "Use A, B, C, D, or F."))
    if card.type not in SOURCE_OPTIONAL_TYPES and not card.source_refs:
        findings.append(EvidenceFinding(card.id, "high", "missing source_refs", "Add at least one source reference."))
    if card.evidence_grade in {"D", "F"}:
        findings.append(EvidenceFinding(card.id, "high", f"low evidence grade {card.evidence_grade}", "Upgrade evidence or mark as unknown/assumption."))
    # SHR-081: refs that carry a "#sha256:<hex>" suffix must still match the
    # source file's current content — otherwise the evidence has silently
    # drifted and cannot be used.
    for ref in card.source_refs:
        m = _HASH_SUFFIX_RE.match(ref)
        if m is None:
            continue
        text = _source_text(m.group("ref"))
        if text is None:
            findings.append(EvidenceFinding(
                card.id, "high",
                f"pinned source unavailable: {m.group('ref')}",
                "Restore the source file or re-run upgrade-evidence to re-pin.",
            ))
            continue
        if _hash_source_bytes(text) != m.group("hex"):
            findings.append(EvidenceFinding(
                card.id, "high",
                f"source hash mismatch: {m.group('ref')} (expected {m.group('hex')[:12]}…)",
                "Re-verify the source content and run upgrade-evidence to re-pin.",
            ))
    return findings


def list_by_grade(store: MemoryStore, grade: str) -> list[MemoryCard]:
    return [card for card in store.list_cards(limit=1000) if card.evidence_grade == grade]


def upgrade_evidence(store: MemoryStore, memory_id: str, source: str) -> MemoryCard:
    card = store.get_card(memory_id)
    if card is None:
        raise KeyError(f"memory card {memory_id} not found")
    # SHR-072: refuse a source that contradicts the card's own claim rather
    # than silently upgrading the card's grade on refuting evidence.
    text = _source_text(source)
    if text is not None and contradicts_claim(text, card.claim or card.title):
        raise GuardRejection(
            "EvidenceGuard",
            f"source {source!r} contradicts card {memory_id} claim",
            "Provide a source that supports the claim, or open a contradiction "
            "card instead of upgrading.",
        )
    # SHR-081: when the source resolves to a real file, pin its current hash
    # into the ref so later reads can detect drift. URLs / bare descriptors
    # remain unpinned — provenance work for a follow-up PR.
    ref_to_store = source
    if text is not None and "#sha256:" not in source:
        ref_to_store = f"{source}#sha256:{_hash_source_bytes(text)}"
    data = card.to_dict()
    refs = list(dict.fromkeys([*card.source_refs, ref_to_store]))
    data["source_refs"] = refs
    data["evidence_grade"] = "B"
    updated = MemoryCard.from_dict(data)
    with store._connect() as conn:  # internal helper until card update API grows
        store._replace_card(conn, updated)
        conn.commit()
    store.record_event(event="memory-card-evidence-upgrade", payload={"id": memory_id, "source": ref_to_store})
    return updated


def report_findings(findings: list[EvidenceFinding]) -> str:
    if not findings:
        return "No EvidenceGuard findings.\n"
    return "\n".join(f"{f.severity.upper()} {f.memory_id} {f.reason} Fix: {f.fix}" for f in findings) + "\n"


def check_public_docs(path: Path) -> list[str]:
    issues: list[str] = []
    files = [path] if path.is_file() else sorted(path.rglob("*.md"))
    for file in files:
        for line in file.read_text(errors="ignore").splitlines():
            lowered = line.lower()
            if ("best-in-class" in lowered or "scores 10/10 on all benchmarks" in lowered) and not _negated_example(lowered):
                issues.append(f"{file}: unsupported public claim")
            if "evidence grade: f" in lowered and not _negated_example(lowered):
                issues.append(f"{file}: grade F public claim")
    return issues


def _negated_example(line: str) -> bool:
    return any(token in line for token in ("avoid", "do not", "without", "unsupported", "forbidden", "blocked", "claims"))
