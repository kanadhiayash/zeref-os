from __future__ import annotations

import argparse

from shiroe.cli.common import print_json, project_root


COMMAND_NAME = "state"


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(COMMAND_NAME, help="Inspect canonical state")
    sub = parser.add_subparsers(dest="state_command", required=True)
    for name in ("migrate", "rebuild", "verify"):
        child = sub.add_parser(name)
        child.add_argument("--json", action="store_true")
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    from shiroe.storage import EventLog, StateDB
    from shiroe.storage import views as views_mod
    from shiroe.storage.events import HashChainError

    root = project_root()
    db = StateDB(root)
    exit_code = 0
    if args.state_command == "migrate":
        applied = db.migrate()
        payload = {"schema_version": db.schema_version(), "applied": applied, "tables": db.tables()}
    elif args.state_command == "rebuild":
        db.migrate()
        conn = db.connect()
        result = EventLog(root, mirror_conn=conn).replay_into(conn)
        rendered = views_mod.render_all(root, conn)
        payload = {**result, "rendered": [str(path) for path in rendered]}
    else:
        db.migrate()
        try:
            EventLog(root, mirror_conn=db.connect()).verify_chain()
        except HashChainError as exc:
            payload = {
                "status": "fail",
                "chain": "broken",
                "schema_version": db.schema_version(),
                "error": str(exc),
            }
            exit_code = 1
        else:
            payload = {"status": "pass", "chain": "ok", "schema_version": db.schema_version()}
    print_json(payload) if getattr(args, "json", False) else print(payload)
    return exit_code
