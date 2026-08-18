#!/usr/bin/env python3
"""
check-canon-consistency.py — Audit-only canon consistency gate (SHR-003..SHR-006).

This script DETECTS canon contradictions. It never fixes them. Every finding it
reports must either be absent from the tree or acknowledged, with an owner and a
resolving PR, in docs/canon/canon-baseline.json.

Inputs (all under docs/canon/, all hand-maintained):
    SOURCE_AUTHORITY.md      the precedence map, in one tagged fenced JSON block
    canon-baseline.json      the acknowledged-findings ledger
    PUBLIC_CLAIM_LEDGER.json numeric public claims + how to recompute each one

What is checked:

SHR-003 — source authority
    * the authority map parses and its tier ranks are unique and contiguous 1..N
    * every tier/archived glob matches at least one file (no dead globs)
    * no file is claimed by two different ranks (no ambiguous authority)
    * every non-pruned file is active, archived, or explicitly unscoped
    * every conflict_rules[].authority exists and is an Accepted ADR

SHR-004 — canon conflicts
    Sentence-bounded prose scan over ACTIVE surfaces only, so superseded prose
    under an archived glob stays silent while accepted ADRs stay authoritative.
    Also: archived surfaces must carry their marker, and active surfaces must not
    cite an archived directory as if it were live.

SHR-005 — component status labels
    Active only while the contract registry exists. Phase 01 intentionally
    removes shiroe-registry.json and its schema, so absence of both surfaces
    is a clean no-op rather than an input error.

SHR-006 — public claim ledger
    Numeric and count claims only. Machine-verified claims are recomputed with
    pure-stdlib verifiers and compared against the recorded evidence value.
    Reverse drift: any numeric claim shape found in README.md or AGENTS.md that
    has no ledger entry is a finding. Prose claims are NOT handled here — they
    remain the job of shiroe/release/claim_gate.py, which this script does not
    duplicate.

Finding identity is (surface, rule), rendered "<surface>::<rule>". It is
deliberately not a line number and not a content hash, so that reflowing a
paragraph does not invent a new finding. Multiplicity is carried in `count` and
is drift-checked.

Exit codes:
    0  clean — observed findings exactly match the baseline
    1  drift — a new, dropped, regressed, or miscounted finding
    2  the checker's own inputs are missing or malformed, an acknowledgement in
       the baseline is anonymous (no owner / resolving_pr / why_open), a data
       file names a path outside --root, or the audit outran its time budget

Availability is part of the contract. The inputs are data files, and data must
not be able to stop the gate: a ledger-supplied regex is compiled and run per
file, a surface may be a symlink or FIFO, and a glob may be superlinear. Reads
are restricted to regular files inside --root, and the whole run is bounded by
CANON_AUDIT_BUDGET_S (default 30s against a ~0.2s real-tree runtime).

Usage:
    python3 scripts/check-canon-consistency.py [--root <repo-root>]

--root is required by design (not merely convenient): the synthetic-tree tests in
tests/test_canon_consistency.py point it at a tmp_path repo to prove each
detector actually fires.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import stat
import sys
from functools import lru_cache
from pathlib import Path

AUTHORITY_REL = "docs/canon/SOURCE_AUTHORITY.md"
BASELINE_REL = "docs/canon/canon-baseline.json"
LEDGER_REL = "docs/canon/PUBLIC_CLAIM_LEDGER.json"
REGISTRY_REL = "shiroe-registry.json"
SCHEMA_REL = "registry/shiroe-registry.schema.json"

AUTHORITY_SCHEMA = "shiroe.source-authority/v1"
BASELINE_SCHEMA = "shiroe.canon-baseline/v1"
LEDGER_SCHEMA = "shiroe.public-claim-ledger/v1"

# Keyed on the fence tag, not on "the first json block" — SOURCE_AUTHORITY.md is
# prose first and may grow illustrative JSON examples later.
AUTHORITY_BLOCK_RE = re.compile(
    r"```json\s+" + re.escape(AUTHORITY_SCHEMA) + r"\s*\n(.*?)\n```",
    re.DOTALL,
)

# Directories that are never canon surfaces and are expensive to walk.
PRUNE_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    "htmlcov", ".pytest_cache", "build", "dist", ".claude",
}

BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".sqlite", ".db", ".parquet", ".pyc"}
MAX_SCAN_BYTES = 2 * 1024 * 1024

# Wall-clock ceiling for the whole audit. The real tree finishes in ~0.2s, so 30s
# is ~150x headroom and only a runaway can reach it. Overridable so the
# denial-of-service tests do not have to burn the full budget to prove a point.
CANON_AUDIT_BUDGET_S = float(os.environ.get("CANON_AUDIT_BUDGET_S", "30"))

# A quantified group that is itself quantified — (a+)+, (a*)*, (?:a|a){2,} — is
# the shape that backtracks exponentially when the match fails. This is a
# DIAGNOSTIC that names the offending claim, never the guard: regex safety is not
# statically decidable, and the watchdog is what actually bounds the damage.
NESTED_QUANTIFIER_RE = re.compile(r"\)[*+{]")

ACKNOWLEDGED_STATUSES = {"acknowledged", "wontfix"}
BASELINE_STATUSES = ACKNOWLEDGED_STATUSES | {"resolved"}


class InputError(Exception):
    """The checker's own inputs are missing or malformed — exit 2."""


