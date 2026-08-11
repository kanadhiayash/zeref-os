from __future__ import annotations

import argparse

from shiroe.cli.common import print_json, project_root


COMMAND_NAME = "doctor"


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
    from shiroe.policy import load_policy_stack
    from shiroe.storage import EventLog, StateDB

    checks = []
    db = StateDB(root)
    try:
        db.migrate()
        checks.append({"name": "canonical_state", "status": "pass", "detail": "opens and migrates"})
        EventLog(root, mirror_conn=db.connect()).verify_chain()
        checks.append({"name": "hash_chain", "status": "pass", "detail": "ok"})
        load_policy_stack(root)
        checks.append({"name": "policy_stack", "status": "pass", "detail": "parses"})
        CapabilityStore(root).close()
        checks.append({"name": "capability_store", "status": "pass", "detail": "opens"})
        adapters = adapter_registry()
        unhealthy = [name for name, adapter in adapters.items() if not adapter.health().healthy]
        checks.append({"name": "adapters", "status": "pass" if not unhealthy else "fail", "detail": ",".join(unhealthy) or "healthy"})
    except Exception as exc:  # noqa: BLE001
        checks.append({"name": "runtime", "status": "fail", "detail": str(exc)})
    finally:
        db.close()
    return checks
