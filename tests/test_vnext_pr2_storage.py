"""vNext PR 2 gate tests — canonical storage (ADR-0001).

Covers migration idempotency, hash-chained event envelope, tamper detection,
replay rebuild, generated views, and the canonical-store wording regression.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from shiroe.storage import EventEnvelope, EventLog, StateDB
from shiroe.storage import events as events_mod
from shiroe.storage import views as views_mod

REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Migrations
# ---------------------------------------------------------------------------

def _schema_dump(conn: sqlite3.Connection) -> str:
    rows = conn.execute(
        "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY name"
    ).fetchall()
    return "\n".join(r[0] for r in rows)


def test_migration_creates_current_baseline_tables_only(tmp_path: Path) -> None:
    db = StateDB(tmp_path)
    applied = db.migrate()
    tables = set(db.tables())
    expected = {
        "memory_records", "memory_sources", "memory_relations", "memory_events",
        "capabilities", "capability_versions",
        "capability_permissions", "adapter_status",
        "work_graphs", "work_nodes", "work_edges", "work_attempts",
        "approval_requests", "approval_advice", "nodes", "node_leases", "transfers",
    }
    obsolete = {
        "contradictions", "evidence_reviews", "team_assignments",
        "execution_steps", "team_runs", "missions", "capability_benchmarks",
        "evaluator_runs", "codec_profiles",
    }
    assert expected | {"schema_version"} == tables
    assert obsolete.isdisjoint(tables)
    assert applied == ["m0100_current"]
    columns = {row[1] for row in db.connect().execute("PRAGMA table_info(memory_records)")}
    assert "tags_json" in columns
    assert db.schema_version() == 100
    assert not (tmp_path / "memory" / "state" / "backups").exists()


def test_migration_is_idempotent(tmp_path: Path) -> None:
    db = StateDB(tmp_path)
    first = db.migrate()
    dump_before = _schema_dump(db.connect())
    second = db.migrate()
    dump_after = _schema_dump(db.connect())
    assert first, "first run should apply at least one migration"
    assert second == [], "second run must be a no-op"
    assert dump_before == dump_after


# ---------------------------------------------------------------------------
# Event envelope + hash chain
# ---------------------------------------------------------------------------

def _log(tmp_path: Path, conn: sqlite3.Connection) -> EventLog:
    (tmp_path / "REDACT.md").write_text("# minimal\n")
    return EventLog(tmp_path, redact_md=tmp_path / "REDACT.md", mirror_conn=conn)


def test_event_append_validates_schema(tmp_path: Path) -> None:
    db = StateDB(tmp_path); db.migrate()
    log = _log(tmp_path, db.connect())

    env = log.append(EventEnvelope(event_type="memory.written", actor="test",
                                   payload={"k": "v"}))
    assert env["schema"] == events_mod.SCHEMA_ID
    assert env["hash"].startswith("sha256:")
    assert env["previous_hash"] == "sha256:0"

    with pytest.raises(events_mod.EventValidationError):
        log.append(EventEnvelope(event_type="totally.made.up",
                                 actor="test", payload={}))


def test_hash_chain_verifies_and_detects_tamper(tmp_path: Path) -> None:
    db = StateDB(tmp_path); db.migrate()
    log = _log(tmp_path, db.connect())
    for i in range(5):
        log.append(EventEnvelope(event_type="memory.written", actor="test",
                                 payload={"i": i}))
    log.verify_chain()  # clean

    files = list((tmp_path / "memory" / "events").rglob("events.jsonl"))
    assert files
    lines = files[0].read_text(encoding="utf-8").splitlines()
    env = json.loads(lines[2])
    env["payload"]["i"] = 999
    lines[2] = json.dumps(env, sort_keys=True, separators=(",", ":"))
    files[0].write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(events_mod.HashChainError):
        log.verify_chain()


def test_events_are_redacted_before_disk(tmp_path: Path) -> None:
    db = StateDB(tmp_path); db.migrate()
    log = _log(tmp_path, db.connect())
    env = log.append(EventEnvelope(
        event_type="memory.written", actor="test",
        payload={"note": "contact ada.lovelace@example.com about token sk-live-1234567890abcdef"},
    ))
    disk = list((tmp_path / "memory" / "events").rglob("events.jsonl"))[0].read_text("utf-8")
    # Whatever scrub does to shape the string, the raw email + provider-shaped
    # token must not appear verbatim.
    assert "ada.lovelace@example.com" not in disk
    assert "sk-live-1234567890abcdef" not in disk
    # Envelope still valid.
    events_mod.validate_envelope(env)


def test_replay_rebuilds_memory_events(tmp_path: Path) -> None:
    db = StateDB(tmp_path); db.migrate()
    conn = db.connect()
    log = _log(tmp_path, conn)
    for i in range(4):
        log.append(EventEnvelope(event_type="memory.written", actor="t",
                                 payload={"i": i}))
    (n_before,) = conn.execute("SELECT COUNT(*) FROM memory_events").fetchone()
    assert n_before == 4

    conn.execute("DELETE FROM memory_events"); conn.commit()
    n = log.replay_into(conn)
    (after,) = conn.execute("SELECT COUNT(*) FROM memory_events").fetchone()
    assert n == 4 and after == 4


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

def test_views_carry_banner_and_are_derived(tmp_path: Path) -> None:
    db = StateDB(tmp_path); db.migrate()
    conn = db.connect()

    written = views_mod.render_all(tmp_path, conn)
    assert len(written) == 8
    for path in written:
        text = path.read_text(encoding="utf-8")
        assert text.startswith("<!-- GENERATED BY SHIROE."), path

    # Hand-edit a view; regenerating must overwrite it (view is derived).
    target = written[0]
    target.write_text("tampered", encoding="utf-8")
    views_mod.render_all(tmp_path, conn)
    assert target.read_text(encoding="utf-8").startswith("<!-- GENERATED BY SHIROE.")


# ---------------------------------------------------------------------------
# Canonical-store wording regression
# ---------------------------------------------------------------------------

def test_no_stale_markdown_is_canonical_wording() -> None:
    banned = "Markdown stays canonical"
    offenders: list[str] = []
    for path in (REPO_ROOT / "shiroe").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if banned in text:
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, (
        "canonical-store contradiction not fully purged; still says "
        f"{banned!r} in: {offenders}"
    )