def install_watchdog() -> None:
    """
    Bound the audit's wall clock, so no input can stop the gate by running long.

    `verify.pattern` is attacker-supplied data compiled and run per file, and a
    nested quantifier backtracks exponentially — 40 bytes of input outlasts any
    CI job. Pattern-length caps and `(?m)^` anchoring were both measured against
    it and both fail (an 11-character anchored pattern hangs just as hard), and
    anchoring would additionally break a shipped verified claim. So the boundary
    is time, not pattern shape: it needs no prediction about which regexes are
    dangerous, and it covers the superlinear `**/` glob case for free.

    CPython's regex loop polls signals, so SIGALRM interrupts a running findall
    rather than waiting for it to finish.

    Ceiling: SIGALRM is POSIX and main-thread only. CI is ubuntu-latest, so this
    always arms there; on a hypothetical Windows runner it becomes a no-op and
    the denial-of-service exposure returns silently.
    """
    if not hasattr(signal, "SIGALRM"):
        return

    def _expired(_signum: int, _frame: object) -> None:
        raise InputError(
            f"canon audit exceeded its {CANON_AUDIT_BUDGET_S:g}s budget — a "
            f"ledger-supplied regex or an authority-map glob is not terminating"
        )

    signal.signal(signal.SIGALRM, _expired)
    signal.setitimer(signal.ITIMER_REAL, CANON_AUDIT_BUDGET_S)


def cancel_watchdog() -> None:
    if hasattr(signal, "SIGALRM"):
        signal.setitimer(signal.ITIMER_REAL, 0)


# --------------------------------------------------------------------------- #
# Glob matching
# --------------------------------------------------------------------------- #


@lru_cache(maxsize=None)
def _glob_re(glob: str) -> re.Pattern[str]:
    """
    Compile one POSIX-relative path glob, once.

    Deliberately not fnmatch.translate: fnmatch's `*` crosses `/`, which would
    make the non-recursive `docs/*.md` swallow `docs/adr/*.md` and `docs/wiki/**`
    and report ambiguous authority everywhere. Here `*` and `?` stop at `/`,
    `**/` spans zero or more directories, and a trailing `**` spans everything.
    """
    out: list[str] = []
    i, n = 0, len(glob)
    while i < n:
        if glob.startswith("**/", i):
            out.append("(?:[^/]+/)*")
            i += 3
        elif glob.startswith("**", i):
            out.append(".*")
            i += 2
        elif glob[i] == "*":
            out.append("[^/]*")
            i += 1
        elif glob[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(glob[i]))
            i += 1
    return re.compile("".join(out) + r"\Z")


def _matches(glob: str, rel: str) -> bool:
    return _glob_re(glob).match(rel) is not None


def _literal_dir_prefix(glob: str) -> str | None:
    """Return a literal directory prefix for an archive glob, or None for a file."""
    head = glob.split("*", 1)[0].split("?", 1)[0]
    return head if head.endswith("/") else None


def walk_files(root: Path) -> list[str]:
    """Every non-pruned file, as a POSIX repo-relative path. Never shells out to git."""
    found: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames
            if d not in PRUNE_DIRS and not d.endswith(".egg-info")
        ]
        for name in filenames:
            if name in PRUNE_DIRS:  # in a worktree, `.git` is a file, not a directory
                continue
            found.append(Path(dirpath, name).relative_to(root).as_posix())
    return sorted(found)


def is_regular_file(path: Path) -> bool:
    """
    True only for a real file, following no symlink.

    `stat()` follows symlinks and reports st_size 0 for a character device, so
    `x.md -> /dev/zero` cleared the MAX_SCAN_BYTES gate below and was then read
    until memory ran out; a FIFO never returns from open() at all. `lstat` plus
    S_ISREG closes symlink, FIFO, device and socket in one call, and reports the
    honest size of the entry itself.
    """
    try:
        return stat.S_ISREG(path.lstat().st_mode)
    except OSError:
        return False


def read_text(root: Path, rel: str) -> str | None:
    """Text content, or None for non-regular / binary / oversized files."""
    path = root / rel
    if path.suffix.lower() in BINARY_SUFFIXES:
        return None
    if not is_regular_file(path):
        return None
    try:
        if path.lstat().st_size > MAX_SCAN_BYTES:
            return None
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


# --------------------------------------------------------------------------- #
# Findings
# --------------------------------------------------------------------------- #


class Finding:
    __slots__ = ("surface", "rule", "shr", "count", "excerpt", "hits")

    def __init__(
        self,
        surface: str,
        rule: str,
        shr: str,
        count: int = 1,
        excerpt: str = "",
        hits: tuple[str, ...] = (),
    ) -> None:
        self.surface = surface
        self.rule = rule
        self.shr = shr
        self.count = count
        self.excerpt = excerpt
        # The matched text, when the detector can supply it. Feeds `digest`.
        self.hits = tuple(hits)

    @property
    def id(self) -> str:
        return f"{self.surface}::{self.rule}"

    @property
    def digest(self) -> str:
        """
        Fingerprint of WHAT was matched, not how many times.

        Identity is (surface, rule) and drift was `count` alone, so swapping an
        acknowledged contradiction for a *different* one of the same rule on the
        same surface kept count at 1 and stayed [KNOWN]. Every acknowledgement
        was a laundering slot. Empty when the detector supplies no hits, in which
        case reconcile falls back to the count comparison.
        """
        if not self.hits:
            return ""
        return hashlib.sha256("\n".join(sorted(self.hits)).encode("utf-8")).hexdigest()[:12]


