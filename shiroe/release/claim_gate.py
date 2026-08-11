"""External benchmark truth gate (SHR-66 / issue #172).

privacy-audit: allow-file "Claim-gate module names evidence classes + example
claim patterns as spec; no user data."

Two things live here:

1. **Capability evidence matrix** (`build_capability_matrix`) — every
   capability the project could make a public claim about, graded on two
   independent axes:

   - namespace: what kind of check produced the evidence —
     `conformance | integration | performance | external_benchmark | security_review`
   - evidence_tier: how it was validated —
     `fixture_tested` (only against fixtures/corpora authored alongside the
     code — self-consistency, not generalization) or `external_tested`
     (against an independently-sourced or held-out dataset)

   Combined with `maturity` (`runtime | contract | experimental`), each
   entry carries `public_claim_allowed`. A self-check must never be allowed
   to imply the same trust level as an externally-tested result.

2. **Public-claim scanner** (`scan_public_claims`) — greps README.md and
   docs/*.md for three specific claim shapes this program flagged as
   currently unsupported, and blocks them:

   a. Routing-accuracy / CRITICAL-recall claims. PR3's 48-entry corpus and
      the classifier were authored together (see
      tests/test_routing_classifier.py's own docstring) — that is
      fixture-coverage, not a generalization claim, until a held-out or
      independently-labeled corpus exists.
   b. Comparative ranking claims resting on contested vendor LoCoMo figures
      (Zep/Mem0 have each publicly revised their own numbers), and any
      Shiroe benchmark number published without both a full-context baseline
      and a lexical baseline alongside it.
   c. External-benchmark score claims before any dataset run is on record —
      "explicitly unscored" is the correct posture until one exists.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from shiroe.compat.legacy_identity import LEGACY_PRODUCT_NAME

NAMESPACES = ("conformance", "integration", "performance", "external_benchmark", "security_review")
EVIDENCE_TIERS = ("fixture_tested", "external_tested")
MATURITIES = ("runtime", "contract", "experimental")

_EXTERNAL_BENCHMARK_NAMES = ("locomo", "longmemeval", "convomem", "personamem", "ruler", "helmet")


@dataclass(frozen=True)
class CapabilityEvidence:
    capability: str
    namespace: str
    maturity: str
    evidence_tier: str
    public_claim_allowed: bool
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


def _routing_classifier_entry() -> CapabilityEvidence:
    return CapabilityEvidence(
        capability="routing_criticality_classifier",
        namespace="conformance",
        maturity="runtime",
        evidence_tier="fixture_tested",
        public_claim_allowed=False,
        reason=(
            "tests/test_routing_classifier.py documents that the 48-entry "
            "corpus and the classifier rules were authored together, so "
            "agreement on this corpus is expected by construction, not a "
            "generalization result. No held-out or independently-labeled "
            "corpus exists yet."
        ),
    )


def _external_benchmark_entries() -> list[CapabilityEvidence]:
    return [
        CapabilityEvidence(
            capability=f"external_benchmark_{name}",
            namespace="external_benchmark",
            maturity="experimental",
            evidence_tier="fixture_tested",
            public_claim_allowed=False,
            reason=(
                f"benchmarks/external/loaders/{name}.py + harness.py validate "
                "the dataset format, but no full-dataset run (dry_run or "
                "live) is on record under benchmarks/external/results/. "
                "'Explicitly unscored' is the correct public posture."
            ),
        )
        for name in _EXTERNAL_BENCHMARK_NAMES
    ]


def _registry_capabilities(root: Path) -> list[CapabilityEvidence]:
    reg_path = root / "shiroe-registry.json"
    if not reg_path.exists():
        return []
    reg = json.loads(reg_path.read_text(encoding="utf-8"))
    tests_dir = root / "tests"
    test_stems = {p.stem for p in tests_dir.glob("test_*.py")} if tests_dir.is_dir() else set()
    out: list[CapabilityEvidence] = []

    for gate in reg.get("gates", []):
        name = gate["gate"]
        key = name.replace("-", "_")
        short = key.replace("_guard", "")
        tested = any(key in stem or short in stem for stem in test_stems)
        out.append(CapabilityEvidence(
            capability=f"gate:{name}",
            namespace="security_review" if "privacy" in key or "guard" in key else "conformance",
            maturity="runtime",
            evidence_tier="fixture_tested",
            public_claim_allowed=tested,
            reason=(f"local pytest coverage found for {key}" if tested
                    else f"no tests/test_*{key}* found — contract only"),
        ))

    for skill in reg.get("skills", []):
        status = skill.get("status", "contract")
        out.append(CapabilityEvidence(
            capability=f"skill:{skill['skill']}",
            namespace="integration",
            maturity="runtime" if status == "runtime" else "contract",
            evidence_tier="fixture_tested",
            public_claim_allowed=(status == "runtime"),
            reason=f"registry status={status}",
        ))

    for agent in reg.get("agents", []):
        status = agent.get("status", "contract")
        runtime_backed = bool(agent.get("runtime_backed", False))
        out.append(CapabilityEvidence(
            capability=f"agent:{agent['agent']}",
            namespace="integration",
            maturity="runtime" if runtime_backed else "contract",
            evidence_tier="fixture_tested",
            public_claim_allowed=runtime_backed,
            reason=f"registry status={status}, runtime_backed={runtime_backed}",
        ))

    return out


def build_capability_matrix(root: Path) -> list[CapabilityEvidence]:
    """Evidence class for every capability the project could make a public
    claim about. Registry-declared gates/skills/agents are graded from
    shiroe-registry.json cross-referenced with tests/; the routing classifier
    and external-benchmark entries are hand-graded because their evidence
    class depends on provenance facts (who authored the test corpus, whether
    a dataset run has ever completed) that a registry entry can't express.
    """
    out = [_routing_classifier_entry(), *_external_benchmark_entries()]
    out.extend(_registry_capabilities(root))
    return sorted(out, key=lambda c: c.capability)


def format_matrix(entries: list[CapabilityEvidence], *, format: str = "text") -> str:
    if format == "json":
        return json.dumps([e.to_dict() for e in entries], indent=2, sort_keys=True) + "\n"
    lines = []
    for e in entries:
        badge = "CLAIM-OK " if e.public_claim_allowed else "NO-CLAIM"
        lines.append(
            f"{badge} {e.capability:<45} ns={e.namespace:<18} "
            f"maturity={e.maturity:<12} tier={e.evidence_tier}"
        )
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Public-claim scanner
# ---------------------------------------------------------------------------

_ROUTING_CLAIM_RE = re.compile(
    r"critical recall|routing accuracy|100%\s*(critical\s+)?recall|recall[:\s]+1\.0+\b",
    re.IGNORECASE,
)
_VENDOR_NAMES = ("zep", "mem0", "locomo")
# Both product names. The rename to Shiroe does not retire the old one from
# the corpus this gate reads: docs still in flight, archived reports, and any
# third-party copy all say "Shiroe". A gate that stopped matching the former
# name would quietly let a Shiroe-attributed overclaim through.
_PRODUCT_NAMES = ("shiroe", LEGACY_PRODUCT_NAME)
_COMPARISON_WORDS = (
    "beats", "outperform", "better than", " vs ", " vs. ", "ranked #",
    "wins over", "surpasses", "ahead of",
)
_FULL_CONTEXT_TERMS = ("full-context baseline", "full context baseline")
_LEXICAL_TERMS = ("lexical baseline", "grep baseline")
_SCORE_RE = re.compile(r"\b\d{1,3}(?:\.\d+)?\s*%")
_UNSCORED_DISCLAIMER_MARKERS = (
    "no scores exist", "no dataset runs", "unscored", "no external benchmark",
    "no score", "explicitly unscored",
)
# (d) issue #153 gap: a generic "we're the best" claim needs no vendor name
# and no percentage to be a problem — a model-comparison doc under references/
# carried exactly this shape ("Best-in-class", "Strongest differentiator vs.
# comparable systems") for a long time, unevidenced, unseen because
# references/ was never scanned. Phrases here are drawn directly from the
# project's own banned-wording lists (docs/PUBLIC_SURFACE.md's "Not allowed"
# row, CONTRIBUTING.md, docs/RELEASE_PROCESS.md) plus the real phrasing that
# shipped. The owner's rule is unconditional: no claim of "best" or any
# roundabout superiority claim may ship without a public benchmark behind it,
# and none exists yet (see _external_benchmark_has_run).
_SUPERIORITY_PHRASES = (
    "best-in-class", "best in class", "world top", "world best", "world's best",
    "worlds best", "top ranked", "top-ranked", "10/10", "production-grade",
    "production grade", "production secure", "secure by default",
    "strongest differentiator",
)


@dataclass(frozen=True)
class ClaimFinding:
    path: str
    line: int
    constraint: str
    excerpt: str
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


# Directory names whose contents are frozen records, matched on any path
# segment. See _public_docs.__doc__ for why each one is here.
_EXCLUDED_PARTS = frozenset({"_evidence", "_research", "adr", "release-evidence", "v4x-canon"})


def _public_docs(root: Path) -> list[Path]:
    """Every file a visitor can read before cloning or installing Shiroe.

    issue #172 originally covered README.md + docs/*.md. That missed two real
    gaps:

    - `references/` was never scanned at all. An unevidenced self-rating
      table sat in a model-comparison doc there for a long time, claiming
      "Best-in-class" and "Strongest differentiator" with no benchmark behind
      either — the gate never saw it because it lives under references/. That
      table is gone now, but the blind spot was real.
    - SECURITY.md, CONTRIBUTING.md and AGENTS.md are named as "primary
      surfaces" in docs/PUBLIC_SURFACE.md itself, yet were never scanned.

    Excluded on purpose, not silently skipped:
    - docs/_evidence/, docs/_research/ — internal working notes, not public.
    - docs/adr/, docs/audits/release-evidence/, and the archived v4.x canon
      bundle under references/ — frozen historical records (architecture
      decisions, dated release-evidence blobs, and superseded canon, each
      carrying its own banner saying so). Editing history to satisfy a gate
      would falsify the record, so these paths are excluded from scanning
      rather than ever being hand-edited to pass. SHR-027: the gate derives
      no behaviour from an archived surface.
    - CHANGELOG.md — historical by definition; was never scanned and stays
      that way for the same reason.
    """
    out = []
    for name in ("README.md", "SECURITY.md", "CONTRIBUTING.md", "AGENTS.md"):
        candidate = root / name
        if candidate.exists():
            out.append(candidate)

    def _walk(base: Path) -> list[Path]:
        if not base.is_dir():
            return []
        return [
            p for p in sorted(base.rglob("*.md"))
            if not (_EXCLUDED_PARTS & set(p.parts))
        ]

    out.extend(_walk(root / "docs"))
    out.extend(_walk(root / "references"))
    return out


def _external_benchmark_has_run(root: Path) -> bool:
    results_dir = root / "benchmarks" / "external" / "results"
    return results_dir.is_dir() and any(results_dir.glob("*.json"))


def scan_public_claims(root: Path) -> list[ClaimFinding]:
    """Scan public docs for the three blocked claim shapes. Returns every
    hit; an empty list means the current public surface is clean."""
    findings: list[ClaimFinding] = []
    ran = _external_benchmark_has_run(root)

    for path in _public_docs(root):
        text = path.read_text(errors="ignore")
        rel = str(path.relative_to(root))
        for lineno, line in enumerate(text.splitlines(), start=1):
            lowered = line.lower()

            # (a) routing accuracy / CRITICAL recall
            if _ROUTING_CLAIM_RE.search(line):
                findings.append(ClaimFinding(
                    path=rel, line=lineno,
                    constraint="routing_accuracy_fixture_coverage",
                    excerpt=line.strip(),
                    reason=(
                        "routing classifier evidence is fixture-coverage "
                        "(self-consistency by construction, not generalization) "
                        "— no held-out corpus exists; this claim is blocked"
                    ),
                ))

            # (b1) contested vendor comparative ranking — only when Shiroe is
            # the subject of the comparison. Citing a vendor's own published
            # figures for context (e.g. justifying why a baseline is
            # required) is not Shiroe making a ranking claim; require a product name
            # on the line so the gate targets the claim, not the citation.
            if any(p in lowered for p in _PRODUCT_NAMES) and any(v in lowered for v in _VENDOR_NAMES) and any(
                c in lowered for c in _COMPARISON_WORDS
            ):
                findings.append(ClaimFinding(
                    path=rel, line=lineno,
                    constraint="contested_vendor_comparison",
                    excerpt=line.strip(),
                    reason=(
                        "comparative ranking claim rests on publicly disputed "
                        "vendor LoCoMo figures (vendors have each issued "
                        "double-digit self-corrections) — blocked"
                    ),
                ))

            # (b2) a Shiroe benchmark number without both required baselines
            if any(p in lowered for p in _PRODUCT_NAMES) and _SCORE_RE.search(line) and (
                "locomo" in lowered or "benchmark" in lowered or "memory accuracy" in lowered
            ):
                doc_lower = text.lower()
                has_full_context = any(t in doc_lower for t in _FULL_CONTEXT_TERMS)
                has_lexical = any(t in doc_lower for t in _LEXICAL_TERMS)
                if not (has_full_context and has_lexical):
                    findings.append(ClaimFinding(
                        path=rel, line=lineno,
                        constraint="missing_baseline_pair",
                        excerpt=line.strip(),
                        reason=(
                            "a Shiroe benchmark number appears without both a "
                            "full-context baseline and a lexical baseline in "
                            "the same document — published evidence shows "
                            "plain full-context beats purpose-built memory "
                            "products at small-to-medium context lengths, so "
                            "omitting baselines risks an implied win over a "
                            "floor a no-memory system already clears"
                        ),
                    ))

            # (c) external benchmark score claimed with no run on record
            if not ran and _SCORE_RE.search(line) and any(name in lowered for name in _EXTERNAL_BENCHMARK_NAMES):
                if not any(marker in lowered for marker in _UNSCORED_DISCLAIMER_MARKERS):
                    findings.append(ClaimFinding(
                        path=rel, line=lineno,
                        constraint="unscored_external_benchmark",
                        excerpt=line.strip(),
                        reason=(
                            "no external benchmark run is on record under "
                            "benchmarks/external/results/ — 'explicitly "
                            "unscored' is the only correct public posture"
                        ),
                    ))

            # (d) generic superiority claim ("best", "world top", "10/10", ...)
            # about the product, with no public benchmark behind it. Requires
            # a product name on the line — same guard as (b1)/(b2) — so this
            # does not trip on CONTRIBUTING.md / docs/RELEASE_PROCESS.md /
            # docs/PUBLIC_SURFACE.md, which list these exact phrases as
            # banned wording rather than making the claim.
            if any(p in lowered for p in _PRODUCT_NAMES) and any(
                s in lowered for s in _SUPERIORITY_PHRASES
            ):
                findings.append(ClaimFinding(
                    path=rel, line=lineno,
                    constraint="unverified_superiority_claim",
                    excerpt=line.strip(),
                    reason=(
                        "roundabout claim of superiority ('best', 'world "
                        "top', '10/10', 'production-grade', ...) with no "
                        "public benchmark-verified result behind it — "
                        "docs/PUBLIC_SURFACE.md bans this wording outright, "
                        "regardless of which surface it appears on"
                    ),
                ))

    return findings


def run_claim_gate(root: Path) -> tuple[bool, list[ClaimFinding]]:
    findings = scan_public_claims(root)
    return (len(findings) == 0, findings)


def format_findings(findings: list[ClaimFinding]) -> str:
    if not findings:
        return "No claim-gate findings.\n"
    lines = [
        f"BLOCK {f.constraint} {f.path}:{f.line} — {f.excerpt}\n       {f.reason}"
        for f in findings
    ]
    return "\n".join(lines) + "\n"
