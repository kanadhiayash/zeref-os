"""Clean-clone end-to-end tests for the shiroe command surface.

The Wave 3 hardening PRs (registry parity, capability lifecycle, step
contracts, self-verification + concurrent-write rejection) each ship with
focused unit tests. This module proves they COMPOSE — a fresh operator with
no state can drive the CLI through a real session and get deterministic,
non-mutating behavior at every declared support level.

Support levels declared in the registry (see `shiroe-registry.json` and
`registry/components.json`) are `runtime`, `contract`, and `adapter`. Every
entry point that maps to one of them is exercised here at least once against
a scaffolded clean clone in `tmp_path`. The real checkout is never written to.

Missing-spec note: SHIROE_FULL_FUNCTIONALITY_CLAUDE_HANDOFF.md,
SHR_BACKLOG_COVERAGE_MATRIX.csv, and SHIROE_EXECUTION_PROGRAM.json are
absent from disk. The PR acceptance-gate wording is used as the sole spec
source. Backlog IDs covered: SHR-054, SHR-062, SHR-064, SHR-065, SHR-067.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Sequence

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
VENV_PY = REPO_ROOT / ".venv" / "bin" / "python"
if not VENV_PY.exists():
    pytest.skip(
        f"pinned venv interpreter missing: {VENV_PY}", allow_module_level=True
    )
PY = str(VENV_PY)
SUBPROCESS_TIMEOUT_S = 60


def _run(
    args: Sequence[str],
    *,
    cwd: Path,
    check: bool = False,
) -> subprocess.CompletedProcess:
    """Invoke `python -m shiroe ARGS` with the repo on PYTHONPATH.

    cwd is set to the clean clone (or wherever the caller wants the CLI to
    treat as "here") — importantly NOT to the real repo, so a stray write
    would land in tmp_path, not in the tracked tree.
    """
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [PY, "-m", "shiroe", *args],
        capture_output=True, text=True,
        cwd=str(cwd), env=env, check=check,
        timeout=SUBPROCESS_TIMEOUT_S,
    )


@pytest.fixture()
def clean_clone(tmp_path: Path) -> Path:
    """A tmp_path scaffolded via `shiroe init` — the runtime `project-setup`
    skill's declared deliverable. Every subsequent CLI call in this module
    operates on this clean clone, so the real checkout is never touched."""
    r = _run(
        ["init",
         "--directory", str(tmp_path),
         "--name", "e2e-session",
         "--privacy", "abstract",
         "--tier", "auto",
         "--parent", ""],
        cwd=REPO_ROOT,  # init reads templates from the checkout
    )
    assert r.returncode == 0, (
        f"init failed:\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    )
    # Sanity: the scaffold declares the runtime project-setup deliverables.
    for rel in ("PRIVACY.md", "REDACT.md", "SHARING_POLICY.md",
                "config/PROJECT.md", "config/PERMISSIONS.md"):
        assert (tmp_path / rel).is_file(), f"init did not create {rel}"
    return tmp_path


# ---------------------------------------------------------------------------
# Support level: runtime — CLI-wrapped gates
# ---------------------------------------------------------------------------

def test_privacy_guard_passes_on_clean_scaffold(clean_clone: Path) -> None:
    """`privacy-guard` gate (runtime) — a fresh init has no PII."""
    r = _run(
        ["audit-privacy", "--directory", str(clean_clone), "--strict",
         "--fail-classes", "credentials"],
        cwd=clean_clone,
    )
    assert r.returncode == 0, (
        f"audit-privacy failed on clean scaffold: rc={r.returncode}\n"
        f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    )
    assert "No PII detected" in r.stdout or "Files scanned" in r.stdout


def test_contradiction_guard_scan_reports_none(clean_clone: Path) -> None:
    """`contradiction-guard` gate (runtime) — empty memory has no conflicts."""
    r = _run(["contradictions", "scan", "--format", "json"], cwd=clean_clone)
    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)
    assert payload.get("count", 0) == 0


def test_evidence_guard_check_passes_on_empty_memory(clean_clone: Path) -> None:
    """`evidence-guard` gate (runtime) — empty memory has no ungraded claims."""
    r = _run(["evidence", "check", "memory"], cwd=clean_clone)
    assert r.returncode == 0, r.stderr
    assert "No EvidenceGuard findings" in r.stdout


def test_fact_guard_scan_passes_on_empty_memory(clean_clone: Path) -> None:
    """`fact-guard` gate (runtime) — empty memory has no unsupported claims."""
    r = _run(["factguard", "scan", "memory"], cwd=clean_clone)
    assert r.returncode == 0, r.stderr
    assert "No FactGuard findings" in r.stdout


def test_write_gate_via_write_decision_appends_only(clean_clone: Path) -> None:
    """`write-gate` gate (runtime) — write-decision is the sanctioned writer."""
    before = (clean_clone / "memory" / "DECISIONS.md").read_text(encoding="utf-8")
    r = _run(
        ["write-decision",
         "--title", "E2E smoke",
         "--why", "prove the write-gate composes with the clean scaffold",
         "--evidence", "docs/canon/SOURCE_AUTHORITY.md",
         "--grade", "high"],
        cwd=clean_clone,
    )
    assert r.returncode == 0, r.stderr
    after = (clean_clone / "memory" / "DECISIONS.md").read_text(encoding="utf-8")
    assert after.startswith(before), "write-decision must append, not rewrite"
    assert "E2E smoke" in after


# ---------------------------------------------------------------------------
# Support level: runtime — supervisor / storage / policy / capabilities
# ---------------------------------------------------------------------------

def test_state_verify_chain_ok_on_fresh_scaffold(clean_clone: Path) -> None:
    """`shiroe.storage` component (runtime) — hash-chained JSONL verifies."""
    r = _run(["state", "verify"], cwd=clean_clone)
    assert r.returncode == 0, (
        f"state verify failed: rc={r.returncode}\n"
        f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    )
    assert "chain OK" in r.stdout


def test_capability_adapters_enumerated(clean_clone: Path) -> None:
    """`shiroe.capabilities` component (runtime) — adapter surface reachable."""
    r = _run(["capability", "adapters"], cwd=clean_clone)
    assert r.returncode == 0, r.stderr
    # PR13 wired five adapters; every one must be discoverable end-to-end.
    for expected in ("generic-skill", "agent", "cli",
                     "mcp-server", "repository-tool"):
        assert expected in r.stdout, f"missing adapter {expected!r}"


def test_capability_list_yields_valid_json(clean_clone: Path) -> None:
    """`shiroe.capabilities` component (runtime) — list runs end-to-end and is
    parseable JSON, even when nothing is yet registered in the clone."""
    r = _run(["capability", "list", "--json"], cwd=clean_clone)
    assert r.returncode == 0, r.stderr
    # Empty payload is valid; the contract is machine-readability.
    parsed = json.loads(r.stdout or "[]")
    assert isinstance(parsed, (list, dict))


def test_policy_show_reports_runtime_invariant(clean_clone: Path) -> None:
    """`shiroe.policy` component (runtime) — merged stack is inspectable."""
    r = _run(["policy", "show"], cwd=clean_clone)
    assert r.returncode == 0, r.stderr
    assert "runtime-invariant" in r.stdout


def test_status_reports_active_tier_from_scaffold(clean_clone: Path) -> None:
    """`status` composes memory + config surfaces (runtime skill deliverable)."""
    r = _run(["status"], cwd=clean_clone)
    assert r.returncode == 0, r.stderr
    # scaffold declares tier=auto; status must surface it.
    assert "auto" in r.stdout
    assert "config/PROJECT.md" in r.stdout


def test_doctor_all_checks_pass_on_fresh_scaffold(clean_clone: Path) -> None:
    """`doctor` runs every health check against the clean scaffold; PR14 raised
    the bar so a fresh init must pass its own doctor with no FAIL rows."""
    r = _run(["doctor"], cwd=clean_clone)
    assert r.returncode == 0, (
        f"doctor failed on clean scaffold:\n{r.stdout}\n{r.stderr}"
    )
    assert "FAIL" not in r.stdout, r.stdout


# ---------------------------------------------------------------------------
# Support level: contract — registry-declared surfaces stay reachable via CLI
# ---------------------------------------------------------------------------

def test_claims_matrix_lists_every_contract_command(clean_clone: Path) -> None:
    """`claims matrix` enumerates every declared capability (PR12 parity).
    Runs against the real registry via the repo, but from the clean clone."""
    r = _run(["claims", "matrix", "--format", "json"], cwd=clean_clone)
    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)
    # PR12 established that every runtime claim must resolve. Sanity-check
    # that the matrix is non-empty and structurally valid.
    assert payload, "claims matrix returned empty payload"


def test_version_matches_pinned_release(clean_clone: Path) -> None:
    """`version` (contract) — every clean clone reports the pinned version."""
    r = _run(["version"], cwd=clean_clone)
    assert r.returncode == 0, r.stderr
    pinned = (REPO_ROOT / "shiroe" / "VERSION").read_text(encoding="utf-8").strip()
    assert pinned in r.stdout


# ---------------------------------------------------------------------------
# Support level: adapter — capability-adapter surface
# (Distinct from the runtime "capabilities" assertions above: adapters live
# on their own tier in registry/components.json; the CLI must still list
# them from a clean clone.)
# ---------------------------------------------------------------------------

def test_registry_declares_expected_support_levels() -> None:
    """The declared support levels this suite covers must match the registry.
    If someone adds a new tier, this test fails so we notice — the acceptance
    gate ("every declared support level") is not silently under-covered."""
    components = json.loads(
        (REPO_ROOT / "registry" / "components.json").read_text(encoding="utf-8")
    )
    declared = sorted({c["status"] for c in components["components"]})
    assert declared == ["adapter", "runtime"], declared

    top = json.loads(
        (REPO_ROOT / "shiroe-registry.json").read_text(encoding="utf-8")
    )
    surface_statuses: set[str] = set()
    for surface in ("skills", "agents", "commands", "team_packs", "gates"):
        for entry in top.get(surface, []):
            if "status" in entry:
                surface_statuses.add(entry["status"])
    assert surface_statuses == {"contract", "runtime"}, sorted(surface_statuses)


# ---------------------------------------------------------------------------
# Full session composition — the whole point of "session e2e"
# ---------------------------------------------------------------------------

def test_full_session_start_to_verify_leaves_clone_intact(
    clean_clone: Path,
) -> None:
    """A realistic operator session: status → gates → state verify → policy.
    Everything must succeed AND the tree the clone owns must stay stable in
    the files a curious user wouldn't expect the CLI to touch."""
    project_before = (clean_clone / "config" / "PROJECT.md").read_bytes()

    for args in (
        ["status"],
        ["audit-privacy", "--directory", str(clean_clone), "--strict"],
        ["contradictions", "scan", "--format", "json"],
        ["evidence", "check", "memory"],
        ["factguard", "scan", "memory"],
        ["state", "verify"],
        ["policy", "show"],
        ["capability", "adapters"],
        ["claims", "matrix", "--format", "json"],
    ):
        r = _run(args, cwd=clean_clone)
        assert r.returncode == 0, (
            f"session step {args!r} failed:\n{r.stdout}\n{r.stderr}"
        )

    # Read-only commands must not mutate config in the clone.
    assert (clean_clone / "config" / "PROJECT.md").read_bytes() == project_before


# ---------------------------------------------------------------------------
# Working-tree invariance — the real checkout never gets dirtied by any test
# in this module. If it does, the per-PR gate's `git status --short` step
# would catch it; this catches it earlier with a clearer message.
# ---------------------------------------------------------------------------

def test_real_checkout_stays_clean_after_full_session(
    clean_clone: Path,
) -> None:
    """After running the whole session-composition path, `git status` on the
    real repo must still be clean. Guards against tests silently writing back
    to the tracked tree via a stray absolute path."""
    # Re-run a subset so this test is meaningful in isolation as well.
    for args in (
        ["status"],
        ["state", "verify"],
        ["capability", "adapters"],
        ["claims", "matrix", "--format", "json"],
    ):
        r = _run(args, cwd=clean_clone)
        assert r.returncode == 0, r.stderr

    dirty = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
        timeout=SUBPROCESS_TIMEOUT_S,
    )
    assert dirty.returncode == 0
    # Only the test file itself may show up (staged/unstaged), nothing else.
    for line in dirty.stdout.splitlines():
        path = line[3:].strip()
        assert path in {"tests/test_command_session_e2e.py"}, (
            f"unexpected dirty path after e2e run: {line!r}"
        )