# --------------------------------------------------------------------------- #
# Inputs
# --------------------------------------------------------------------------- #


def load_authority_map(root: Path) -> dict:
    path = root / AUTHORITY_REL
    if not path.exists():
        raise InputError(f"authority map missing: {AUTHORITY_REL}")
    blocks = AUTHORITY_BLOCK_RE.findall(path.read_text(encoding="utf-8"))
    if len(blocks) != 1:
        raise InputError(
            f"{AUTHORITY_REL} must carry exactly one ```json {AUTHORITY_SCHEMA} "
            f"block, found {len(blocks)}"
        )
    try:
        amap = json.loads(blocks[0])
    except json.JSONDecodeError as exc:
        raise InputError(f"{AUTHORITY_REL} authority block is not valid JSON: {exc}") from exc

    if amap.get("schema") != AUTHORITY_SCHEMA:
        raise InputError(f"{AUTHORITY_REL}: schema must be {AUTHORITY_SCHEMA!r}")
    for key in ("tiers", "archived", "unscoped", "conflict_rules"):
        if key not in amap:
            raise InputError(f"{AUTHORITY_REL}: missing required key {key!r}")

    # An archived entry silences its files from the conflict scan, and
    # check_archived_files_marked skips any entry that carries no marker. So a
    # markerless archived entry is a scope hole with nothing to review: it looks
    # exactly like the two legitimate ones already in the map. Demand a marker or
    # a written reason — the attacker must then either stamp a visible lie into
    # the file or write one into the map, next to honest entries for comparison.
    #
    # Deliberately not a *finding*: that would mean baselining the two legitimate
    # entries, rebuilding the laundering slot that finding digests exist to close.
    for entry in amap["archived"]:
        if not entry.get("marker") and not entry.get("why_no_marker"):
            raise InputError(
                f"{AUTHORITY_REL}: archived entry {entry.get('id')!r} carries neither "
                f"'marker' nor 'why_no_marker' — an unmarked archived surface reads as live"
            )

    ranks = [t["rank"] for t in amap["tiers"]]
    if len(ranks) != len(set(ranks)):
        raise InputError(f"{AUTHORITY_REL}: tier ranks are not unique: {ranks}")
    if sorted(ranks) != list(range(1, len(ranks) + 1)):
        raise InputError(f"{AUTHORITY_REL}: tier ranks must be contiguous 1..N, got {sorted(ranks)}")
    return amap


