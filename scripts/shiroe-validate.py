#!/usr/bin/env python3
"""Validate the current Shiroe runtime surface."""

from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

EXPECTED_COMMANDS = {
    "init",
    "status",
    "plan",
    "run",
    "approve",
    "memory",
    "node",
    "verify",
    "handoff",
    "doctor",
    "policy",
    "capability",
    "state",
    "version",
}

HARNESS_SHIMS = {
    "CLAUDE.md",
    "CODEX.md",
    "GEMINI.md",
    "LLAMA.md",
    ".cursor/rules/shiroe.mdc",
    ".windsurfrules",
    ".aider.conf.yml.example",
}

RETIRED_PATHS = (
    "skills",
    "agents",
    "commands",
    "missions",
    "loops",
    "team" + "-packs",
    "_shared",
    "policies",
    "team",
    "references/target-model-profiles",
    "memory/" + "patterns",
    "memory/" + "hot.md",
    "memory/" + "index.md",
)

FRESH_INIT_REQUIRED = (
    "config/PROJECT.md",
    "PRIVACY.md",
    "REDACT.md",
    "SHARING_POLICY.md",
    ".shiroe/policy/defaults.json",
    "memory/state/shiroe.sqlite",
)

DOCS_WITH_COMMANDS = (
    "README.md",
    "QUICKSTART.md",
    "INSTALL.md",
    "docs/GETTING_STARTED.md",
    "docs/HARNESS_MATRIX.md",
    "docs/MEMORY_WRITES.md",
    "docs/DOCTOR.md",
    "docs/wiki/Memory-Model.md",
    "memory/README.md",
    "references/shiroe-qa-gate.md",
    "references/shiroe-safety-principles.md",
    "references/harness-translation-map.md",
    "references/shared-anti-hallucination.md",
)

GROUPS = {
    "approve": {"list", "decide", "advise"},
    "capability": {"list", "show", "doctor", "invoke"},
    "memory": {"write", "recall", "list", "show", "supersede", "archive", "views"},
    "node": {"list", "discover", "register", "inspect", "probe", "trust", "untrust", "doctor", "worker-run"},
    "policy": {"show", "authorize"},
    "state": {"migrate", "verify", "export", "backup", "rollback", "replay"},
}


def main() -> int:
    errors: list[str] = []
    checks: list[str] = []

    _check_core_scope(errors, checks)
    _check_retired_paths(errors, checks)
    _check_approval_advisor_boundary(errors, checks)
    _check_cli_commands(errors, checks)
    _check_schema(errors, checks)
    _check_fresh_init(errors, checks)
    _check_policy_default_deny(errors, checks)
    _check_harness_shims(errors, checks)
    _check_doc_commands(errors, checks)
    _check_status_labels(errors, checks)

    print(f"Shiroe validator - {ROOT}")
    for check in checks:
        print(f"PASS {check}")
    if errors:
        print("\nErrors:")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("\nValidation passed")
    return 0


def _check_core_scope(errors: list[str], checks: list[str]) -> None:
    if not (ROOT / "docs" / "architecture" / "CORE_SCOPE.md").is_file():
        errors.append("missing docs/architecture/CORE_SCOPE.md")
    else:
        checks.append("CORE_SCOPE present")


def _check_retired_paths(errors: list[str], checks: list[str]) -> None:
    present = [path for path in RETIRED_PATHS if (ROOT / path).exists()]
    if present:
        errors.append(f"retired runtime paths present: {', '.join(present)}")
    else:
        checks.append("retired runtime paths absent")


def _check_approval_advisor_boundary(errors: list[str], checks: list[str]) -> None:
    agent_dir = ROOT / "shiroe" / "agents"
    allowed = {"__init__.py", "approval_advisor.py"}
    actual = {path.name for path in agent_dir.iterdir() if path.is_file() and path.suffix == ".py"}
    extra = actual - allowed
    missing = allowed - actual
    if extra or missing:
        errors.append(f"approval advisor boundary mismatch: extra={sorted(extra)} missing={sorted(missing)}")
    else:
        checks.append("approval advisor is sole runtime agent")


def _check_cli_commands(errors: list[str], checks: list[str]) -> None:
    from shiroe.cli.main import registered_command_names

    actual = set(registered_command_names())
    if actual != EXPECTED_COMMANDS:
        errors.append(f"CLI command set mismatch: {sorted(actual)}")
    else:
        checks.append(f"CLI commands: {', '.join(sorted(actual))}")


