from __future__ import annotations

import argparse

from shiroe.cli.common import print_json, project_root


COMMAND_NAME = "handoff"
TARGETS = ("codex", "claude", "cursor", "github", "human")


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(COMMAND_NAME, help="Compile a canonical handoff")
    parser.add_argument("target", choices=TARGETS)
    parser.add_argument("--graph", required=True)
    parser.add_argument("--include-private", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    from shiroe.handoff.compiler import compile_handoff

    payload = compile_handoff(project_root(), target=args.target, graph_id=args.graph, include_private=args.include_private)
    print_json(payload) if args.json else print(payload["markdown"])
    return 0