def load_baseline(root: Path) -> dict[str, dict]:
    path = root / BASELINE_REL
    if not path.exists():
        raise InputError(f"baseline missing: {BASELINE_REL}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InputError(f"{BASELINE_REL} is not valid JSON: {exc}") from exc
    if data.get("schema") != BASELINE_SCHEMA:
        raise InputError(f"{BASELINE_REL}: schema must be {BASELINE_SCHEMA!r}")

    by_id: dict[str, dict] = {}
    for entry in data.get("findings", []):
        fid = entry.get("id")
        if not fid:
            raise InputError(f"{BASELINE_REL}: a finding has no id")
        if fid in by_id:
            raise InputError(f"{BASELINE_REL}: duplicate finding id {fid!r}")
        status = entry.get("status")
        if status not in BASELINE_STATUSES:
            raise InputError(f"{BASELINE_REL}: finding {fid!r} has invalid status {status!r}")
        if status in ACKNOWLEDGED_STATUSES:
            for field in ("owner", "resolving_pr", "why_open"):
                if not entry.get(field):
                    raise InputError(
                        f"{BASELINE_REL}: anonymous acknowledgement {fid!r} — missing {field!r}"
                    )
        by_id[fid] = entry
    data["_by_id"] = by_id
    return data


def load_ledger(root: Path) -> dict:
    path = root / LEDGER_REL
    if not path.exists():
        raise InputError(f"public claim ledger missing: {LEDGER_REL}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InputError(f"{LEDGER_REL} is not valid JSON: {exc}") from exc
    if data.get("schema") != LEDGER_SCHEMA:
        raise InputError(f"{LEDGER_REL}: schema must be {LEDGER_SCHEMA!r}")

    seen: set[str] = set()
    for claim in data.get("claims", []):
        cid = claim.get("id")
        if not cid:
            raise InputError(f"{LEDGER_REL}: a claim has no id")
        if cid in seen:
            raise InputError(f"{LEDGER_REL}: duplicate claim id {cid!r}")
        seen.add(cid)
        # A claim whitelists every numeric phrase its `claim` string contains
        # (check_unledgered_claims does a substring match), so one without any
        # evidence handle can silence a whole surface while looking verified.
        # tests/test_canon_consistency.py already asserted this; the checker's
        # own contract was the weaker of the two.
        if not any(k in claim for k in ("verify", "evidence_command", "evidence_path")):
            raise InputError(f"{LEDGER_REL}: claim {cid!r} carries no evidence handle")
        if claim.get("status") != "verified":
            for field in ("owner", "resolving_pr", "why_unverified"):
                if not claim.get(field):
                    raise InputError(
                        f"{LEDGER_REL}: non-verified claim {cid!r} is anonymous — missing {field!r}"
                    )
    return data


def head_commit(root: Path) -> str | None:
    """Best-effort HEAD sha from .git, stdlib only. Never shells out."""
    try:
        dot_git = root / ".git"
        if dot_git.is_file():  # worktree / submodule pointer
            gitdir = dot_git.read_text(encoding="utf-8").split("gitdir:", 1)[1].strip()
            dot_git = Path(gitdir)
            if not dot_git.is_absolute():
                dot_git = (root / dot_git).resolve()
        head = (dot_git / "HEAD").read_text(encoding="utf-8").strip()
        if not head.startswith("ref:"):
            return head
        ref = head.split(":", 1)[1].strip()
        for base in (dot_git, dot_git.parent.parent if dot_git.name != ".git" else dot_git):
            candidate = base / ref
            if candidate.exists():
                return candidate.read_text(encoding="utf-8").strip()
        for line in (dot_git / "packed-refs").read_text(encoding="utf-8").splitlines():
            if line.endswith(" " + ref):
                return line.split(" ", 1)[0]
    except (OSError, IndexError, UnicodeDecodeError):
        pass
    return None


# --------------------------------------------------------------------------- #
# SHR-003 — source authority
# --------------------------------------------------------------------------- #


class Classification:
    def __init__(self) -> None:
        self.active: dict[str, tuple[int, str]] = {}  # rel -> (rank, tier id)
        self.archived: dict[str, str] = {}            # rel -> archived entry id
        self.unscoped: set[str] = set()
        self.unclassified: list[str] = []
        self.excluded: set[str] = set()  # carved out of a tier by an `exclude` glob


def classify(amap: dict, files: list[str]) -> tuple[Classification, list[Finding]]:
    findings: list[Finding] = []
    result = Classification()
    used_globs: set[str] = set()

    def _claimed(entry: dict, rel: str) -> list[str]:
        """
        Every glob in this tier/archived entry that claims `rel`.

        The optional `exclude` list carves a more specific tier out of a broader
        one without either having to enumerate files: `docs/*.md` is narrative
        prose *except* `docs/GLOSSARY.md`, which is rank 4. Globs cannot express
        negation, and hand-listing every narrative doc would rot on the first
        new file. Returning all matching globs, not just the first, is what
        keeps the dead-glob check honest.
        """
        if any(_matches(glob, rel) for glob in entry.get("exclude", ())):
            if any(_matches(glob, rel) for glob in entry["paths"]):
                result.excluded.add(rel)  # would have been claimed but for the exclude
            return []
        return [glob for glob in entry["paths"] if _matches(glob, rel)]

    for rel in files:
        hits: list[tuple[int, str]] = []  # (rank, tier id)
        for tier in amap["tiers"]:
            claimed = _claimed(tier, rel)
            if claimed:
                hits.append((tier["rank"], tier["id"]))
                used_globs.update(claimed)

        if hits:
            if len({r for r, _ in hits}) > 1:
                owners = ", ".join(f"{tid}(rank {r})" for r, tid in sorted(hits))
                findings.append(
                    Finding(rel, "ambiguous-authority", "SHR-003", excerpt=f"claimed by {owners}")
                )
            result.active[rel] = min(hits)
            continue

        archived_id = None
        for entry in amap["archived"]:
            claimed = _claimed(entry, rel)
            if claimed:
                archived_id = entry["id"]
                used_globs.update(claimed)
        if archived_id:
            result.archived[rel] = archived_id
            continue

        matched_unscoped = [glob for glob in amap["unscoped"] if _matches(glob, rel)]
        if matched_unscoped:
            result.unscoped.add(rel)
            used_globs.update(matched_unscoped)
            if rel in result.excluded:
                # `unscoped` is exempt from the dead-glob check, so a tier
                # `exclude` plus a covering unscoped glob drops a live surface
                # out of every scan and leaves no unused glob behind to notice.
                # Excluding into another tier is the intended use and stays quiet.
                findings.append(
                    Finding(rel, "excluded-into-unscoped", "SHR-003",
                            excerpt="carved out of its tier, then absorbed by an unscoped glob")
                )
            continue

        result.unclassified.append(rel)
        findings.append(Finding(rel, "unclassified-surface", "SHR-003"))

    # Dead globs — tiers and archived only. Unscoped is an explicit escape hatch
    # and is allowed to over-declare so that new directories land softly.
    for tier in amap["tiers"]:
        for glob in tier["paths"]:
            if glob not in used_globs:
                findings.append(
                    Finding(glob, "dead-glob", "SHR-003", excerpt=f"tier {tier['id']} matches no file")
                )
    for entry in amap["archived"]:
        for glob in entry["paths"]:
            if glob not in used_globs:
                findings.append(
                    Finding(glob, "dead-glob", "SHR-003", excerpt=f"archived {entry['id']} matches no file")
                )
    return result, findings


def check_readable_surfaces(root: Path, cls: Classification) -> list[Finding]:
    """
    A canon surface the checker cannot safely read is a finding, not a skip.

    `read_text` returning None is the *skip* path, so without this a committed
    `docs/x.md -> ../elsewhere/contradicting.md` would classify active, be
    skipped by every prose scan, and ship an unscanned contradiction — the exact
    evasion SHR-004 exists to stop. Unscoped surfaces are never read, so firing
    there would be noise rather than coverage.
    """
    findings: list[Finding] = []
    for rel in sorted(set(cls.active) | set(cls.archived)):
        path = root / rel
        if path.suffix.lower() in BINARY_SUFFIXES:
            continue
        if not is_regular_file(path):
            findings.append(
                Finding(rel, "unreadable-surface", "SHR-003",
                        excerpt="not a regular file (symlink, FIFO, device or socket)")
            )
    return findings


def check_conflict_authorities(root: Path, amap: dict) -> list[Finding]:
    findings: list[Finding] = []
    for rule in amap["conflict_rules"]:
        rel = rule["authority"]
        text = read_text(root, rel)
        if text is None:
            findings.append(
                Finding(rel, "missing-authority", "SHR-003", excerpt=f"cited for {rule['question']}")
            )
        elif "**Status:** Accepted" not in text:
            findings.append(
                Finding(rel, "authority-not-accepted", "SHR-003", excerpt=f"cited for {rule['question']}")
            )
    return findings


# --------------------------------------------------------------------------- #
# SHR-004 — canon conflicts
# --------------------------------------------------------------------------- #

# Sentence-bounded on purpose. `[^.;\n]` stops the window at a sentence or clause
# break so that correct statements which merely mention both words in adjacent
# clauses do not fire.
#
_CANON = "canon" + "ical"
_MARKDOWN = "mark" + "down"

# Two boundary characters are driven by real false positives on this tree:
# a full stop separates current-state authority from generated prose views, and
# a semicolon separates append-only history from generated human-readable views.
CONFLICT_RULES: list[tuple[str, re.Pattern[str]]] = [
    (
        _MARKDOWN + "-" + _CANON,
        re.compile(
            r"(?i)"
            + _CANON
            + r"[^.;\n]{0,60}\b"
            + _MARKDOWN
            + r"\b|\b"
            + _MARKDOWN
            + r"\b[^.;\n]{0,60}"
            + _CANON
        ),
    ),
    ("canonical-wiki", re.compile(r"(?i)canonical\s+wiki")),
    ("markdown-source-of-truth", re.compile(r"(?i)\bmarkdown\b[^.;\n]{0,40}source of truth")),
]

# A line that states the *resolved* invariant mentions both words and is correct.
# Sentence bounds alone cannot separate these two, because the correct form often
# packs the whole invariant into one clause:
#
#   contradiction  "state authority points at generated prose"      (AGENTS.md:32)
#   correct        "Generated prose views are never authority"       (memory service:792)
#   correct        "...JSONL holds canonical append-only history,
#                   Markdown is a generated human-readable view"    (wiki/Glossary.md:11)
#
# The discriminator is whether the line frames Markdown as derived. If it says
# generated / derived / view / never canonical, ADR-0001 is being restated, not
# contradicted.
#
# Scoped to the CLAUSE containing the hit, never the whole line. Line scope was a
# one-word bypass of the entire SHR-004 scan: appending "Views are generated." to
# a contradicting sentence silenced it, and a Markdown table row with a
# "generated" cell silenced a contradiction in an adjacent cell. Clause bounds use
# the same '.' and ';' characters as the CONFLICT_RULES windows, so the two agree.
EXCULPATING_RE = re.compile(r"(?i)\bgenerated\b|\bderive[sd]?\b|\bviews?\b|never canonical")

# '|' is a boundary too: a Markdown table row carries no sentence punctuation, so
# without it one cell's "generated" exculpates a contradiction in another cell.
# Narrower than the CONFLICT_RULES window on purpose — narrowing the exculpation
# scope can only surface more findings, never hide one.
_CLAUSE_BOUNDS = ".;|"


def _clause_around(line: str, start: int, end: int) -> str:
    """The clause containing [start:end), bounded by '.' or ';' (or the line ends)."""
    lo = max(line.rfind(c, 0, start) for c in _CLAUSE_BOUNDS)
    after = [i for i in (line.find(c, end) for c in _CLAUSE_BOUNDS) if i != -1]
    hi = min(after) if after else len(line)
    return line[lo + 1 : hi]


def _contradiction_hits(text: str, pattern: re.Pattern[str]) -> list[str]:
    hits: list[str] = []
    for line in text.splitlines():
        for m in pattern.finditer(line):
            if EXCULPATING_RE.search(_clause_around(line, m.start(), m.end())):
                continue
            hits.append(m.group(0).strip())
    return hits


def check_canon_conflicts(root: Path, cls: Classification, amap: dict) -> list[Finding]:
    """
    Scan ACTIVE surfaces only.

    The ADR that resolves a conflict is exempt: ADR-0001's Context section must
    quote the contradiction it retired ("treated Markdown as the source of
    truth") in order to explain the decision. Flagging the resolution as the
    problem would make the audit unfixable.
    """
    exempt = {rule["authority"] for rule in amap["conflict_rules"]}
    findings: list[Finding] = []
    for rel in sorted(cls.active):
        if rel in exempt:
            continue
        text = read_text(root, rel)
        if text is None:
            continue
        for rule, pattern in CONFLICT_RULES:
            hits = _contradiction_hits(text, pattern)
            if hits:
                findings.append(
                    Finding(rel, rule, "SHR-004", count=len(hits), excerpt=hits[0], hits=tuple(hits))
                )
    return findings


def check_archived_files_marked(root: Path, amap: dict, cls: Classification) -> list[Finding]:
    """An archived surface that does not say so reads as live to every reader."""
    markers = {entry["id"]: entry["marker"] for entry in amap["archived"] if entry.get("marker")}
    findings: list[Finding] = []
    for rel, entry_id in sorted(cls.archived.items()):
        marker = markers.get(entry_id)
        if not marker:
            continue
        text = read_text(root, rel)
        if text is None:
            continue
        head = "\n".join(text.splitlines()[:15])
        if marker.lower() not in head.lower():
            findings.append(
                Finding(rel, "archived-unmarked", "SHR-004",
                        excerpt=f"no {marker!r} in first 15 lines")
            )
    return findings


def check_live_citations_of_archived(root: Path, amap: dict, cls: Classification) -> list[Finding]:
    """Active prose that points readers at a superseded directory."""
    prefixes = sorted({
        p for entry in amap["archived"] for glob in entry["paths"]
        if (p := _literal_dir_prefix(glob))
    })
    if not prefixes:
        return []
    findings: list[Finding] = []
    for rel in sorted(cls.active):
        text = read_text(root, rel)
        if text is None:
            continue
        cited = [p for p in prefixes if p in text]
        if cited:
            findings.append(
                Finding(rel, "cites-archived", "SHR-004", count=len(cited),
                        excerpt=", ".join(cited), hits=tuple(cited))
            )
    return findings


# --------------------------------------------------------------------------- #
# SHR-005 — component status labels
# --------------------------------------------------------------------------- #

STATUS_COLLECTIONS = ["skills", "agents", "commands", "team_packs", "gates"]


def status_enum(root: Path) -> tuple[list[str], list[Finding]]:
    """
    Read the label set from the schema at runtime when the contract registry
    still exists. vNext Phase 01 deliberately removes it.
    """
    path = root / SCHEMA_REL
    if not path.exists():
        if not (root / REGISTRY_REL).exists():
            return [], []
        raise InputError(f"registry schema missing: {SCHEMA_REL}")
    try:
        schema = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InputError(f"{SCHEMA_REL} is not valid JSON: {exc}") from exc

    def _enum(collection: str) -> list[str] | None:
        node = schema.get("properties", {}).get(collection, {})
        node = node.get("items", {}).get("properties", {}).get("status", {})
        return node.get("enum")

    skills_enum = _enum("skills")
    if not skills_enum:
        raise InputError(f"{SCHEMA_REL}: no $.properties.skills.items.properties.status.enum")

    findings: list[Finding] = []
    agents_enum = _enum("agents")
    if agents_enum != skills_enum:
        findings.append(
            Finding(SCHEMA_REL, "status-enum-divergence", "SHR-005",
                    excerpt=f"skills={skills_enum} agents={agents_enum}")
        )
    return skills_enum, findings


def check_status_labels(root: Path, enum: list[str]) -> tuple[list[Finding], list[str]]:
    path = root / REGISTRY_REL
    if not path.exists():
        return [], ["contract registry removed"]
    try:
        registry = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InputError(f"{REGISTRY_REL} is not valid JSON: {exc}") from exc

    allowed = set(enum)
    findings: list[Finding] = []
    census: list[str] = []
    for collection in STATUS_COLLECTIONS:
        entries = registry.get(collection)
        if not isinstance(entries, list):
            continue
        missing = [e for e in entries if not e.get("status")]
        invalid = [e for e in entries if e.get("status") and e["status"] not in allowed]
        labelled = len(entries) - len(missing)
        census.append(
            f"{collection}: {labelled}/{len(entries)} labelled"
            + (f", {len(invalid)} out of enum" if invalid else "")
        )
        if missing:
            findings.append(
                Finding(REGISTRY_REL, f"{collection}.status-missing", "SHR-005",
                        count=len(missing), excerpt=f"{len(missing)} entries carry no status label")
            )
        if invalid:
            bad = sorted({e["status"] for e in invalid})
            findings.append(
                Finding(REGISTRY_REL, f"{collection}.status-invalid", "SHR-005",
                        count=len(invalid), excerpt=f"out of enum: {bad}")
            )
    return findings, census


# --------------------------------------------------------------------------- #
# SHR-006 — public claim ledger
# --------------------------------------------------------------------------- #

# Public surfaces bold their numbers ("**979 tests**"), so a shape that demands a
# literal space and a lowercase noun sees almost nothing. `_GAP` absorbs Markdown
# emphasis, backticks and non-breaking space on either side of the number, and
# every shape is case-insensitive.
_GAP = r"[*_`]*[\s\u00a0]+[*_`]*"
_NUM = r"[*_`]*(\d{1,4})[*_`]*"

CLAIM_SHAPES = [
    re.compile(
        r"(?i)" + _NUM + _GAP
        + r"(?:tests|files|checks|surfaces|skills|agents|commands|team-packs|packs|gates)\b"
    ),
    re.compile(r"(?i)capped at" + _GAP + _NUM + _GAP + r"agents"),
    re.compile(r"(?i)max" + _GAP + _NUM + _GAP + r"agents per pack"),
    re.compile(r"(?i)lists all" + _GAP + _NUM),
]
CLAIM_SURFACES = ["README.md", "AGENTS.md"]

_MARKUP_RE = re.compile(r"[*_`]+")


def _normalise_claim(text: str) -> str:
    """
    Strip Markdown emphasis and fold whitespace, lowercased.

    The ledger records the claim as a human writes it ("979 tests"); the surface
    renders it with emphasis ("**979** tests"). Comparing raw strings made every
    bolded claim look unledgered the moment CLAIM_SHAPES learned to see markup.
    """
    return " ".join(_MARKUP_RE.sub("", text).replace("\u00a0", " ").split()).lower()




def _dotted(data: object, path: str) -> object:
    for key in path.split("."):
        if isinstance(data, list):
            data = data[int(key)]
        elif isinstance(data, dict):
            data = data[key]
        else:
            raise InputError(f"cannot descend into {type(data).__name__} at {key!r}")
    return data


def resolve_within(root: Path, rel: str) -> Path:
    """
    A data-file path, confined to the repository.

    `root / rel` silently yields `rel` itself when `rel` is absolute, and `..`
    walks out just as easily. The ledger is data, so this is the difference
    between recomputing evidence and reading an arbitrary file on the host —
    which is both an existence oracle and, pointed at a device or FIFO, the same
    unbounded read the surface reader was just hardened against.

    The glob-driven kinds need no equivalent: they match against walk_files(root)
    output, so they can only ever name paths already inside the tree.
    """
    path = (root / rel).resolve()
    if not path.is_relative_to(root.resolve()):
        raise InputError(f"path escapes --root: {rel!r}")
    if not is_regular_file(path):
        raise InputError(f"not a regular file: {rel!r}")
    return path


def recompute(root: Path, verify: dict) -> int:
    """Pure-stdlib evidence recomputation. No subprocess, no network."""
    kind = verify.get("kind")
    if kind == "count_json_array":
        rel = verify["file"]
        try:
            data = json.loads(resolve_within(root, rel).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise InputError(f"count_json_array: cannot read {rel}: {exc}") from exc
        node = _dotted(data, verify["path"])
        if not isinstance(node, list):
            raise InputError(f"count_json_array: {rel}:{verify['path']} is not an array")
        return len(node)
    if kind == "count_glob":
        glob = verify["glob"]
        return sum(1 for rel in walk_files(root) if _matches(glob, rel))
    if kind == "count_regex":
        # `file` is a glob so that a claim spanning sibling modules (the CLI is
        # split across shiroe/cli*.py) stays one claim. A plain path is the
        # degenerate case of a glob with no wildcard.
        pattern = re.compile(verify["pattern"])
        total = 0
        matched_any = False
        for rel in walk_files(root):
            if not _matches(verify["file"], rel):
                continue
            matched_any = True
            text = read_text(root, rel)
            if text is not None:
                total += len(pattern.findall(text))
        if not matched_any:
            raise InputError(f"count_regex: {verify['file']} matches no file")
        return total
    raise InputError(f"unknown verify kind: {kind!r}")


def check_claim_drift(root: Path, ledger: dict) -> list[Finding]:
    findings: list[Finding] = []
    for claim in ledger.get("claims", []):
        if claim.get("claim_class") != "machine_verified":
            continue
        if claim.get("status") == "removed":
            # The status enum carries "removed" for a claim withdrawn from its
            # surface. It asserts nothing, so there is nothing to drift against
            # -- and drift-checking it reports the tree disagreeing with a
            # number nobody publishes any more. The entry stays in the ledger so
            # the withdrawal keeps its reason.
            continue
        observed = recompute(root, claim["verify"])
        expected = claim.get("evidence_value")
        if observed != expected:
            findings.append(
                Finding(claim["surface"], f"claim-drift/{claim['id']}", "SHR-006",
                        excerpt=f"ledger says {expected!r}, tree says {observed!r}")
            )
    return findings


def check_unledgered_claims(root: Path, ledger: dict) -> list[Finding]:
    """Every numeric claim shape on a public surface must be on the books."""
    by_surface: dict[str, list[str]] = {}
    for claim in ledger.get("claims", []):
        by_surface.setdefault(claim["surface"], []).append(claim.get("claim", ""))

    findings: list[Finding] = []
    for rel in CLAIM_SURFACES:
        text = read_text(root, rel)
        if text is None:
            continue
        known = by_surface.get(rel, [])
        orphans: list[str] = []
        known_norm = [_normalise_claim(entry) for entry in known]
        for shape in CLAIM_SHAPES:
            for match in shape.finditer(text):
                phrase = match.group(0)
                if not any(_normalise_claim(phrase) in entry for entry in known_norm):
                    orphans.append(phrase)
        if orphans:
            findings.append(
                Finding(rel, "unledgered-claim", "SHR-006", count=len(orphans),
                        excerpt="; ".join(sorted(set(orphans))))
            )
    return findings


# --------------------------------------------------------------------------- #
# Baseline reconciliation + reporting
# --------------------------------------------------------------------------- #


def reconcile(observed: list[Finding], baseline: dict[str, dict]) -> tuple[list[str], dict[str, list]]:
    errors: list[str] = []
    buckets: dict[str, list] = {"new": [], "known": [], "dropped": [], "regressed": [], "count": []}
    seen: dict[str, Finding] = {}

    for finding in observed:
        if finding.id in seen:  # same (surface, rule) twice — fold multiplicity
            seen[finding.id].count += finding.count
            seen[finding.id].hits += finding.hits
            continue
        seen[finding.id] = finding

    for fid, finding in sorted(seen.items()):
        entry = baseline.get(fid)
        if entry is None:
            buckets["new"].append(finding)
            errors.append(f"NEW: {fid} [{finding.shr}] {finding.excerpt}")
        elif entry["status"] == "resolved":
            buckets["regressed"].append(finding)
            errors.append(f"REGRESSED: {fid} is recorded resolved but is present again")
        elif entry.get("digest") not in (None, "", finding.digest):
            buckets["count"].append(finding)
            errors.append(
                f"CONTENT DRIFT: {fid} is acknowledged, but the matched text changed "
                f"(baseline digest {entry['digest']}, tree {finding.digest}). "
                f"Observed now: {finding.excerpt!r}"
            )
        elif entry["count"] != finding.count:
            buckets["count"].append(finding)
            errors.append(
                f"COUNT DRIFT: {fid} baseline says {entry['count']}, tree has {finding.count}"
            )
        else:
            buckets["known"].append(finding)

    for fid, entry in sorted(baseline.items()):
        if entry["status"] in ACKNOWLEDGED_STATUSES and fid not in seen:
            buckets["dropped"].append(fid)
            errors.append(
                f"DROPPED: {fid} is acknowledged in the baseline but no longer observed — "
                f"remove it or mark it resolved"
            )
    return errors, buckets


def main() -> int:
    parser = argparse.ArgumentParser(description="Canon consistency audit (SHR-003..SHR-006)")
    parser.add_argument("--root", default=".", help="Repository root (default: cwd)")
    args = parser.parse_args()
    root = Path(args.root).resolve()

    try:
        install_watchdog()
        amap = load_authority_map(root)
        baseline_doc = load_baseline(root)
        ledger = load_ledger(root)
        enum, enum_findings = status_enum(root)

        files = walk_files(root)
        cls, authority_findings = classify(amap, files)

        observed: list[Finding] = []
        observed += authority_findings
        observed += check_readable_surfaces(root, cls)
        observed += check_conflict_authorities(root, amap)
        observed += check_canon_conflicts(root, cls, amap)
        observed += check_archived_files_marked(root, amap, cls)
        observed += check_live_citations_of_archived(root, amap, cls)
        observed += enum_findings
        status_findings, census = check_status_labels(root, enum)
        observed += status_findings
        observed += check_claim_drift(root, ledger)
        observed += check_unledgered_claims(root, ledger)
    except InputError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except (KeyError, IndexError, ValueError, TypeError) as exc:
        # A malformed data file reaches here as a raw lookup/parse error from any
        # of a dozen sites (t["rank"], entry["paths"], rule["authority"],
        # claim["verify"], _dotted's descent). The documented contract for bad
        # input is exit 2, and a traceback with exit 1 reads as "drift found".
        print(f"ERROR: malformed checker input: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    finally:
        cancel_watchdog()

    commit = head_commit(root)
    print(f"Canon audit — {root}")
    if commit:
        print(f"commit: {commit}")

    print("\nSHR-003 source authority")
    print(f"  [OK] authority map: {len(amap['tiers'])} tiers, "
          f"{len(amap['archived'])} archived, {len(amap['unscoped'])} unscoped globs")
    print(f"  [OK] surfaces: {len(files)} files — {len(cls.active)} active, "
          f"{len(cls.archived)} archived, {len(cls.unscoped)} unscoped, "
          f"{len(cls.unclassified)} unclassified")

    print("\nSHR-005 status census")
    for line in census:
        print(f"  [OK] {line}")

    recorded = baseline_doc.get("recorded_at_commit")
    if commit and recorded and recorded != commit:
        print(f"\nnote: baseline recorded at {recorded}, HEAD is {commit} (informational)")

    errors, buckets = reconcile(observed, baseline_doc["_by_id"])

    print("\nFindings")
    for finding in buckets["known"]:
        print(f"  [KNOWN] {finding.id} x{finding.count} [{finding.shr}]")
    for finding in buckets["new"]:
        print(f"  [NEW] {finding.id} x{finding.count} [{finding.shr}] {finding.excerpt}")
    for finding in buckets["count"] + buckets["regressed"]:
        print(f"  [DRIFT] {finding.id} x{finding.count} [{finding.shr}]")
    for fid in buckets["dropped"]:
        print(f"  [DRIFT] {fid} (dropped)")

    print(
        f"\nFindings: {len(buckets['new'])} new, {len(buckets['known'])} acknowledged, "
        f"{len(buckets['dropped'])} dropped, {len(buckets['regressed'])} regressed"
    )

    if errors:
        print(f"\n✘ {len(errors)} error(s):", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print(f"\n✔ Canon audit passed ({len(buckets['known'])} acknowledged finding(s), no drift)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
