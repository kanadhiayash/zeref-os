from __future__ import annotations

import argparse

from shiroe.cli.common import print_json, project_root


COMMAND_NAME = "verify"


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(COMMAND_NAME, help="Verify Work Graph or memory state")
    parser.add_argument("--graph")
    parser.add_argument("--memory")
    parser.add_argument("--json", action="store_true")
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    root = project_root()
    if args.graph:
        from shiroe.work.schema import NodeStatus
        from shiroe.work.store import WorkStore

        store = WorkStore(root)
        try:
            graph = store.get(args.graph)
            blocked = [node.id for node in graph.nodes if store.get_node(node.id).status is NodeStatus.blocked]
        finally:
            store.close()
        payload = {"subject": "work_graph", "graph_id": args.graph, "status": "block" if blocked else "pass", "blocked_nodes": blocked}
    elif args.memory:
        from shiroe.memory.models import MemoryWrite
        from shiroe.memory.service import MemoryService
        from shiroe.verification.engine import VerificationEngine

        service = MemoryService(root)
        try:
            record = service.get(args.memory)
        finally:
            service.close()
        proposal = MemoryWrite(
            kind=record.kind,
            title=record.title,
            claim=record.claim,
            source_refs=record.source_refs,
            summary=record.summary,
            confidence=record.confidence,
            evidence_grade=record.evidence_grade,
            privacy_class=record.privacy_class,
            authority=record.authority,
            scope=record.scope,
            valid_from=record.valid_from,
            valid_until=record.valid_until,
            owner=record.owner,
            tags=record.tags,
        )
        report = VerificationEngine(root).verify_memory_write(proposal)
        status = report.status.value if hasattr(report.status, "value") else str(report.status)
        payload = {
            "subject": "memory",
            "memory_id": record.id,
            "status": status,
            "checks": [
                {
                    "name": c.name,
                    "status": c.status.value if hasattr(c.status, "value") else str(c.status),
                }
                for c in report.checks
            ],
        }
    else:
        payload = {"subject": "runtime", "status": "pass"}
    print_json(payload) if args.json else print(payload["status"])
    return 0 if payload["status"] == "pass" else 1
