"""
privacy-audit: allow-file "Memory scaffold module names example project fields (project_root, created, last_session) as schema documentation; no real data."

Memory Core layout helpers for Shiroe.

This module is the narrow boundary for project-root discovery and memory
scaffolding. Higher-level write, search, and lifecycle behavior should build on
these helpers instead of duplicating path lists in the CLI.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from shiroe.compat.legacy_identity import LEGACY_V1_STATE_DB_NAME
from shiroe.lock import LockError, MemoryLock, atomic_append
from shiroe.privacy import scrub


MEMORY_LAYERS: tuple[str, ...] = ("L0", "L1", "L2", "L3")

MEMORY_DIRS: tuple[str, ...] = (
    "memory",
    "memory/archive",
    "memory/archives",
    "memory/audit",
    "memory/handoffs",
    "memory/indexes",
    "memory/l0_raw",
    "memory/l1_atoms",
    "memory/l2_scenes",
    "memory/l3_profiles",
    "memory/layers",
    "memory/layers/L0",
    "memory/layers/L1",
    "memory/layers/L2",
    "memory/layers/L3",
    "memory/loops",
    "memory/patterns",
    "memory/reports",
    "memory/state",
    "memory/views",
    "memory/snapshots",
    "memory/raw",
    "memory/sync/outbound",
    "memory/sync/parent",
)

PROJECT_DIRS: tuple[str, ...] = (
    "config",
)

MEMORY_FILES: tuple[str, ...] = (
    "memory/hot.md",
    "memory/index.md",
    "memory/DECISIONS.md",
    "memory/OPEN_QUESTIONS.md",
    "memory/RISKS.md",
    "memory/CONFLICTS.md",
    "memory/MEMORY.md",
    "memory/patterns/PATTERNS.jsonl",
    "memory/state/events.jsonl",
    "memory/state/schema.json",
    "memory/l1_atoms/facts.jsonl",
    "memory/l1_atoms/decisions.jsonl",
    "memory/l1_atoms/risks.jsonl",
    "memory/l1_atoms/tasks.jsonl",
    "memory/l1_atoms/preferences.jsonl",
    "memory/l1_atoms/contradictions.jsonl",
    "memory/l1_atoms/sources.jsonl",
    "memory/l1_atoms/errors.jsonl",
    "memory/l1_atoms/tests.jsonl",
    "memory/l1_atoms/events.jsonl",
    "memory/audit/writes.jsonl",
    "memory/audit/reads.jsonl",
    "memory/audit/routes.jsonl",
    "memory/audit/guard_failures.jsonl",
    "memory/audit/redactions.jsonl",
    "memory/audit/releases.jsonl",
)

STATE_SCHEMA: dict = {
    "schema_version": "memory-state.v1",
    # v1 compat; vNext canonical = memory/state/shiroe.sqlite (ADR-0001).
    "canonical_store": f"memory/state/{LEGACY_V1_STATE_DB_NAME}",
    "event_log": "memory/state/events.jsonl",
    "tables": {
        "memory_items": {
            "fields": [
                "id",
                "kind",
                "title",
                "body",
                "entity",
                "tags",
                "layer",
                "source_ref",
                "confidence",
                "authority",
                "created_at",
                "updated_at",
                "archived",
            ],
            "search_index": "memory_items_fts",
        },
        "memory_cards": {
            "fields": [
                "id",
                "type",
                "title",
                "claim",
                "status",
                "confidence",
                "evidence_grade",
                "source_refs",
                "privacy_class",
                "created_at",
                "updated_at",
                "valid_from",
                "valid_until",
                "supersedes",
                "superseded_by",
                "tags",
                "owner",
            ],
        },
        "memory_events": {
            "fields": ["id", "ts", "event", "item_id", "payload", "hash"],
            "append_only_mirror": "memory/state/events.jsonl",
        },
    },
}


@dataclass(frozen=True)
class MemoryLayout:
    """Resolved paths for the current Shiroe memory layout."""

    root: Path

    @property
    def memory_dir(self) -> Path:
        return self.root / "memory"

    @property
    def config_dir(self) -> Path:
        return self.root / "config"

    @property
    def patterns_log(self) -> Path:
        return self.root / "memory" / "patterns" / "PATTERNS.jsonl"

    @property
    def state_dir(self) -> Path:
        return self.root / "memory" / "state"

    @property
    def state_db(self) -> Path:
        return self.state_dir / LEGACY_V1_STATE_DB_NAME

    @property
    def state_events(self) -> Path:
        return self.state_dir / "events.jsonl"

    @property
    def state_schema(self) -> Path:
        return self.state_dir / "schema.json"

    @property
    def audit_dir(self) -> Path:
        return self.memory_dir / "audit"

    def path(self, relative: str) -> Path:
        return self.root / relative

    def directories(self) -> tuple[Path, ...]:
        return tuple(self.root / rel for rel in (*MEMORY_DIRS, *PROJECT_DIRS))

    def files(self) -> tuple[Path, ...]:
        return tuple(self.root / rel for rel in MEMORY_FILES)


@dataclass(frozen=True)
class MemoryRoot:
    """A Shiroe project root plus its resolved memory layout."""

    root: Path
    layout: MemoryLayout

    @classmethod
    def from_path(cls, root: Path) -> "MemoryRoot":
        resolved = root.resolve()
        return cls(root=resolved, layout=MemoryLayout(resolved))

    @classmethod
    def discover(cls, start: Path | None = None, max_depth: int = 10) -> "MemoryRoot":
        return cls.from_path(discover_project_root(start=start, max_depth=max_depth))


@dataclass(frozen=True)
class WriteResult:
    """Summary returned after a memory write."""

    target: Path
    title: str
    date: str
    redacted: int
    event_hash: str


class MemoryWriter:
    """Single writer for wiki files and their matching event-log entries."""

    def __init__(self, memory_root: MemoryRoot):
        self.memory_root = memory_root
        self.layout = memory_root.layout

    @classmethod
    def from_root(cls, root: Path) -> "MemoryWriter":
        return cls(MemoryRoot.from_path(root))

    @classmethod
    def discover(cls, start: Path | None = None) -> "MemoryWriter":
        return cls(MemoryRoot.discover(start=start))

    def write_decision(
        self,
        *,
        title: str,
        why: str,
        evidence: str,
        grade: str,
    ) -> WriteResult:
        """Append a scrubbed decision and emit a schema-valid wiki-write event."""
        target = self.layout.path("memory/DECISIONS.md")
        redact = self.memory_root.root / "REDACT.md"

        title_s, title_r = scrub(title, redact, provenance="write-decision/title")
        why_s, why_r = scrub(why, redact, provenance="write-decision/why")
        evidence_s, evidence_r = scrub(evidence, redact, provenance="write-decision/evidence")
        total_redacted = title_r.redacted + why_r.redacted + evidence_r.redacted
        today = date.today().isoformat()

        entry = (
            f"\n---\n"
            f"**Decision:** {title_s}\n"
            f"**Date:** {today}\n"
            f"**Rationale:** {why_s}\n"
            f"**Evidence:** {evidence_s or '(none provided)'}\n"
            f"**Evidence grade:** {grade}\n"
            f"**Provenance:** shiroe-cli write-decision (pii_scrubbed={total_redacted})\n"
            f"---\n"
        )

        event, event_hash = self._wiki_write_event(
            target="memory/DECISIONS.md",
            summary=f"Decision: {title_s}",
            evidence_grade=grade,
        )

        try:
            with MemoryLock(self.layout.memory_dir):
                atomic_append(target, entry)
                atomic_append(self.layout.patterns_log, json.dumps(event, sort_keys=True) + "\n")
        except LockError:
            raise

        return WriteResult(
            target=target,
            title=title_s,
            date=today,
            redacted=total_redacted,
            event_hash=event_hash,
        )

    def _wiki_write_event(
        self,
        *,
        target: str,
        summary: str,
        evidence_grade: str,
    ) -> tuple[dict, str]:
        payload = {"summary": summary}
        payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        event_hash = "sha256:" + hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        event = {
            "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "agent": "memory-keeper",
            "event": "wiki-write",
            "target": target,
            "payload": payload,
            "hash": event_hash,
            "evidence_grade": evidence_grade,
        }
        return event, event_hash


def discover_project_root(start: Path | None = None, max_depth: int = 10) -> Path:
    """Walk up from start looking for a Shiroe project marker.

    Prefer config/PROJECT.md (always scaffolded by `shiroe init`).
    Fall back to AGENTS.md for the packaging repo (which does not run init).
    """
    current = (start or Path.cwd()).resolve()
    for _ in range(max_depth):
        if (current / "config" / "PROJECT.md").exists():
            return current
        if (current / "AGENTS.md").exists():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    return (start or Path.cwd()).resolve()


def normalize_init_values(
    *,
    name: str | None,
    privacy: str | None,
    tier: str | None,
    parent: str | None,
) -> dict[str, str | None]:
    """Normalize init values while preserving empty parent as explicit null."""
    normalized_name = name or "(unnamed)"
    normalized_privacy = privacy or "abstract"
    normalized_tier = tier or "auto"
    normalized_parent = parent if parent else None
    return {
        "name": normalized_name,
        "privacy": normalized_privacy,
        "tier": normalized_tier,
        "parent": normalized_parent,
    }


def scaffold_project(
    root: Path,
    *,
    name: str | None,
    privacy: str | None,
    tier: str | None,
    parent: str | None,
) -> MemoryRoot:
    """Create the Shiroe memory/config scaffold without overwriting user files."""
    memory_root = MemoryRoot.from_path(root)
    values = normalize_init_values(
        name=name,
        privacy=privacy,
        tier=tier,
        parent=parent,
    )

    for directory in memory_root.layout.directories():
        directory.mkdir(parents=True, exist_ok=True)

    project_path = memory_root.layout.config_dir / "PROJECT.md"
    # project_root is discovered at runtime from PROJECT.md's own location.
    # Never write absolute host paths into tracked config — PRIVACY.md internal_paths.
    project_path.write_text(
        f"---\nproject_name: \"{values['name']}\"\nproject_root: \"<discovered-at-runtime>\"\n"
        f"created: \"{date.today().isoformat()}\"\nlast_session: \"\"\n"
        f"active_runtime:\n  - state\n  - memory\n  - policy\n"
        f"privacy_mode: {values['privacy']}\nparent_project: {values['parent'] or 'null'}\n"
        f"model_tier: {values['tier']}\nbudget_warn_at: 50000\n---\n\n# {values['name']}\n\n"
        f"Project initialised via `shiroe init` on {date.today().isoformat()}.\n",
        encoding="utf-8",
    )

    privacy_path = memory_root.root / "PRIVACY.md"
    if not privacy_path.exists():
        privacy_path.write_text(
            f"---\nmode: {values['privacy']}\nabstract_rules:\n  strip_pii: true\n"
            f"  strip_internal_paths: true\n  strip_credentials: true\n"
            f"  strip_numbers: false\nlocal_only_blocks:\n  - memory/sync/outbound/\n"
            f"  - memory/sync/parent/\n---\n\n# PRIVACY.md\n\nMode: `{values['privacy']}`.\n",
            encoding="utf-8",
        )

    budget_path = memory_root.layout.config_dir / "BUDGET.md"
    if not budget_path.exists():
        budget_path.write_text(
            f"---\nmodel_tier: {values['tier']}\nalways_on_target_tokens: 2000\n"
            f"warn_at_tokens: 50000\nhard_cap_tokens: 180000\nboundary_first: true\n---\n",
            encoding="utf-8",
        )

    # WS4 (issue #122): `shiroe doctor` requires REDACT.md, SHARING_POLICY.md,
    # and config/PERMISSIONS.md — a fresh init must satisfy its own doctor.
    redact_path = memory_root.root / "REDACT.md"
    if not redact_path.exists():
        redact_path.write_text(
            "---\n"
            "# Sensitive classes stripped before memory writes / external output.\n"
            "classes:\n"
            "  credentials:\n"
            "    enabled: true\n"
            "    patterns:\n"
            "      - api_keys\n"
            "      - oauth_tokens\n"
            "      - ssh_private_keys\n"
            "      - database_connection_strings\n"
            "  pii:\n"
            "    enabled: true\n"
            "    patterns:\n"
            "      - email_addresses\n"
            "      - phone_numbers\n"
            "      - government_ids\n"
            "  internal_paths:\n"
            "    enabled: true\n"
            "    patterns:\n"
            "      - absolute_filesystem_paths\n"
            "      - hostnames\n"
            "---\n\n# REDACT.md\n\n"
            "Default redaction classes scaffolded by `shiroe init`. "
            "Tune per project.\n",
            encoding="utf-8",
        )

    sharing_path = memory_root.root / "SHARING_POLICY.md"
    if not sharing_path.exists():
        sharing_path.write_text(
            "---\n"
            "# Per-connector sharing allowlist — everything OFF by default.\n"
            "defaults:\n"
            "  read_project_context: false\n"
            "  write_external: false\n"
            "connectors: {}\n"
            "---\n\n# SHARING_POLICY.md\n\n"
            "No connectors enabled. Add entries under `connectors:` with\n"
            "`enabled: true` only after deliberate review.\n",
            encoding="utf-8",
        )

    permissions_path = memory_root.layout.config_dir / "PERMISSIONS.md"
    if not permissions_path.exists():
        permissions_path.write_text(
            "---\n"
            "defaults:\n"
            "  filesystem:\n"
            "    - read: project-root\n"
            "    - write: memory/\n"
            "  network:\n"
            "    - denied\n"
            "  mcp_servers: []\n"
            "session_overrides:\n"
            "---\n\n# Permissions\n\n"
            "Network egress is denied by default (fail-closed). To enable it,\n"
            "change the `network:` entry to `- allowed` AND set\n"
            "`external_transmission: on` in PRIVACY.md, or export\n"
            "`SHIROE_ALLOW_NETWORK=1` for a single session.\n",
            encoding="utf-8",
        )

    _write_memory_files(memory_root.layout)
    return memory_root


def _write_memory_files(layout: MemoryLayout) -> None:
    hot = layout.path("memory/hot.md")
    if not hot.exists():
        hot.write_text("# memory/hot.md\n\n*(empty - populated on first /done)*\n", encoding="utf-8")

    for relative in (
        "memory/index.md",
        "memory/DECISIONS.md",
        "memory/OPEN_QUESTIONS.md",
        "memory/RISKS.md",
        "memory/CONFLICTS.md",
        "memory/MEMORY.md",
    ):
        path = layout.path(relative)
        if not path.exists():
            path.write_text(f"# {Path(relative).name}\n", encoding="utf-8")

    if not layout.patterns_log.exists():
        layout.patterns_log.write_text("", encoding="utf-8")

    if not layout.state_events.exists():
        layout.state_events.write_text("", encoding="utf-8")

    for relative in (
        "memory/l1_atoms/facts.jsonl",
        "memory/l1_atoms/decisions.jsonl",
        "memory/l1_atoms/risks.jsonl",
        "memory/l1_atoms/tasks.jsonl",
        "memory/l1_atoms/preferences.jsonl",
        "memory/l1_atoms/contradictions.jsonl",
        "memory/l1_atoms/sources.jsonl",
        "memory/l1_atoms/errors.jsonl",
        "memory/l1_atoms/tests.jsonl",
        "memory/l1_atoms/events.jsonl",
    ):
        path = layout.path(relative)
        if not path.exists():
            path.write_text("", encoding="utf-8")

    for relative in (
        "memory/audit/writes.jsonl",
        "memory/audit/reads.jsonl",
        "memory/audit/routes.jsonl",
        "memory/audit/guard_failures.jsonl",
        "memory/audit/redactions.jsonl",
        "memory/audit/releases.jsonl",
    ):
        path = layout.path(relative)
        if not path.exists():
            path.write_text("", encoding="utf-8")

    layout.state_schema.write_text(
        json.dumps(STATE_SCHEMA, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
