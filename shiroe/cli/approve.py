from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from shiroe.cli.common import print_json, project_root


COMMAND_NAME = "approve"


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(COMMAND_NAME, help="List, advise, or decide approvals")
    sub = parser.add_subparsers(dest="approve_command", required=True)
    sub.add_parser("list").add_argument("--json", action="store_true")
    show = sub.add_parser("show")
    show.add_argument("approval_id")
    show.add_argument("--json", action="store_true")
    advise = sub.add_parser("advise")
    advise.add_argument("approval_id")
    advise.add_argument("--capability", required=True)
    advise.add_argument("--json", action="store_true")
    decide = sub.add_parser("decide")
    decide.add_argument("approval_id")
    decide.add_argument("--decision", required=True, choices=["approved", "rejected", "revise", "deferred"])
    decide.add_argument("--reason", required=True)
    decide.add_argument("--json", action="store_true")
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    from shiroe.agents.approval_advisor import ApprovalAdvisor
    from shiroe.policy.approval_service import ApprovalService

    root = project_root()
    service = ApprovalService(root)
    try:
        if args.approve_command == "list":
            rows = service.conn.execute(
                "SELECT id FROM approval_requests ORDER BY requested_at DESC, id ASC"
            ).fetchall()
            payload = [asdict(service.get(row[0])) for row in rows]
        elif args.approve_command == "show":
            payload = asdict(service.get(args.approval_id))
        elif args.approve_command == "advise":
            payload = asdict(ApprovalAdvisor(root).advise(args.approval_id, args.capability))
        else:
            payload = asdict(service.decide_human(args.approval_id, decision=args.decision, actor="human", reason=args.reason))
    finally:
        service.close()
    print_json(payload) if getattr(args, "json", False) else print(json.dumps(payload, sort_keys=True))
    return 0
