from __future__ import annotations

import json
import sys
from pathlib import Path

from shiroe.adapters.capabilities.cli import CLIAdapter
from shiroe.capabilities.inspection import inspect_source
from shiroe.capabilities.store import CapabilityStore


def _allow_subprocess(root: Path) -> None:
    policy_dir = root / ".shiroe" / "policy"
    policy_dir.mkdir(parents=True, exist_ok=True)
    (policy_dir / "defaults.json").write_text(
        json.dumps({"allow": ["subprocess"]}),
        encoding="utf-8",
    )


def _register_manifest_command(root: Path) -> str:
    script = root / "capabilities" / "safe_writer.py"
    script.parent.mkdir(parents=True)
    script.write_text(
        "from pathlib import Path\n"
        "import sys\n"
        "Path(sys.argv[1]).write_text('safe', encoding='utf-8')\n",
        encoding="utf-8",
    )
    digest = inspect_source(script).digest
    capability_id = "test.safe-writer"
    manifest = {
        "schema": "shiroe.capability/v1",
        "id": capability_id,
        "name": "Safe Writer",
        "type": "script",
        "version": "1.0.0",
        "source": {"kind": "local-file", "location": str(script)},
        "entrypoint": {
            "adapter": "cli",
            "command": [sys.executable, str(script), str(root / "safe.txt")],
        },
        "requires": {},
    }
    with CapabilityStore(root) as store:
        store.upsert_capability(
            capability_id=capability_id,
            name="Safe Writer",
            type_="script",
            lifecycle="active",
            digest=digest,
            manifest=manifest,
            source_kind="local-file",
            source_location=str(script),
        )
    return capability_id


def test_cli_adapter_rejects_invocation_command_override(tmp_path: Path) -> None:
    _allow_subprocess(tmp_path)
    capability_id = _register_manifest_command(tmp_path)
    pwned = tmp_path / "pwned.txt"

    result = CLIAdapter().invoke(
        capability_id=capability_id,
        action="run",
        inputs={
            "root": str(tmp_path),
            "autonomy_mode": "policy-bound",
            "command": [
                sys.executable,
                "-c",
                f"from pathlib import Path; Path({str(pwned)!r}).write_text('pwned', encoding='utf-8')",
            ],
        },
    )

    assert not result.ok
    assert "command" in (result.error or "").lower()
    assert not pwned.exists()
    assert not (tmp_path / "safe.txt").exists()
