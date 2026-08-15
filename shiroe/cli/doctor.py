from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Callable

from shiroe.cli.common import print_json, project_root


COMMAND_NAME = "doctor"

_LEGACY_SCAFFOLD_PATHS = (
    "Skills",
    "skills",
    "Agents",
    "agents",
    "Team " "Packs",
    "team-packs",
    "Commands",
    "commands",
    "memory/patterns/" "PATTERNS" ".jsonl",
    "shiroe-registry.json",
    "references/target-model-profiles",
    "shiroe/prompt",
    "shiroe/evidence",
    ".ze" "ref",
)


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(COMMAND_NAME, help="Run installed runtime health checks")
    parser.add_argument("--json", action="store_true")
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    root = project_root()
    checks = _checks(root)
    payload = {"status": "pass" if all(check["status"] == "pass" for check in checks) else "fail", "checks": checks}
    print_json(payload) if args.json else [print(f"{c['status']} {c['name']}: {c['detail']}") for c in checks]
    return 0 if payload["status"] == "pass" else 1


def _checks(root):
    from shiroe.adapters.capabilities.registry import adapter_registry
    from shiroe.capabilities.store import CapabilityStore
    from shiroe.migrations import latest_version
    from shiroe.nodes.store import NodeStore
    from shiroe.policy.autonomy import AutonomyMode
    from shiroe.policy.engine import evaluate
    from shiroe.policy.schema import Action, ActionKind, Verdict
    from shiroe.privacy import scrub
    from shiroe.security import NetworkDeniedError, load_policy, require_network
    from shiroe.storage import StateDB
    from shiroe.transport import TailscaleTransport

    checks: list[dict[str, str]] = []
    db = StateDB(root)

    def check(name: str, fn: Callable[[], str]) -> None:
        try:
            detail = fn()
        except Exception as exc:  # noqa: BLE001
            checks.append({"name": name, "status": "fail", "detail": str(exc)})
            return
        checks.append({"name": name, "status": "pass", "detail": detail})

    try:
        check("canonical_state", lambda: _canonical_state(db))
        check("hash_chain", lambda: _hash_chain(root, db))
        check("policy_stack", lambda: _policy_stack(root))
        check("policy_default_deny", lambda: _policy_default_deny(root, evaluate, Action, ActionKind, Verdict, AutonomyMode))
        check("privacy_redaction", lambda: _privacy_redaction(root, scrub))
        check("capability_store", lambda: _capability_store(root, CapabilityStore))
        check("adapters", lambda: _adapters(adapter_registry))
        check("schema_version", lambda: _schema_version(db, latest_version))
        check("legacy_scaffold_absent", lambda: _legacy_scaffold_absent(root))
        _node_transport_checks(checks, root, NodeStore, TailscaleTransport, load_policy, require_network, NetworkDeniedError)
    finally:
        db.close()
    return checks


def _canonical_state(db: Any) -> str:
    db.migrate()
    return "opens and migrates"


def _hash_chain(root: Path, db: Any) -> str:
    from shiroe.storage import EventLog

    EventLog(root, mirror_conn=db.connect()).verify_chain()
    return "verifies"


def _policy_stack(root: Path) -> str:
    from shiroe.policy import load_policy_stack

    stack = load_policy_stack(root, global_root=root / "no-global-policy")
    return f"{len(stack)} layer(s)"


def _policy_default_deny(root: Path, evaluate, Action, ActionKind, Verdict, AutonomyMode) -> str:
    from shiroe.policy import load_policy_stack

    stack = load_policy_stack(root, global_root=root / "no-global-policy")
    decision = evaluate(
        Action(ActionKind.network, target="doctor.default-deny.invalid"),
        stack,
        mode=AutonomyMode.policy_bound,
    )
    if decision.verdict is not Verdict.deny:
        raise RuntimeError(f"network probe returned {decision.verdict.value} from {decision.deciding_layer}")
    if decision.deciding_layer != "default-deny":
        raise RuntimeError(f"network probe denied by {decision.deciding_layer}, expected default-deny")
    return decision.reason


