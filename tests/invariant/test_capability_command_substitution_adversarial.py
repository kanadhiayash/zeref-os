"""Wave 10 (1/3): shell command-substitution must never be interpreted.

The CLI adapter (`shiroe/adapters/capabilities/cli.py`) resolves `argv` from
the approved manifest's `entrypoint.command` list and executes it with
`subprocess.run(argv, shell=False, ...)`. There is no `shell=True` anywhere
in the tree (grepped). A `$(...)`/backtick payload embedded in a manifest
command argument therefore has nowhere to be interpreted: it can only reach
the child process as one inert argv element, never as a substituted shell
expression.

This file pins that property directly (an adversarial payload survives as a
literal argv string, and any side effect a real shell would have produced
from it never happens) and pins the existing override-rejection path
(`test_capability_manifest_execution_integrity.py`) against the same
payload shape, so a future switch to `shell=True` or a shell-based adapter
fails both tests immediately.
"""

from __future__ import annotations

import sys
from pathlib import Path

from shiroe.adapters.capabilities.cli import CLIAdapter
from shiroe.capabilities.inspection import inspect_source
from shiroe.capabilities.store import CapabilityStore


# A payload that, if handed to a real shell, would execute `touch` and
# substitute in the (empty) stdout of the command — the marker file would
# exist afterwards, and the literal text would evaporate.
_SUBSTITUTION_PAYLOAD = "$(touch {marker})"
_BACKTICK_PAYLOAD = "`touch {marker}`"


def _allow_subprocess(root: Path) -> None:
    import json

    policy_dir = root / ".shiroe" / "policy"
    policy_dir.mkdir(parents=True, exist_ok=True)
    (policy_dir / "defaults.json").write_text(
        json.dumps({"allow": ["subprocess"]}),
        encoding="utf-8",
    )


def _register_echo_capability(root: Path, extra_argv: list[str]) -> str:
    """Register a project-local shebang'd script whose command echoes argv[1:].

    Uses a project-relative script path and a project-relative received-file
    path so REDACT.md's ``internal_paths`` class cannot scrub argv into
    unreachability. All argv values stay project-relative.
    """
    script = root / "capabilities" / "echo_argv.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        "from pathlib import Path\n"
        "out = Path(sys.argv[1])\n"
        "out.write_text(json.dumps(sys.argv[2:]), encoding='utf-8')\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    digest = inspect_source(script).digest
    capability_id = "test.echo-argv"
    received_rel = "received.json"
    manifest = {
        "schema": "shiroe.capability/v1",
        "id": capability_id,
        "name": "Echo Argv",
        "type": "script",
        "version": "1.0.0",
        "source": {"kind": "local-file", "location": str(script)},
        "entrypoint": {
            "adapter": "cli",
            "command": [str(script), received_rel, *extra_argv],
        },
        "requires": {},
    }
    with CapabilityStore(root) as store:
        store.upsert_capability(
            capability_id=capability_id,
            name="Echo Argv",
            type_="script",
            lifecycle="active",
            digest=digest,
            manifest=manifest,
            source_kind="local-file",
            source_location=str(script),
        )
    return capability_id


def test_manifest_command_substitution_payload_is_never_shell_interpreted(tmp_path: Path) -> None:
    """A $(...) payload in the manifest command survives as an inert literal.

    If the adapter ever executed this through a shell, ``touch <marker>``
    would run and the marker file would exist while the literal ``$(...)``
    text would be gone from what the child process received. Neither happens.

    The marker path is project-relative so REDACT.md's ``internal_paths``
    class cannot rewrite it inside the persisted event payload; the shell-
    safety check that the marker file does NOT exist is the real
    invariant this test guards.
    """
    _allow_subprocess(tmp_path)
    marker_rel = "pwned-by-substitution.txt"
    marker = tmp_path / "capabilities" / marker_rel
    payload = _SUBSTITUTION_PAYLOAD.format(marker=marker_rel)
    capability_id = _register_echo_capability(tmp_path, [payload])

    result = CLIAdapter().invoke(
        capability_id=capability_id,
        action="run",
        inputs={"root": str(tmp_path), "autonomy_mode": "policy-bound"},
    )

    assert result.ok, result.error
    assert not marker.exists(), (
        "command-substitution payload produced a shell side effect: "
        "the adapter must never invoke a shell"
    )
    received = (tmp_path / "capabilities" / "received.json").read_text(encoding="utf-8")
    assert payload in received, (
        f"payload was not passed through as a literal argv element: {received!r}"
    )


def test_manifest_command_backtick_payload_is_never_shell_interpreted(tmp_path: Path) -> None:
    """Same property for the backtick substitution form."""
    _allow_subprocess(tmp_path)
    marker_rel = "pwned-by-backtick.txt"
    marker = tmp_path / "capabilities" / marker_rel
    payload = _BACKTICK_PAYLOAD.format(marker=marker_rel)
    capability_id = _register_echo_capability(tmp_path, [payload])

    result = CLIAdapter().invoke(
        capability_id=capability_id,
        action="run",
        inputs={"root": str(tmp_path), "autonomy_mode": "policy-bound"},
    )

    assert result.ok, result.error
    assert not marker.exists(), (
        "backtick substitution payload produced a shell side effect: "
        "the adapter must never invoke a shell"
    )
    received = (tmp_path / "capabilities" / "received.json").read_text(encoding="utf-8")
    assert payload in received, (
        f"payload was not passed through as a literal argv element: {received!r}"
    )


def test_invocation_override_carrying_substitution_payload_is_rejected(tmp_path: Path) -> None:
    """Even a caller-supplied `inputs.command` override is rejected outright.

    Mirrors test_cli_adapter_rejects_invocation_command_override, but the
    override payload itself carries a command-substitution string — so a
    caller cannot use the override path to smuggle a substitution expression
    in either as a real override or as an inert value.
    """
    _allow_subprocess(tmp_path)
    marker = tmp_path / "pwned-by-override.txt"
    capability_id = _register_echo_capability(tmp_path, [])

    result = CLIAdapter().invoke(
        capability_id=capability_id,
        action="run",
        inputs={
            "root": str(tmp_path),
            "autonomy_mode": "policy-bound",
            "command": [sys.executable, "-c", f"import os; os.system('touch {marker}')"],
        },
    )

    assert not result.ok
    assert "command" in (result.error or "").lower()
    assert not marker.exists()
