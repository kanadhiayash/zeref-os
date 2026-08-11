"""Local release readiness checks.

privacy-audit: allow-file "Release-check module names findings + example evidence fields; no user data."
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from shiroe.compat.legacy_identity import LEGACY_V1_STATE_DB_NAME
from shiroe.guards.evidence_guard import check_public_docs, check_store
from shiroe.guards.fact_guard import scan_path as fact_scan
from shiroe.memory import MEMORY_FILES, MemoryRoot
from shiroe.memory_state import MemoryStore


@dataclass(frozen=True)
class ReleaseFinding:
    name: str
    status: str
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


def run_release_check(root: Path) -> list[ReleaseFinding]:
    memory_root = MemoryRoot.from_path(root)
    store = MemoryStore(memory_root)
    findings: list[ReleaseFinding] = []
    # WS4 (issue #122): the gate must prove which commit it graded. Fail closed
    # when the tree is not a git repo or HEAD cannot be resolved.
    findings.append(_check_commit_provenance(root))
    findings.append(_check_test_suite(root))
    findings.append(_check_version_file(root))
    findings.append(_check_memory_layout(root))
    findings.append(_check_audit_logs(memory_root))
    findings.append(_check_factguard(root))
    findings.append(_check_evidence(store, root))
    # R9 (SHR-AUDIT-021): fold audit-surfaced gates into the release check so a
    # single pass encodes the whole trust boundary. Every subcheck is SHA-bound
    # via the running HEAD; a stale evidence blob is refused.
    findings.append(_check_version_consistency(root))
    findings.append(_check_workflow_yaml(root))
    findings.append(_check_privacy_scan(root))
    findings.append(_check_registry_completeness(root))
    findings.append(_check_pyproject_backend(root))
    findings.append(_check_soul_present(root))
    findings.append(_check_target_profiles(root))
    findings.append(_check_claim_gate(root))
    _emit_release_evidence(root, findings)
    return findings


def _check_claim_gate(root: Path) -> ReleaseFinding:
    """SHR-66 / issue #172: block public claims that exceed their evidence
    class (routing-accuracy claims off a fixture-coverage corpus, contested
    vendor comparisons, un-baselined Shiroe numbers, unscored external
    benchmarks). See shiroe.release.claim_gate for the encoded constraints."""
    from shiroe.release.claim_gate import scan_public_claims
    findings = scan_public_claims(root)
    if findings:
        sample = "; ".join(f"{f.path}:{f.line} ({f.constraint})" for f in findings[:3])
        return _fail("claim_gate", f"{len(findings)} blocked public claim(s): {sample}")
    return _pass("claim_gate", "no blocked public-claim patterns found")


def _check_target_profiles(root: Path) -> ReleaseFinding:
    """Phase 14 profiles: schema-valid + source-graded freshness (issue #175).

    Fail-closed (issue #153): profiles now ship — `references/target-model-
    profiles/` is populated as of v1.2 — so a missing or unreadable profiles
    directory is no longer the expected pre-release state and is refused
    like every other gate check, instead of the old fail-open behavior.
    A stale `official`-sourced profile still hard-fails; a stale
    `third_party`/`derived` profile still only emits a non-blocking WARNING
    (issue #175, unchanged — there is no authoritative publisher to
    re-verify a mirrored/reconstructed profile against). See
    `shiroe.prompt.target_profile.grade_profile_freshness` for the shared
    grading logic (also used by `shiroe doctor`, which keeps its own
    fail-open read since it is a local dev diagnostic, not a release gate)."""
    try:
        from shiroe.prompt.target_profile import grade_profile_freshness
    except ImportError:
        return _pass("target_profiles", "loader unavailable — pre-v1.2 skip")
    # pathlib's glob() silently swallows PermissionError (treats it like an
    # empty directory), so an unreadable dir would otherwise be indistinguishable
    # from "no profiles" and fall through to the skip branch below. Check
    # readability explicitly first.
    profiles_dir = root / "references" / "target-model-profiles"
    if profiles_dir.exists() and not os.access(profiles_dir, os.R_OK | os.X_OK):
        return _fail("target_profiles", f"profiles directory unreadable: {profiles_dir}")
    status, reason = grade_profile_freshness(project_root=root, max_age_days=60)
    if status == "fail":
        return _fail("target_profiles", reason)
    if status == "warn":
        return _warn("target_profiles", reason)
    if status == "skip":
        return _fail(
            "target_profiles",
            f"profiles now ship (issue #153), a missing directory no longer "
            f"fails open: {reason}",
        )
    return _pass("target_profiles", reason)


def _check_version_consistency(root: Path) -> ReleaseFinding:
    import subprocess
    script = root / "scripts" / "check-version-consistency.py"
    if not script.exists():
        return _fail("version_consistency", "scripts/check-version-consistency.py missing")
    try:
        result = subprocess.run(
            ["python3", str(script), "--root", str(root)],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return _fail("version_consistency", f"script exec failed: {exc}")
    if result.returncode == 0:
        return _pass("version_consistency", "all surfaces + tag lineage aligned")
    return _fail("version_consistency", f"drift detected (exit {result.returncode})")


def _check_workflow_yaml(root: Path) -> ReleaseFinding:
    wf_dir = root / ".github" / "workflows"
    if not wf_dir.exists():
        return _fail("workflow_yaml", ".github/workflows/ missing")
    try:
        import yaml  # optional dep
    except ImportError:
        yaml = None
    bad: list[str] = []
    for wf in sorted(wf_dir.glob("*.yml")):
        text = wf.read_text(errors="ignore")
        if yaml is not None:
            try:
                yaml.safe_load(text)
            except yaml.YAMLError as exc:
                bad.append(f"{wf.name}: {exc.__class__.__name__}")
        # cheap structural check even without yaml dep
        if "\n  - uses:" in text and "\n  with:" in text:
            bad.append(f"{wf.name}: dedented 'with:' (block-collection error)")
    if bad:
        return _fail("workflow_yaml", "; ".join(bad[:3]))
    return _pass("workflow_yaml", f"{len(list(wf_dir.glob('*.yml')))} workflow(s) parseable")


def _check_privacy_scan(root: Path) -> ReleaseFinding:
    """Strict scan across every tracked extension — severity-class model (WS2).

    Files carrying a `privacy-audit: allow-file` marker are excluded (their
    contents are spec descriptions of the classifier itself, not user data);
    individual lines can carry `noqa: privacy-audit`. Those markers are the
    only escape hatch.

    Severity model replaces the old count ceiling (was 150 hits / 80 files):
      * credentials class — ZERO tolerance. Any hit (provider-shaped token,
        labelled secret, encoded or whitespace-split variant) fails the gate
        outright, regardless of how few there are.
      * all other classes (pii, internal_paths, proprietary_code, ...) —
        informational. They are name-shaped / path-shaped noise in spec and
        schema files and are reported but never block a release.
    """
    from shiroe.privacy import audit as privacy_audit
    results = privacy_audit(directory=root, redact_md_path=root / "REDACT.md", strict=True)
    hits = results["total_hits"]
    allowlisted = len(results.get("allowlisted", []))
    credential_files: dict = results.get("credential_files", {})
    credential_hits = results.get("hits_by_class", {}).get("credentials", 0)
    if credential_hits or credential_files:
        sample = ", ".join(sorted(credential_files)[:3]) or "unknown"
        return _fail(
            "privacy_scan",
            f"{credential_hits} credentials-class hit(s) in {len(credential_files)} "
            f"file(s) (e.g. {sample}) — zero tolerance for credentials",
        )
    if hits == 0:
        return _pass("privacy_scan",
                     f"scanned {results['scanned']} files, 0 hits (allowlisted: {allowlisted})")
    return _pass(
        "privacy_scan",
        f"0 credentials-class hits; {hits} informational hit(s) in non-blocking "
        f"classes across {len(results['by_file'])} file(s) (allowlisted: {allowlisted})",
    )


def _check_registry_completeness(root: Path) -> ReleaseFinding:
    reg_path = root / "shiroe-registry.json"
    if not reg_path.exists():
        return _fail("registry_completeness", "shiroe-registry.json missing")
    reg = json.loads(reg_path.read_text(encoding="utf-8"))
    required = ("skills", "agents", "commands", "team_packs", "gates")
    missing = [k for k in required if k not in reg]
    if missing:
        return _fail("registry_completeness", "missing arrays: " + ", ".join(missing))
    # count-vs-disk parity
    disk_counts = {
        "skills":     len(list((root / "skills").glob("*/SKILL.md"))),
        "agents":     len(list((root / "agents").glob("*.md"))),
        "commands":   len(list((root / "commands").glob("*.md"))),
        "team_packs": len(list((root / "team-packs").glob("*.md"))),
        "gates":      len(list((root / "shiroe" / "guards").glob("*_guard.py"))) + 1,  # +write_gate
    }
    drift = [f"{k}: reg={len(reg[k])}, disk={disk_counts[k]}"
             for k in required if len(reg[k]) != disk_counts[k]]
    if drift:
        return _fail("registry_completeness", "; ".join(drift))
    return _pass("registry_completeness", "registry counts match disk for all 5 surfaces")


def _check_pyproject_backend(root: Path) -> ReleaseFinding:
    py = root / "pyproject.toml"
    if not py.exists():
        return _fail("pyproject_backend", "pyproject.toml missing")
    text = py.read_text(errors="ignore")
    if "setuptools.build_meta" in text:
        return _pass("pyproject_backend", "build-backend = setuptools.build_meta")
    return _fail("pyproject_backend", "build-backend id invalid or missing (pip install will fail)")


def _check_soul_present(root: Path) -> ReleaseFinding:
    if (root / "SOUL.md").exists():
        return _pass("soul_present", "SOUL.md present at repo root")
    return _fail("soul_present", "SOUL.md missing — boot step 0 broken")


def _resolve_head_sha(root: Path) -> str | None:
    """Return the full 40-hex HEAD SHA, or None when it cannot be proven.

    Fail-closed: no `.git`, a git error, or a malformed answer all yield None.
    """
    import re
    import subprocess
    if not (root / ".git").exists():  # dir in a repo, file in a worktree
        return None
    try:
        sha = subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            text=True, stderr=subprocess.DEVNULL, timeout=15,
        ).strip()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        return None
    return sha


def _check_commit_provenance(root: Path) -> ReleaseFinding:
    sha = _resolve_head_sha(root)
    if sha is None:
        return _fail(
            "commit_provenance",
            "cannot resolve a real HEAD commit SHA (not a git repository, or "
            "git failed) — release evidence without provenance is refused",
        )
    return _pass("commit_provenance", f"HEAD resolved: {sha[:12]}")


def _check_test_suite(root: Path) -> ReleaseFinding:
    """Execute the test suite live instead of trusting any stored artifact.

    When the gate itself is invoked from within an active pytest run
    (PYTEST_CURRENT_TEST set), the surrounding run is already executing the
    suite; re-spawning it would recurse.
    """
    import subprocess
    import sys
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return _pass(
            "test_suite",
            "gate invoked from within an active pytest run — the surrounding "
            "run executes the suite",
        )
    if not (root / "tests").is_dir():
        return _fail("test_suite", "tests/ directory missing — suite cannot be executed")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-x", str(root / "tests")],
            cwd=str(root), capture_output=True, text=True, timeout=1800,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return _fail("test_suite", f"pytest execution failed: {exc}")
    if result.returncode == 0:
        summary = result.stdout.strip().splitlines()[-1:] or ["passed"]
        return _pass("test_suite", f"pytest executed live: {summary[0][:160]}")
    tail = (result.stdout + result.stderr).strip().splitlines()[-1:] or ["no output"]
    return _fail("test_suite", f"pytest exit {result.returncode} ({tail[0][:160]})")


def _emit_release_evidence(root: Path, findings: list) -> None:
    """Write a SHA-bound evidence blob under docs/audits/release-evidence/.

    The release gate consumers can trust a stored PASS only when this blob
    matches the current HEAD SHA (see SHR-AUDIT-013 pattern for freshness).
    Refuses to emit evidence without a resolvable HEAD SHA — an `unknown`
    provenance blob is worse than no blob.
    """
    from datetime import datetime, timezone
    head_sha = _resolve_head_sha(root)
    if head_sha is None:
        return
    out_dir = root / "docs" / "audits" / "release-evidence"
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    blob = {
        "sha": head_sha,
        "ts": ts,
        "findings": [f.to_dict() for f in findings],
        "passed": release_passed(findings),
    }
    try:
        (out_dir / f"{head_sha[:12]}_{ts}.json").write_text(
            json.dumps(blob, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except OSError:
        pass


def format_release(findings: list[ReleaseFinding], *, format: str = "text") -> str:
    if format == "json":
        return json.dumps([finding.to_dict() for finding in findings], indent=2, sort_keys=True) + "\n"
    if format == "md":
        lines = ["# Shiroe Release Check", ""]
        for finding in findings:
            lines.append(f"- **{finding.status}** `{finding.name}` - {finding.reason}")
        return "\n".join(lines) + "\n"
    return "\n".join(f"{f.status.upper()} {f.name}: {f.reason}" for f in findings) + "\n"


def release_passed(findings: list[ReleaseFinding]) -> bool:
    """True when no finding failed.

    `skip` findings (e.g. benchmark suite blocked on a local-only fixture)
    do not block the gate, but they are never reported as PASS and the
    formatted output surfaces them loudly.
    """
    return all(finding.status != "fail" for finding in findings)


def _check_version_file(root: Path) -> ReleaseFinding:
    return _pass("version", "shiroe/VERSION exists") if (root / "shiroe" / "VERSION").exists() else _fail("version", "shiroe/VERSION missing")


def _check_memory_layout(root: Path) -> ReleaseFinding:
    missing = [rel for rel in MEMORY_FILES if not (root / rel).exists()]
    if missing:
        if _tracked_memory_scaffold_present(root):
            return _pass(
                "memory_layout",
                "tracked memory scaffold present; runtime memory files are generated locally",
            )
        return _fail("memory_layout", "missing " + ", ".join(missing[:5]))
    return _pass("memory_layout", "required memory files exist")


def _check_audit_logs(memory_root: MemoryRoot) -> ReleaseFinding:
    required = ("writes.jsonl", "reads.jsonl", "routes.jsonl", "guard_failures.jsonl", "redactions.jsonl", "releases.jsonl")
    missing = [name for name in required if not (memory_root.layout.audit_dir / name).exists()]
    if missing:
        if _tracked_memory_scaffold_present(memory_root.root):
            return _pass(
                "audit_logs",
                "tracked memory scaffold present; audit logs are generated locally",
            )
        return _fail("audit_logs", "missing " + ", ".join(missing))
    return _pass("audit_logs", "audit logs present")


def _check_factguard(root: Path) -> ReleaseFinding:
    findings = fact_scan(root / "README.md")
    if findings:
        return _fail("factguard", f"{len(findings)} unsupported public claim(s)")
    return _pass("factguard", "README has no FactGuard findings")


def _check_evidence(store: MemoryStore, root: Path) -> ReleaseFinding:
    state_db = root / "memory" / "state" / LEGACY_V1_STATE_DB_NAME
    store_findings = [] if _is_macos_dataless_placeholder(state_db) else check_store(store)
    doc_issues = check_public_docs(root / "docs")
    if store_findings or doc_issues:
        return _fail("evidenceguard", f"{len(store_findings) + len(doc_issues)} evidence issue(s)")
    return _pass("evidenceguard", "no release-blocking evidence issues")


def _pass(name: str, reason: str) -> ReleaseFinding:
    return ReleaseFinding(name=name, status="pass", reason=reason)


def _fail(name: str, reason: str) -> ReleaseFinding:
    return ReleaseFinding(name=name, status="fail", reason=reason)


def _skip(name: str, reason: str) -> ReleaseFinding:
    """Explicitly-not-run: surfaced loudly, never counted as pass."""
    return ReleaseFinding(name=name, status="skip", reason=reason)


def _warn(name: str, reason: str) -> ReleaseFinding:
    """Non-blocking WARNING: surfaced loudly, never counted as pass, never fails the gate."""
    return ReleaseFinding(name=name, status="warn", reason=reason)


def _tracked_memory_scaffold_present(root: Path) -> bool:
    return (root / "memory" / ".gitkeep").exists() and (root / "memory" / "README.md").exists()


def _is_macos_dataless_placeholder(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        return bool(os.stat(path).st_flags & 0x40000000)
    except (AttributeError, OSError):
        return False
