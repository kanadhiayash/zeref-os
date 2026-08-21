"""CLI adapter — invoke an approved CLI capability via subprocess.

Enforcement is Level A for launch control: Shiroe owns the subprocess
invocation and policy gate. This is not an OS/network sandbox; a child process
can still perform syscalls the operating system permits.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from shiroe.adapters.capabilities.base import (
    AdapterResult,
    EnforcementLevel,
    HealthReport,
)
from shiroe.capabilities.store import CapabilityStore
from shiroe.policy import Action, ActionKind, AutonomyMode, Verdict, evaluate, load_policy_stack


class CLIAdapter:
    name = "cli"
    enforcement_level = EnforcementLevel.embedded
    supported_types: tuple[str, ...] = ("cli", "script")

    def health(self) -> HealthReport:
        return HealthReport(
            adapter=self.name,
            detected_version="1.0",
            enforcement_level=self.enforcement_level,
            supported_features=("subprocess", "policy_gated", "timeout"),
            healthy=True,
            supported_types=self.supported_types,
        )

    def invoke(self, *, capability_id: str, action: str, inputs: dict,
               permissions: dict | None = None,
               timeout_s: int | None = None) -> AdapterResult:
        root = inputs.get("root")
        if root is None:
            return AdapterResult(ok=False, error="missing 'root' input")

        if "command" in inputs:
            return AdapterResult(
                ok=False,
                error="inputs.command is not allowed; execution uses the approved manifest command",
            )

        # 1. Resolve approved manifest and source location.
        store = CapabilityStore(root)
        try:
            row = store.conn.execute(
                "SELECT manifest, source_location FROM capability_versions "
                "WHERE capability_id=? ORDER BY created_at DESC LIMIT 1",
                (capability_id,),
            ).fetchone()
        finally:
            store.close()
        if row is None:
            return AdapterResult(
                ok=False, error=f"no version record for {capability_id!r}",
            )
        manifest = json.loads(row[0])
        # ponytail: source_location + entrypoint.command are project-relative
        # (REDACT scrubs absolute paths from event log). Resolve here.
        root_path = Path(root)
        raw_src = Path(row[1])
        source = raw_src if raw_src.is_absolute() else (root_path / raw_src).resolve()

        # 2. Resolve command from the approved manifest only.
        raw_cmd = manifest.get("entrypoint", {}).get("command")
        if not isinstance(raw_cmd, list) or not raw_cmd or not all(isinstance(x, str) for x in raw_cmd):
            return AdapterResult(
                ok=False,
                error="capability manifest entrypoint.command must be a non-empty list of strings",
            )
        argv: list[str] = []
        for i, token in enumerate(raw_cmd):
            token_path = Path(token)
            if i == 0 and not token_path.is_absolute() and (root_path / token_path).exists():
                argv.append(str((root_path / token_path).resolve()))
            else:
                argv.append(token)
        raw_args = inputs.get("args", ())
        if raw_args:
            contract = manifest.get("entrypoint", {}).get("args")
            if not isinstance(contract, list):
                return AdapterResult(
                    ok=False,
                    error="inputs.args are not allowed unless manifest entrypoint.args declares an argument contract",
                )
            if not isinstance(raw_args, (list, tuple)) or not all(isinstance(x, str) for x in raw_args):
                return AdapterResult(ok=False, error="inputs.args must be a list of strings")
            argv.extend(raw_args)

        # 3. Policy check — always. Every subprocess flows through here.
        stack = load_policy_stack(root)
        mode = AutonomyMode(inputs.get("autonomy_mode", "auto-safe"))
        decision = evaluate(
            Action(ActionKind.subprocess,
                   target=" ".join(argv),
                   context={"capability_id": capability_id}),
            stack, mode=mode,
        )
        if decision.verdict is not Verdict.allow:
            return AdapterResult(
                ok=False,
                error=f"policy {decision.verdict.value} at {decision.deciding_layer}: {decision.reason}",
                metadata={"policy": {
                    "verdict": decision.verdict.value,
                    "reason": decision.reason,
                    "deciding_layer": decision.deciding_layer,
                }},
            )

        # 4. Command allowlist (from declared permissions)
        allow_commands = _string_list(permissions, "allow_commands")
        if allow_commands and argv[0] not in allow_commands:
            return AdapterResult(
                ok=False,
                error=f"command {argv[0]!r} not in capability allowlist "
                      f"{sorted(allow_commands)}",
            )

        # 5. Execute
        try:
            completed = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=timeout_s or 60,
                cwd=str(source.parent if source.is_file() else source),
                shell=False,
            )
        except subprocess.TimeoutExpired as e:
            return AdapterResult(
                ok=False, error=f"timeout after {e.timeout}s",
                stderr_tail=(e.stderr or "")[-2000:] if isinstance(e.stderr, str) else None,
            )
        except FileNotFoundError as e:
            return AdapterResult(ok=False, error=f"executable not found: {e}")

        return AdapterResult(
            ok=completed.returncode == 0,
            output=_try_json(completed.stdout),
            exit_code=completed.returncode,
            stderr_tail=completed.stderr[-2000:] if completed.stderr else None,
            metadata={
                "argv": argv,
                "enforcement_level": self.enforcement_level.value,
                "policy": {"verdict": decision.verdict.value,
                           "deciding_layer": decision.deciding_layer},
            },
        )


def _try_json(text: str) -> Any:
    text = (text or "").strip()
    if not text:
        return ""
    if text.startswith(("{", "[")):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text
    return text


def _string_list(permissions: dict | None, key: str) -> list[str]:
    if not permissions:
        return []
    raw = permissions.get(key) or []
    return [str(x) for x in raw]
