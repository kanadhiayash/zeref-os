from __future__ import annotations

import argparse

from shiroe.cli.common import print_json, project_root


COMMAND_NAME = "policy"


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(COMMAND_NAME, help="Inspect policy")
    sub = parser.add_subparsers(dest="policy_command", required=True)
    sub.add_parser("show").add_argument("--json", action="store_true")
    check = sub.add_parser("check")
    check.add_argument("kind")
    check.add_argument("--target", default="")
    check.add_argument("--mode", default="auto-safe", choices=["suggest", "auto-safe", "policy-bound"])
    check.add_argument("--json", action="store_true")
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    from shiroe.policy import Action, ActionKind, AutonomyMode, evaluate, load_policy_stack

    stack = load_policy_stack(project_root())
    if args.policy_command == "show":
        payload = [{"name": layer.name, "allows": [kind.value for kind in layer.allows], "denies": [kind.value for kind in layer.denies]} for layer in stack]
        print_json(payload) if args.json else [print(layer["name"]) for layer in payload]
        return 0
    decision = evaluate(Action(ActionKind(args.kind), target=args.target), stack, mode=AutonomyMode(args.mode))
    payload = {"verdict": decision.verdict.value, "reason": decision.reason, "deciding_layer": decision.deciding_layer}
    print_json(payload) if args.json else print(payload["verdict"])
    return 0 if decision.allowed else 2
