from __future__ import annotations

import argparse
import json
from pathlib import Path

from shiroe.cli.common import print_json, project_root


COMMAND_NAME = "plan"


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(COMMAND_NAME, help="Persist a Work Graph plan")
    parser.add_argument("--from-json", required=True)
    parser.add_argument("--json", action="store_true")
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    from shiroe.work.compiler import compile_work_graph
    from shiroe.work.store import WorkStore

    spec = json.loads(Path(args.from_json).read_text(encoding="utf-8"))
    graph = compile_work_graph(spec)
    store = WorkStore(project_root())
    try:
        store.create(graph)
    finally:
        store.close()
    payload = {"id": graph.id, "status": graph.status.value, "nodes": len(graph.nodes)}
    print_json(payload) if args.json else print(f"planned {graph.id}")
    return 0
