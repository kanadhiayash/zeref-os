"""vNext PR 5 gate tests — capability adapters + probing."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from shiroe.adapters.capabilities import (
    AdapterNotFoundError,
    EnforcementLevel,
    list_adapters,
    probe,
    record_status,
    resolve_adapter,
)
from shiroe.adapters.capabilities.base import HealthReport
from shiroe.adapters.capabilities.cli import CLIAdapter
from shiroe.adapters.capabilities.repository_tool import RepositoryToolAdapter
from shiroe.capabilities import (
    approve,
    inspect_source,
    register_discovery,
)
from shiroe.capabilities.discovery import DiscoveredCapability
from shiroe.storage import EventLog, StateDB
from shiroe.storage import events as events_mod


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def test_all_adapters_registered() -> None:
    for name in ("cli", "repository-tool", "repository_tool"):
        adapter = resolve_adapter(name)
        assert adapter is not None


def test_unknown_adapter_raises() -> None:
    with pytest.raises(AdapterNotFoundError):
        resolve_adapter("nonexistent-adapter")


def test_enforcement_levels_are_honest() -> None:
    # Level A: we own the subprocess
    assert CLIAdapter().enforcement_level is EnforcementLevel.embedded
    assert RepositoryToolAdapter().enforcement_level is EnforcementLevel.embedded


def test_list_adapters_deduplicates() -> None:
    rows = list_adapters()
    names = [r["name"] for r in rows]
    assert len(names) == len(set(names))
    # Every row exposes a valid enforcement level
    for row in rows:
        assert row["enforcement_level"] in {"A", "B"}


# ---------------------------------------------------------------------------
# Executable CLI adapter helpers
# ---------------------------------------------------------------------------

def _register(tmp_path: Path, name: str, *, files: dict[str, str]) -> str:
    src = tmp_path / "source" / name
    src.mkdir(parents=True)
    for filename, content in files.items():
        (src / filename).write_text(content, encoding="utf-8")
    entry = src / next(iter(files))
    d = DiscoveredCapability(adapter="cli", root="<project>/source",
                             path=entry, kind="script")
    trust = inspect_source(src)
    return register_discovery(tmp_path, d, trust=trust)


# ---------------------------------------------------------------------------
# CLI adapter — policy integration
# ---------------------------------------------------------------------------

def _write_deny_subprocess(tmp_path: Path) -> None:
    (tmp_path / ".shiroe" / "policy").mkdir(parents=True)
    (tmp_path / ".shiroe" / "policy" / "deny.json").write_text(
        json.dumps({"deny": ["subprocess"]}), encoding="utf-8",
    )


def _write_allow_subprocess(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir(exist_ok=True)
    # PERMISSIONS.md doesn't yet vocabulary "subprocess", so route through
    # explicit-user-grant via project-defaults JSON.
    (tmp_path / ".shiroe" / "policy").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".shiroe" / "policy" / "defaults.json").write_text(
        json.dumps({"allow": ["subprocess"]}), encoding="utf-8",
    )


def test_cli_adapter_denies_when_policy_denies(tmp_path: Path) -> None:
    _write_deny_subprocess(tmp_path)
    cid = _register(tmp_path, "runme",
                    files={"run.sh": "#!/bin/sh\necho ok\n"})
    approve(tmp_path, cid)
    result = CLIAdapter().invoke(
        capability_id=cid, action="run",
        inputs={"root": str(tmp_path),
                "command": ["/bin/echo", "hello"]},
    )
    assert not result.ok
    assert "policy" in result.error.lower()
    assert result.metadata["policy"]["verdict"] == "deny"


def test_cli_adapter_runs_when_policy_allows(tmp_path: Path) -> None:
    _write_allow_subprocess(tmp_path)
    cid = _register(tmp_path, "echo",
                    files={"run.sh": "#!/bin/sh\necho hi\n"})
    approve(tmp_path, cid)
    result = CLIAdapter().invoke(
        capability_id=cid, action="run",
        inputs={"root": str(tmp_path),
                "command": ["/bin/echo", "adapter-ok"],
                "autonomy_mode": "policy-bound"},
    )
    assert result.ok, result.error
    assert "adapter-ok" in (result.output or "")
    assert result.exit_code == 0
    assert result.metadata["enforcement_level"] == "A"


def test_cli_adapter_enforces_command_allowlist(tmp_path: Path) -> None:
    _write_allow_subprocess(tmp_path)
    cid = _register(tmp_path, "restricted",
                    files={"run.sh": "#!/bin/sh\necho ok\n"})
    approve(tmp_path, cid)
    result = CLIAdapter().invoke(
        capability_id=cid, action="run",
        inputs={"root": str(tmp_path),
                "command": ["/bin/ls"],
                "autonomy_mode": "policy-bound"},
        permissions={"allow_commands": ["/bin/echo"]},
    )
    assert not result.ok
    assert "allowlist" in result.error


# ---------------------------------------------------------------------------
# Probe writes adapter_status + emits event
# ---------------------------------------------------------------------------

def test_probe_writes_adapter_status_row(tmp_path: Path) -> None:
    cid = _register(tmp_path, "tool1", files={"run.sh": "#!/bin/sh\necho hi\n"})
    report = probe(tmp_path, cid)
    assert report.healthy
    assert report.adapter == "cli"

    conn = sqlite3.connect(tmp_path / "memory" / "state" / "shiroe.sqlite")
    try:
        row = conn.execute(
            "SELECT adapter, enforcement_level, last_health_check, failure_reason "
            "FROM adapter_status WHERE adapter=?",
            (report.adapter,),
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    adapter, level, checked_at, reason = row
    assert adapter == "cli"
    assert level == "A"
    assert checked_at
    assert reason is None


def test_probe_updates_existing_row(tmp_path: Path) -> None:
    cid = _register(tmp_path, "tool2", files={"run.sh": "#!/bin/sh\necho hi\n"})
    r1 = probe(tmp_path, cid)
    r2 = probe(tmp_path, cid)

    conn = sqlite3.connect(tmp_path / "memory" / "state" / "shiroe.sqlite")
    try:
        (n,) = conn.execute(
            "SELECT COUNT(*) FROM adapter_status WHERE adapter=?",
            (r1.adapter,),
        ).fetchone()
    finally:
        conn.close()
    assert n == 1


def test_probe_emits_hash_chained_event(tmp_path: Path) -> None:
    cid = _register(tmp_path, "tool3", files={"run.sh": "#!/bin/sh\necho hi\n"})
    probe(tmp_path, cid)

    log = EventLog(tmp_path)
    events = list(log.iter_events())
    types = {e["event_type"] for e in events}
    assert "adapter.probed" in types
    log.verify_chain()  # chain still valid after adapter.probed appended


def test_probe_of_unknown_capability_records_unhealthy(tmp_path: Path) -> None:
    (tmp_path / "memory").mkdir()
    report = probe(tmp_path, "cli:nope")
    assert not report.healthy
    assert "no version record" in (report.failure_reason or "")

    conn = sqlite3.connect(tmp_path / "memory" / "state" / "shiroe.sqlite")
    try:
        row = conn.execute(
            "SELECT failure_reason FROM adapter_status WHERE adapter='unknown'"
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row[0]  # failure_reason recorded


# ---------------------------------------------------------------------------
# No silent substitution
# ---------------------------------------------------------------------------

def test_unhealthy_adapter_never_swaps_silently(tmp_path: Path) -> None:
    """When probing surfaces an unhealthy report, the row records the failure
    truthfully; no other adapter's name is written in its place."""
    (tmp_path / "memory").mkdir()
    report = probe(tmp_path, "cli:nope")

    conn = sqlite3.connect(tmp_path / "memory" / "state" / "shiroe.sqlite")
    try:
        rows = conn.execute(
            "SELECT adapter, failure_reason FROM adapter_status"
        ).fetchall()
    finally:
        conn.close()
    # Exactly one row, its adapter is the honest 'unknown' marker.
    assert len(rows) == 1
    adapter, failure = rows[0]
    assert adapter == "unknown"
    assert failure


def test_adapter_probed_event_type_is_whitelisted() -> None:
    assert "adapter.probed" in events_mod._KNOWN_EVENT_TYPES
    assert "adapter.unhealthy" in events_mod._KNOWN_EVENT_TYPES
