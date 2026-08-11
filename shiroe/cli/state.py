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

    root = project_root()
    db = StateDB(root)
    if args.state_command == "migrate":
        applied = db.migrate()
        payload = {"schema_version": db.schema_version(), "applied": applied, "tables": db.tables()}
    elif args.state_command == "rebuild":
        db.migrate()
        conn = db.connect()
        replayed = EventLog(root, mirror_conn=conn).replay_into(conn)
        rendered = views_mod.render_all(root, conn)
        payload = {"replayed": replayed, "rendered": [str(path) for path in rendered]}
    else:
        db.migrate()
        EventLog(root, mirror_conn=db.connect()).verify_chain()
        payload = {"status": "pass", "chain": "ok", "schema_version": db.schema_version()}
    print_json(payload) if getattr(args, "json", False) else print(payload)
    return 0
