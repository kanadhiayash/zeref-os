"""
privacy-audit: allow-file "Memory scaffold module names example project fields (project_root, created, last_session) as schema documentation; no real data."

Memory Core layout helpers for Shiroe.

This module is the narrow boundary for project-root discovery and memory
scaffolding. Higher-level write, search, and lifecycle behavior should build on
these helpers instead of duplicating path lists in the CLI.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from shiroe.privacy import scrub
from shiroe.storage.state import StateDB


@dataclass(frozen=True)
class MemoryRoot:
    """A discovered Shiroe project root."""

    root: Path

    @classmethod
    def from_path(cls, root: Path) -> "MemoryRoot":
        resolved = root.resolve()
        return cls(root=resolved)

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
    """Compatibility writer that records decisions through canonical memory."""

    def __init__(self, memory_root: MemoryRoot):
        self.memory_root = memory_root

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
        """Write a decision to canonical SQLite and regenerate Markdown views."""
        from shiroe.memory.models import MemoryWrite
        from shiroe.memory.service import MemoryService
        from shiroe.memory.views import render_views

        redact = self.memory_root.root / "REDACT.md"

        title_s, title_r = scrub(title, redact, provenance="write-decision/title")
        why_s, why_r = scrub(why, redact, provenance="write-decision/why")
        evidence_s, evidence_r = scrub(evidence, redact, provenance="write-decision/evidence")
        total_redacted = title_r.redacted + why_r.redacted + evidence_r.redacted
        today = date.today().isoformat()

        service = MemoryService(self.memory_root.root)
        record = service.write(
            MemoryWrite(
                kind="decision",
                title=title_s,
                claim=title_s,
                summary=(
                    f"Rationale: {why_s}; Evidence: "
                    f"{evidence_s or '(none provided)'}; pii_scrubbed={total_redacted}"
                ),
                source_refs=(evidence_s or "user-input",),
                evidence_grade=grade,
                privacy_class="internal",
                confidence="medium",
            )
        )
        render_views(self.memory_root.root)
        history = service.history(record.id)
        event_hash = history[-1].hash if history else ""

        return WriteResult(
            target=self.memory_root.root / "memory" / "views" / "decisions.md",
            title=title_s,
            date=today,
            redacted=total_redacted,
            event_hash=event_hash,
        )

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
    network_scope: str | None,
) -> dict[str, str | None]:
    """Normalize current init values."""
    normalized_name = name or "(unnamed)"
    normalized_privacy = privacy or "abstract"
    normalized_network_scope = network_scope or "device-only"
    return {
        "name": normalized_name,
        "privacy": normalized_privacy,
        "network_scope": normalized_network_scope,
    }


def scaffold_project(
    root: Path,
    *,
    name: str | None,
    privacy: str | None,
    network_scope: str | None,
) -> MemoryRoot:
    """Create the Shiroe memory/config scaffold without overwriting user files."""
    memory_root = MemoryRoot.from_path(root)
    values = normalize_init_values(
        name=name,
        privacy=privacy,
        network_scope=network_scope,
    )

    for directory in (
        memory_root.root / "config",
        memory_root.root / ".shiroe" / "policy",
        memory_root.root / "memory" / "state",
    ):
        directory.mkdir(parents=True, exist_ok=True)

    project_path = memory_root.root / "config" / "PROJECT.md"
    # project_root is discovered at runtime from PROJECT.md's own location.
    # Never write absolute host paths into tracked config — PRIVACY.md internal_paths.
    project_path.write_text(
        f"---\nproject_name: \"{values['name']}\"\nproject_root: \"<discovered-at-runtime>\"\n"
        f"created: \"{date.today().isoformat()}\"\nlast_session: \"\"\n"
        f"---\n\n# {values['name']}\n\n"
        f"Project initialised via `shiroe init` on {date.today().isoformat()}.\n",
        encoding="utf-8",
    )

    privacy_path = memory_root.root / "PRIVACY.md"
    if not privacy_path.exists():
        privacy_path.write_text(
            f"---\nmode: {values['privacy']}\nnetwork_scope: {values['network_scope']}\n"
            f"---\n\n# PRIVACY.md\n\nMode: `{values['privacy']}`.\n"
            f"Network scope: `{values['network_scope']}`.\n",
            encoding="utf-8",
        )

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
            "  email:\n"
            "    enabled: true\n"
            "  internal_paths:\n"
            "    enabled: true\n"
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

    defaults_path = memory_root.root / ".shiroe" / "policy" / "defaults.json"
    if not defaults_path.exists():
        defaults_path.write_text(
            '{"allow":["capability.invoke","subprocess"]}\n',
            encoding="utf-8",
        )

    _write_runtime_files(memory_root.root)
    return memory_root


def _write_runtime_files(root: Path) -> None:
    state = StateDB(root)
    try:
        state.migrate()
    finally:
        state.close()
