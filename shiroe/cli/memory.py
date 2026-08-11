from __future__ import annotations

import argparse
import json
from pathlib import Path

from shiroe.cli.common import memory_write_from_payload, print_json, project_root, record_payload


COMMAND_NAME = "memory"


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(COMMAND_NAME, help="Canonical memory operations")
    sub = parser.add_subparsers(dest="memory_command", required=True)
    write = sub.add_parser("write")
    write.add_argument("--from", dest="from_path", required=True)
    write.add_argument("--json", action="store_true")
    recall = sub.add_parser("recall")
    recall.add_argument("query")
    recall.add_argument("--json", action="store_true")
    list_p = sub.add_parser("list")
    list_p.add_argument("--json", action="store_true")
    show = sub.add_parser("show")
    show.add_argument("id")
    show.add_argument("--json", action="store_true")
    sup = sub.add_parser("supersede")
    sup.add_argument("id")
    sup.add_argument("--with", dest="with_id", required=True)
    archive = sub.add_parser("archive")
    archive.add_argument("id")
    sub.add_parser("views")
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    from shiroe.memory.service import MemoryService
    from shiroe.memory.views import render_views
    from shiroe.verification import VerificationEngine

    root = project_root()
    service = MemoryService(root)
    try:
        if args.memory_command == "write":
            proposal = memory_write_from_payload(json.loads(Path(args.from_path).read_text(encoding="utf-8")))
            report = VerificationEngine(root).verify_memory_write(proposal)
            if report.status.value == "block":
                print_json({"status": "block", "report": report})
                return 1
            payload = record_payload(service.write(proposal))
        elif args.memory_command == "recall":
            result = service.search(args.query)
            payload = {
                "query": result.query,
                "abstained": result.abstained,
                "hits": [{"record": record_payload(hit.record), "score": hit.score, "why": hit.why} for hit in result.hits],
            }
        elif args.memory_command == "list":
            payload = [record_payload(record) for record in service.list(statuses=("active",))]
        elif args.memory_command == "show":
            payload = record_payload(service.get(args.id))
        elif args.memory_command == "supersede":
            payload = {"superseded": record_payload(service.supersede(args.id)), "replacement": record_payload(service.get(args.with_id))}
        elif args.memory_command == "archive":
            payload = record_payload(service.archive(args.id))
        else:
            payload = {"rendered": [str(path) for path in render_views(root)]}
    finally:
        service.close()
    print_json(payload) if getattr(args, "json", False) or not isinstance(payload, dict) else print(payload.get("id") or "ok")
    return 0
