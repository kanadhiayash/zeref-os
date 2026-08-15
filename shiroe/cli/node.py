"""Private node registry command surface."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from pathlib import Path

from shiroe.cli.common import project_root
from shiroe.nodes.local_config import load_local_node_config
from shiroe.nodes.store import NodeStore
from shiroe.nodes.worker import worker_run_package
from shiroe.transport import TailscaleTransport


COMMAND_NAME = "node"


def register(subparsers):
    parser = subparsers.add_parser(COMMAND_NAME, help=argparse.SUPPRESS)
    subparsers._choices_actions = [  # noqa: SLF001 - argparse has no public hook for hidden subcommands.
        action for action in subparsers._choices_actions if action.dest != COMMAND_NAME
    ]
    node_sub = parser.add_subparsers(dest="node_command", required=True)

    list_p = node_sub.add_parser("list", help="List registered Shiroe nodes")
    list_p.add_argument("--json", action="store_true")
    list_p.set_defaults(handler=_list)

    discover_p = node_sub.add_parser("discover", help="Discover private transport peers as untrusted candidates")
    discover_p.add_argument("--json", action="store_true")
    discover_p.set_defaults(handler=_discover)

    register_p = node_sub.add_parser("register", help="Register an untrusted private execution candidate")
    register_p.add_argument("--name", required=True)
    register_p.add_argument("--host", required=True)
    register_p.add_argument("--ssh-user", required=True)
    register_p.add_argument("--role", choices=("worker", "controller"), default="worker")
    register_p.add_argument("--transport-stable-id", dest="transport_stable_id")
    register_p.add_argument("--tailscale-stable-id", dest="transport_stable_id", help=argparse.SUPPRESS)
    register_p.add_argument("--capability-digest")
    register_p.add_argument("--json", action="store_true")
    register_p.set_defaults(handler=_register)

    inspect_p = node_sub.add_parser("inspect", help="Inspect one node")
    inspect_p.add_argument("node_id")
    inspect_p.add_argument("--json", action="store_true")
    inspect_p.set_defaults(handler=_inspect)

    probe_p = node_sub.add_parser("probe", help="Probe a node transport path")
    probe_p.add_argument("node_id")
    probe_p.add_argument("--json", action="store_true")
    probe_p.set_defaults(handler=_probe)

    trust_p = node_sub.add_parser("trust", help="Mark a registered execution candidate trusted")
    trust_p.add_argument("node_id")
    trust_p.add_argument("--json", action="store_true")
    trust_p.set_defaults(handler=_trust)

    untrust_p = node_sub.add_parser("untrust", help="Remove trust from a registered execution candidate")
    untrust_p.add_argument("node_id")
    untrust_p.add_argument("--json", action="store_true")
    untrust_p.set_defaults(handler=_untrust)

    doctor_p = node_sub.add_parser("doctor", help="Run semantic checks for one node")
    doctor_p.add_argument("node_id")
    doctor_p.add_argument("--json", action="store_true")
    doctor_p.set_defaults(handler=_doctor)

    worker_p = node_sub.add_parser("worker-run", help="Internal package runner")
    worker_p.add_argument("--package", required=True)
    worker_p.add_argument("--json", action="store_true")
    worker_p.set_defaults(handler=_worker_run)


def run(args) -> int:
    return args.handler(args)


def _store() -> NodeStore:
    return NodeStore(project_root())


def _node_payload(node) -> dict:
    return {
        "id": node.id,
        "name": node.name,
        "role": node.role,
        "transport": node.transport,
        "trusted": node.trusted,
        "status": node.status,
        "capabilities": list(node.capabilities),
        "capability_digest": node.capability_digest,
        "last_seen_at": node.last_seen_at,
        "created_at": node.created_at,
        "updated_at": node.updated_at,
    }


def _list(args) -> int:
    payload = [_node_payload(node) for node in _store().list_nodes()]
    _print_public_json(payload) if args.json else [print(f"{n['id']} {n['role']} trusted={n['trusted']}") for n in payload]
    return 0


def _discover(args) -> int:
    status = TailscaleTransport().discover()
    payload = [asdict(peer) for peer in status.peers]
    _print_public_json(payload) if args.json else [print(f"{p['host']} {p['ip']} online={p['online']}") for p in payload]
    return 0


def _register(args) -> int:
    node = _store().register_candidate(
        name=args.name,
        role=args.role,
        transport_host=args.host,
        ssh_user=args.ssh_user,
        tailscale_stable_id=args.transport_stable_id,
        capability_digest=args.capability_digest,
    )
    payload = _node_payload(node)
    _print_public_json(payload) if args.json else print(payload["id"])
    return 0


def _inspect(args) -> int:
    payload = _node_payload(_store().get_node(args.node_id))
    _print_public_json(payload) if args.json else print(f"{payload['id']} {payload['role']}")
    return 0


def _probe(args) -> int:
    node = _store().get_node(args.node_id)
    result = TailscaleTransport().probe(node.transport_host)
    payload = asdict(result)
    _print_public_json(payload) if args.json else print(f"{payload['path_type']} {payload['latency_ms']}")
    return 0


def _trust(args) -> int:
    payload = _node_payload(_store().trust_node(args.node_id, trusted=True))
    _print_public_json(payload) if args.json else print(f"{payload['id']} trusted")
    return 0


def _untrust(args) -> int:
    payload = _node_payload(_store().trust_node(args.node_id, trusted=False))
    _print_public_json(payload) if args.json else print(f"{payload['id']} untrusted")
    return 0


def _doctor(args) -> int:
    node = _store().get_node(args.node_id)
    probe = TailscaleTransport().probe(node.transport_host)
    checks = [
        {"name": "registered", "status": "pass", "detail": "configured"},
        {"name": "trusted", "status": "pass" if node.trusted else "fail", "detail": str(node.trusted).lower()},
        {"name": "probe", "status": "pass" if probe.reachable else "fail", "detail": "checked"},
    ]
    payload = {"status": "pass" if all(c["status"] == "pass" for c in checks) else "fail", "checks": checks}
    _print_public_json(payload) if args.json else [print(f"{c['status']} {c['name']}: {c['detail']}") for c in checks]
    return 0 if payload["status"] == "pass" else 1


def _worker_run(args) -> int:
    package = json.loads(Path(args.package).read_text(encoding="utf-8"))
    config_path = os.environ.get("SHIROE_NODE_CONFIG")
    config = load_local_node_config(Path(config_path) if config_path else None)
    capability_digest = os.environ.get("SHIROE_WORKER_CAPABILITY_DIGEST")
    if not capability_digest:
        raise RuntimeError("SHIROE_WORKER_CAPABILITY_DIGEST is required for worker-run")
    receipt = worker_run_package(
        package,
        config=config,
        ssh_env=os.environ,
        transport=TailscaleTransport(),
        capability_digest=capability_digest,
        executor=lambda _package: {"output": {}},
    )
    payload = receipt.to_dict()
    _print_public_json(payload) if args.json else print(payload["package_digest"])
    return 0


def _print_public_json(payload: object) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))
