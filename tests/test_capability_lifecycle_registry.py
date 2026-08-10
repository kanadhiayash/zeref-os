"""SHR-051 / 052 / 053 gate — capability lifecycle enforcement mid-run and
registry snapshot propagation.

Acceptance: digest drift and revocation block the *next action in an
active run*, not just the next `start`. And the registry snapshot
(`registry/capabilities.json`) surfaces `digest` and `lifecycle_state`
for every stored capability.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

from shiroe.adapters.capabilities.base import AdapterResult
from shiroe.capabilities import (
    approve,
    inspect_source,
    register_discovery,
    revoke,
)
from shiroe.capabilities.discovery import DiscoveredCapability
from shiroe.capabilities.store import CapabilityStore
from shiroe.policy import AutonomyMode
from shiroe.registry import generate_all
from shiroe.runtime import Supervisor
from shiroe.teams import compile_team

REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Fixture (mirrors tests/test_vnext_pr8_supervisor.py::_seed)
# ---------------------------------------------------------------------------

def _seed(tmp_path: Path) -> tuple[str, dict[str, Path], dict[str, str]]:
    """Compile a real build-mission run and return (run_id, source paths per
    seat, capability_id per seat)."""
    for name in ("missions", "policies"):
        shutil.copytree(REPO_ROOT / name, tmp_path / name)

    (tmp_path / ".shiroe" / "policy").mkdir(parents=True)
    (tmp_path / ".shiroe" / "policy" / "defaults.json").write_text(
        json.dumps({"allow": ["subprocess", "memory.write"]}),
        encoding="utf-8",
    )

    src_paths: dict[str, Path] = {}
    cap_ids: dict[str, str] = {}
    for name, provides in (
        ("architect", ["architecture-planning", "dependency-analysis"]),
        ("coder", ["code-editing", "test-execution"]),
        ("reviewer", ["code-review", "verification"]),
    ):
        src = tmp_path / "source" / name
        src.mkdir(parents=True)
        (src / "SKILL.md").write_text(f"# {name}\n", encoding="utf-8")
        src_paths[name] = src
        d = DiscoveredCapability(
            adapter="generic", root="<home>/skills", path=src, kind="skill",
        )
        cid = register_discovery(tmp_path, d, trust=inspect_source(src))
        cap_ids[name] = cid
        # inject provides so the resolver can match seats
        store = CapabilityStore(tmp_path)
        try:
            row = store.conn.execute(
                "SELECT id, manifest FROM capability_versions "
                "WHERE capability_id=? ORDER BY created_at DESC LIMIT 1",
                (cid,),
            ).fetchone()
            manifest = json.loads(row[1])
            manifest["provides"] = provides
            store.conn.execute(
                "UPDATE capability_versions SET manifest=? WHERE id=?",
                (json.dumps(manifest, sort_keys=True), row[0]),
            )
            store.conn.commit()
        finally:
            store.close()
        approve(tmp_path, cid)

    plan = compile_team(tmp_path, task_id="task_e2e", mission_id="build",
                        policy_id="balanced", active_harness="claude-code")
    return plan.run_id, src_paths, cap_ids


def _assignments(tmp_path: Path, run_id: str) -> dict[str, str]:
    """seat_id → capability_id map for the compiled run."""
    conn = sqlite3.connect(tmp_path / "memory" / "state" / "shiroe.sqlite")
    try:
        rows = conn.execute(
            "SELECT seat_id, capability_id FROM team_assignments WHERE run_id=?",
            (run_id,),
        ).fetchall()
    finally:
        conn.close()
    return dict(rows)


# ---------------------------------------------------------------------------
# SHR-052 — mid-run digest drift blocks the next step
# ---------------------------------------------------------------------------

def test_mid_run_digest_drift_blocks_next_step(tmp_path: Path) -> None:
    run_id, src_paths, _ = _seed(tmp_path)
    assign = _assignments(tmp_path, run_id)

    # The second-step seat is 'implementer' (build.yaml execution_sequence).
    # After step 1 passes, mutate the second seat's on-disk source so its
    # digest drifts — the next _invoke_step must refuse.
    victim_seat = "implementer"
    # The capability whose source we mutate is the one registered as 'coder'
    # (it provides code-editing/test-execution, which matches the
    # implementer seat's requirements).
    victim_src_name = "coder"

    calls = {"n": 0}

    def _invoker(step_id, step_name, cap_id, ctx):
        calls["n"] += 1
        # Between step 1 and step 2, mutate the victim seat's source so its
        # digest no longer matches the stored one. The supervisor's per-step
        # assert_executable will then re-quarantine and refuse.
        if calls["n"] == 1:
            victim = src_paths[victim_src_name]
            (victim / "SKILL.md").write_text("# tampered\n", encoding="utf-8")
        return AdapterResult(ok=True, output=f"done:{step_name}",
                             exit_code=0,
                             metadata={"enforcement_level": "A"})

    sup = Supervisor(tmp_path, run_id, mode=AutonomyMode.policy_bound,
                     invoker=_invoker)
    try:
        result = sup.run()
    finally:
        sup.close()

    assert result.state == "PAUSED_PERMISSION"
    assert "capability gate" in (result.paused_reason or "").lower()
    # Exactly one step actually ran; the second was refused BEFORE its
    # invoker call — proving the block happened on the next action in
    # an already-running run, not at start.
    assert calls["n"] == 1

    # And the store snapped the drifted capability back to quarantined.
    store = CapabilityStore(tmp_path)
    try:
        row = store.get(assign[victim_seat])
    finally:
        store.close()
    assert row["lifecycle"] == "quarantined", (
        f"expected quarantined after drift, got {row['lifecycle']!r}"
    )


# ---------------------------------------------------------------------------
# SHR-053 — mid-run revocation blocks the next step
# ---------------------------------------------------------------------------

def test_mid_run_revocation_blocks_next_step(tmp_path: Path) -> None:
    run_id, _, _ = _seed(tmp_path)
    assign = _assignments(tmp_path, run_id)
    # implementer seat runs second in build.yaml execution_sequence
    victim_cap = assign["implementer"]

    calls = {"n": 0}

    def _invoker(step_id, step_name, cap_id, ctx):
        calls["n"] += 1
        # After the first step succeeds, revoke the capability the next
        # step depends on. The supervisor's per-step gate must refuse.
        if calls["n"] == 1:
            revoke(tmp_path, victim_cap)
        return AdapterResult(ok=True, output=f"done:{step_name}",
                             exit_code=0,
                             metadata={"enforcement_level": "A"})

    sup = Supervisor(tmp_path, run_id, mode=AutonomyMode.policy_bound,
                     invoker=_invoker)
    try:
        result = sup.run()
    finally:
        sup.close()

    assert result.state == "PAUSED_PERMISSION"
    assert "capability gate" in (result.paused_reason or "").lower()
    assert calls["n"] == 1

    # And the store confirms the terminal state.
    store = CapabilityStore(tmp_path)
    try:
        row = store.get(victim_cap)
    finally:
        store.close()
    assert row["lifecycle"] == "revoked"


# ---------------------------------------------------------------------------
# SHR-051 — registry snapshot carries digest + lifecycle_state per entry
# ---------------------------------------------------------------------------

def test_registry_capabilities_snapshot_includes_digest_and_lifecycle_state(
    tmp_path: Path,
) -> None:
    # Seed three capabilities, approve one, revoke one, leave one quarantined.
    for name in ("alpha", "beta", "gamma"):
        src = tmp_path / "source" / name
        src.mkdir(parents=True)
        (src / "SKILL.md").write_text(f"# {name}\n", encoding="utf-8")
        d = DiscoveredCapability(adapter="generic", root="<home>/skills",
                                 path=src, kind="skill")
        register_discovery(tmp_path, d, trust=inspect_source(src))

    approve(tmp_path, "generic:alpha")
    revoke(tmp_path, "generic:beta")
    # gamma stays quarantined

    generate_all(tmp_path)
    data = json.loads((tmp_path / "registry" / "capabilities.json").read_text())
    entries = {e["id"]: e for e in data["capabilities"]}
    assert set(entries) == {"generic:alpha", "generic:beta", "generic:gamma"}

    for entry in entries.values():
        assert "digest" in entry and entry["digest"], entry
        assert "lifecycle_state" in entry and entry["lifecycle_state"], entry

    assert entries["generic:alpha"]["lifecycle_state"] == "approved"
    assert entries["generic:beta"]["lifecycle_state"] == "revoked"
    assert entries["generic:gamma"]["lifecycle_state"] == "quarantined"