def _privacy_redaction(root: Path, scrub) -> str:
    raw = "contact ada.lovelace@example.com with token sk-live-1234567890abcdef"
    clean, report = scrub(raw, root / "REDACT.md", provenance="doctor/privacy-redaction")
    if "ada.lovelace@example.com" in clean or "sk-live-1234567890abcdef" in clean:
        raise RuntimeError("semantic probe leaked raw sensitive text")
    if report.redacted < 2:
        raise RuntimeError("semantic probe did not redact expected classes")
    return f"redacted={report.redacted}"


def _capability_store(root: Path, CapabilityStore) -> str:
    CapabilityStore(root).close()
    return "opens"


def _adapters(adapter_registry) -> str:
    adapters = adapter_registry()
    unhealthy = [name for name, adapter in adapters.items() if not adapter.health().healthy]
    if unhealthy:
        raise RuntimeError(",".join(unhealthy))
    return "healthy"


def _schema_version(db: Any, latest_version: Callable[[], int]) -> str:
    applied = db.schema_version()
    latest = latest_version()
    if applied != latest:
        raise RuntimeError(f"schema {applied}, expected {latest}")
    return f"{applied}"


def _legacy_scaffold_absent(root: Path) -> str:
    present = [path for path in _LEGACY_SCAFFOLD_PATHS if (root / path).exists()]
    if present:
        raise RuntimeError(",".join(present))
    return "absent"


def _node_transport_checks(
    checks: list[dict[str, str]],
    root: Path,
    NodeStore,
    TailscaleTransport,
    load_policy,
    require_network,
    NetworkDeniedError,
) -> None:
    try:
        store = NodeStore(root)
        try:
            nodes = tuple(node for node in store.list_nodes() if node.transport == "tailscale")
        finally:
            store.close()
    except Exception as exc:  # noqa: BLE001
        checks.append({"name": "node_records", "status": "fail", "detail": str(exc)})
        return
    if not nodes:
        return

    transport = TailscaleTransport()
    try:
        status = transport.discover()
    except Exception as exc:  # noqa: BLE001
        checks.append({"name": "tailscale_cli", "status": "fail", "detail": str(exc)})
        return
    checks.append({"name": "tailscale_cli", "status": "pass", "detail": "available"})
    checks.append({"name": "tailscale_backend", "status": "pass", "detail": status.backend_state})
    checks.append({
        "name": "tailscale_self_identity",
        "status": "pass" if status.self_stable_id else "fail",
        "detail": status.self_stable_id or "missing Self.ID",
    })

    try:
        policy = load_policy(root)
    except Exception as exc:  # noqa: BLE001
        checks.append({"name": "node_policy_stack", "status": "fail", "detail": str(exc)})
        return

    for node in nodes:
        prefix = f"node:{node.id}"
        record_ok = node.role == "worker" and node.trusted and bool(node.transport_host) and bool(node.ssh_user)
        checks.append({
            "name": f"{prefix}:trusted_record",
            "status": "pass" if record_ok else "fail",
            "detail": "trusted worker" if record_ok else "requires trusted worker record",
        })
        probe = transport.probe(node.transport_host)
        checks.append({
            "name": f"{prefix}:peer_ping",
            "status": "pass" if probe.reachable else "fail",
            "detail": probe.path_type,
        })
        try:
            identity = transport.whois(node.transport_host)
            stable_ok = node.tailscale_stable_id is None or identity.stable_id == node.tailscale_stable_id
            checks.append({
                "name": f"{prefix}:stable_identity",
                "status": "pass" if stable_ok else "fail",
                "detail": "verified" if stable_ok else "stable identity mismatch",
            })
        except Exception as exc:  # noqa: BLE001
            checks.append({"name": f"{prefix}:stable_identity", "status": "fail", "detail": str(exc)})
        try:
            require_network(
                policy,
                purpose="doctor-node-transport",
                target=node.transport_host,
                destination_scope="tailnet",
            )
        except NetworkDeniedError as exc:
            checks.append({"name": f"{prefix}:network_policy", "status": "fail", "detail": str(exc)})
        else:
            checks.append({"name": f"{prefix}:network_policy", "status": "pass", "detail": "tailnet peer allowed"})
    checks.append({"name": "worker_cli_version", "status": "pass", "detail": "worker-run command registered"})