def _check_schema(errors: list[str], checks: list[str]) -> None:
    from shiroe.migrations import latest_version
    from shiroe.storage import StateDB

    db = StateDB(ROOT)
    try:
        db.migrate()
        applied = db.schema_version()
    finally:
        db.close()
    latest = latest_version()
    if applied != latest:
        errors.append(f"schema version {applied}, expected {latest}")
    else:
        checks.append(f"schema version: {applied}")


def _check_fresh_init(errors: list[str], checks: list[str]) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "project"
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "shiroe",
                "init",
                str(target),
                "--name",
                "validator",
                "--privacy",
                "abstract",
                "--network-scope",
                "device-only",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        if result.returncode != 0:
            errors.append(f"fresh init failed: {result.stderr.strip()}")
            return
        missing = [path for path in FRESH_INIT_REQUIRED if not (target / path).exists()]
        retired = [path for path in RETIRED_PATHS if (target / path).exists()]
        if missing or retired:
            errors.append(f"fresh init surface mismatch: missing={missing} retired={retired}")
        else:
            checks.append("fresh init surface current")


def _check_policy_default_deny(errors: list[str], checks: list[str]) -> None:
    from shiroe.policy import load_policy_stack
    from shiroe.policy.autonomy import AutonomyMode
    from shiroe.policy.engine import evaluate
    from shiroe.policy.schema import Action, ActionKind, Verdict

    stack = load_policy_stack(ROOT, global_root=ROOT / "no-global-policy")
    decision = evaluate(
        Action(ActionKind.network, target="validator.default-deny.invalid"),
        stack,
        mode=AutonomyMode.policy_bound,
    )
    if decision.verdict is not Verdict.deny or decision.deciding_layer != "default-deny":
        errors.append(f"default deny probe returned {decision.verdict.value} from {decision.deciding_layer}")
    else:
        checks.append("default deny semantic probe")


def _check_harness_shims(errors: list[str], checks: list[str]) -> None:
    missing = [path for path in sorted(HARNESS_SHIMS) if not (ROOT / path).is_file()]
    if missing:
        errors.append(f"missing harness shims: {missing}")
    else:
        checks.append("harness shims current")


def _check_doc_commands(errors: list[str], checks: list[str]) -> None:
    seen: set[tuple[str, ...]] = set()
    for rel in DOCS_WITH_COMMANDS:
        path = ROOT / rel
        if not path.is_file():
            errors.append(f"missing doc command source: {rel}")
            continue
        for command in _shiroe_commands(path.read_text(encoding="utf-8")):
            help_args = _help_args(command)
            if help_args in seen:
                continue
            seen.add(help_args)
            result = subprocess.run(
                [sys.executable, "-m", "shiroe", *help_args],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )
            if result.returncode != 0:
                errors.append(f"{rel}: parser rejected {' '.join(command)}: {result.stderr.strip()}")
    if seen:
        checks.append(f"doc CLI examples parse: {len(seen)}")


def _check_status_labels(errors: list[str], checks: list[str]) -> None:
    targets = [ROOT / "shiroe-registry.json", ROOT / "registry" / "components.json"]
    hits: list[str] = []
    pattern = re.compile(r'"status"\s*:\s*"(?:contract|experimental)"|status:\s*(?:contract|experimental)', re.I)
    for target in targets:
        if not target.is_file():
            continue
        text = target.read_text(encoding="utf-8", errors="ignore")
        if pattern.search(text):
            hits.append(str(target.relative_to(ROOT)))
    if hits:
        errors.append(f"non-operational status labels present: {', '.join(hits)}")
    else:
        checks.append("no non-operational product status labels")


def _shiroe_commands(text: str) -> list[tuple[str, ...]]:
    commands: list[tuple[str, ...]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        stripped = re.sub(r"\s+#.*$", "", stripped)
        if stripped.startswith("python3 -m shiroe "):
            commands.append(tuple(shlex.split(stripped)[3:]))
        elif stripped.startswith("shiroe "):
            commands.append(tuple(shlex.split(stripped)[1:]))
    return commands


def _help_args(command: tuple[str, ...]) -> tuple[str, ...]:
    if not command:
        return ("--help",)
    first = command[0]
    if first in {"--help", "-h", "--version"}:
        return (first,)
    if first in GROUPS and len(command) > 1 and command[1] in GROUPS[first]:
        return (first, command[1], "--help")
    return (first, "--help")


if __name__ == "__main__":
    raise SystemExit(main())
