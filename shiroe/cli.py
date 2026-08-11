"""
privacy-audit: allow-file "CLI help text names example commands and env-var-shaped tokens (SHIROE_ALLOW_*, GITHUB_TOKEN) as documentation of the security policy."

shiroe.cli — Reference CLI for Shiroe (Sprint 2).

Commands:
    shiroe status          Print hot.md summary + active tier
    shiroe write-decision  Append a decision to memory/DECISIONS.md
    shiroe memory ...      Add/search/get/update/history/explain structured memory
    shiroe grade <claim>   Grade a claim (evidence-grader heuristics + optional LLM)
    shiroe audit-privacy   Run deterministic PII audit on memory/
    shiroe audit           Structural validation (wraps shiroe-validate.py)

Write commands: write-decision, memory add, memory update.
Wraps litellm for grade if available; degrades gracefully without it.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _project_root() -> Path:
    """Walk up from cwd until AGENTS.md found (Shiroe root)."""
    from shiroe.memory import MemoryRoot

    return MemoryRoot.discover().root


def _read_file(path: Path, fallback: str = "") -> str:
    return path.read_text(errors="ignore") if path.exists() else fallback


def _print_section(title: str, body: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")
    print(body.strip())


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_status(args: argparse.Namespace) -> int:
    root = _project_root()

    hot = _read_file(root / "memory" / "hot.md", "(hot.md not found — run /start first)")
    _print_section("memory/hot.md (last 3 sessions)", hot[:1500])

    project = _read_file(root / "config" / "PROJECT.md", "(config/PROJECT.md missing — run /start)")
    _print_section("config/PROJECT.md (first 10 lines)", "\n".join(project.splitlines()[:10]))

    budget = _read_file(root / "config" / "BUDGET.md", "")
    tier = "Standard (default)"
    for line in budget.splitlines():
        if "model_tier:" in line:
            tier = line.split(":", 1)[-1].strip()
            break
    _print_section("Active tier", tier)

    return 0


def cmd_write_decision(args: argparse.Namespace) -> int:
    """Write a decision: hold single-writer lock, atomic append, scrub PII first."""
    from shiroe.lock import LockError
    from shiroe.memory import MemoryWriter

    root = _project_root()

    title    = args.title    or input("Decision title: ").strip()
    why      = args.why      or input("Why (rationale): ").strip()
    evidence = args.evidence or input("Evidence/source (Enter to skip): ").strip()
    grade    = args.grade    or "medium"

    try:
        result = MemoryWriter.from_root(root).write_decision(
            title=title,
            why=why,
            evidence=evidence,
            grade=grade,
        )
    except LockError as e:
        print(f"✘ {e}")
        return 2

    print(f"✔ Decision appended to {result.target}")
    print(f"  Title: {result.title} | Date: {result.date} | Grade: {grade}")
    print(f"  Event: {result.event_hash}")
    if result.redacted:
        print(f"  PII scrubbed from inputs: {result.redacted} token(s)")
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    """v2.5 L5: scaffold memory/ + config/ + privacy templates (no LLM)."""
    from shiroe.memory import normalize_init_values, scaffold_project

    root = Path(args.directory).resolve() if args.directory else Path.cwd()
    print(f"\nInitialising Shiroe layout at {root}")

    # Use `is None` so empty-string CLI args (e.g. --parent "") skip the prompt.
    # Non-TTY stdin (piped install, CI) also skips prompts and uses defaults.
    import sys as _sys
    _tty = _sys.stdin.isatty()
    def _prompt_or_default(prompt: str, default: str) -> str:
        if not _tty:
            return default
        return input(prompt).strip() or default
    name    = args.name    if args.name    is not None else _prompt_or_default("Project name: ", "(unnamed)")
    privacy = args.privacy if args.privacy is not None else _prompt_or_default("Privacy mode [abstract/exact/local-only] (default abstract): ", "abstract")
    tier    = args.tier    if args.tier    is not None else _prompt_or_default("Model tier [auto/free/standard/god-mode] (default auto): ", "auto")
    parent  = args.parent  if args.parent  is not None else _prompt_or_default("Parent project path (Enter if none): ", "")
    values = normalize_init_values(name=name, privacy=privacy, tier=tier, parent=parent)
    scaffold_project(root, name=name, privacy=privacy, tier=tier, parent=parent)

    print(f"\n✔ Scaffolded:")
    print(f"  config/PROJECT.md (name={values['name']}, privacy={values['privacy']}, tier={values['tier']})")
    print(f"  memory/ flat + layered layout")
    if values["parent"]:
        print(f"  parent: {values['parent']}")
    print(f"\nNext: edit config/PROJECT.md as needed, then `shiroe status`.")
    return 0


def cmd_recall(args: argparse.Namespace) -> int:
    from shiroe.memory.recall import recall

    result = recall(
        _project_root(),
        args.query,
        limit=args.limit,
        atom_type=args.type,
        status=args.status,
    )
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(result["answer"])
        print(f"Evidence: {result['evidence_grade']} | Source: {result['source']}")
        for match in result["matched_atoms"]:
            atom = match["atom"]
            print(f"- {atom['id']} [{atom['type']}/{atom['status']}] {atom['claim']}")
        if result["open_contradictions"]:
            print("Open contradictions:")
            for atom in result["open_contradictions"]:
                print(f"- {atom['id']} {atom['claim']}")
    return 0


def cmd_explain_search(args: argparse.Namespace) -> int:
    from shiroe.memory.recall import explain_search

    result = explain_search(
        _project_root(),
        args.query,
        limit=args.limit,
        atom_type=args.type,
        status=args.status,
    )
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"Query: {result['query']}")
        print(f"Tokens: {', '.join(result['tokens'])}")
        print(f"Source: {result['source']}")
        for candidate in result["candidates"]:
            print(
                f"- {candidate['id']} score={candidate['score']} "
                f"{candidate['why_selected']}"
            )
    return 0


def cmd_cost(args: argparse.Namespace) -> int:
    from shiroe.memory.cost_router import audit_budgets, estimate_tokens, report, route_operation

    root = _project_root()
    if args.cost_command == "estimate":
        result = estimate_tokens(args.text or "")
    elif args.cost_command == "route":
        result = route_operation(
            args.operation,
            text=args.text or "",
            approval=args.approval,
            render_mode=args.render_mode,
            duplicate=args.duplicate,
            status_change=args.status_change,
            public_claim=args.public_claim,
            contradiction=args.contradiction,
        )
    elif args.cost_command == "report":
        result = report(root)
    elif args.cost_command == "audit":
        result = audit_budgets(root, strict=args.strict)
        if args.strict and not result["passed"]:
            print(json.dumps(result, indent=2, sort_keys=True))
            return 1
    else:
        print("✘ cost subcommand required")
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def cmd_facts(args: argparse.Namespace) -> int:
    from shiroe.memory.fact_guard import audit_facts

    result = audit_facts(_project_root())
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passed"] else 1



def cmd_prompt(args: argparse.Namespace) -> int:
    if args.prompt_command == "classify":
        from shiroe.prompt.classify import classify_prompt

        result = classify_prompt(args.prompt)
    elif args.prompt_command == "rewrite":
        from shiroe.prompt.rewrite import rewrite_prompt

        result = rewrite_prompt(args.prompt)
    elif args.prompt_command == "brief":
        from shiroe.prompt.rewrite import build_brief

        result = build_brief(args.prompt)
    elif args.prompt_command == "inject":
        from shiroe.prompt.inject import inject_prompt

        result = inject_prompt(args.prompt, target=args.target)
    else:
        return 2
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif args.prompt_command == "classify":
        print(f"{result['classification']}: {result['reason']}")
    elif args.prompt_command == "inject":
        print(result["content"])
    elif args.prompt_command == "rewrite":
        print(result["markdown"])
    else:
        from shiroe.prompt.rewrite import brief_to_markdown

        print(brief_to_markdown(result))
    return 0 if result.get("classification") != "UNSAFE" else 1


def cmd_handoff(args: argparse.Namespace) -> int:
    from shiroe.handoff.compiler import compile_handoff

    result = compile_handoff(
        _project_root(),
        target=args.handoff_command,
        objective=args.objective,
        include_private=bool(getattr(args, "include_private", False)),
    )
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"✔ Handoff written for {result['target']}")
        print(f"  Markdown: {result['markdown']}")
        print(f"  JSON: {result['json']}")
    return 0


def cmd_loop(args: argparse.Namespace) -> int:
    root = _project_root()
    if args.loop_command == "plan":
        from shiroe.loops.contract import create_loop_contract

        result = create_loop_contract(
            root,
            args.goal,
            team_pack=args.team,
            max_iterations=args.max_iterations,
        )
    elif args.loop_command == "run":
        from shiroe.loops.runtime import run_loop

        result = run_loop(
            root,
            args.goal,
            team_pack=args.team,
            max_iterations=args.max_iterations,
        )
    elif args.loop_command == "status":
        from shiroe.loops.runtime import loop_status

        result = loop_status(root)
    elif args.loop_command == "report":
        from shiroe.loops.runtime import loop_report

        result = loop_report(root, loop_id=args.loop_id)
    else:
        return 2
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif args.loop_command == "report":
        print(result["report"] if result["found"] else "No loop report found.")
    else:
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def cmd_db_status(args: argparse.Namespace) -> int:
    """v2.5 L4: report backend (sqlite/duckdb) + extras availability."""
    backends = {"sqlite3": False, "duckdb": False, "yaml": False, "litellm": False}
    try: import sqlite3; backends["sqlite3"] = True
    except ImportError: pass
    try: import duckdb;  backends["duckdb"]  = True
    except ImportError: pass
    try: import yaml;    backends["yaml"]    = True
    except ImportError: pass
    try: import litellm; backends["litellm"] = True
    except ImportError: pass

    print("\nshiroe backend status:")
    for k, v in backends.items():
        icon = "✔" if v else "✘"
        print(f"  {icon} {k:<10} {'available' if v else 'not installed'}")
    print(f"\n  Parquet export: {'enabled' if backends['duckdb'] else 'disabled (install duckdb)'}")
    print(f"  Rich YAML:      {'enabled' if backends['yaml'] else 'fallback regex parser'}")
    print(f"  LLM grading:    {'enabled' if backends['litellm'] else 'heuristic-only'}")
    return 0


def cmd_grade(args: argparse.Namespace) -> int:
    """Evidence-grader: heuristic + optional LLM via litellm."""
    claim = (args.claim or "").strip()
    if not claim:
        claim = input("Claim to grade: ").strip()

    low = claim.lower()

    # Recency
    if any(w in low for w in ["today", "this week", "just", "recently", "2026", "2025"]):
        recency = "high"
    elif any(w in low for w in ["last year", "2024", "2023", "old", "legacy"]):
        recency = "low"
    else:
        recency = "medium"

    # Provenance
    if any(w in low for w in ["source:", "ref:", "from ", "per ", "according to", "confirmed by"]):
        provenance = "high"
    elif any(w in low for w in ["i think", "probably", "maybe", "might", "guess"]):
        provenance = "low"
    else:
        provenance = "medium"

    # Corroboration
    if any(w in low for w in ["always", "never", "all ", "none ", "definitely"]):
        corroboration = "low"
    elif any(w in low for w in ["typically", "generally", "often", "usually"]):
        corroboration = "medium"
    else:
        corroboration = "medium"

    _s = {"high": 2, "medium": 1, "low": 0}
    avg = (_s[recency] + _s[provenance] + _s[corroboration]) / 3
    grade = "high" if avg >= 1.7 else ("low" if avg < 0.8 else "medium")

    llm_note = ""
    try:
        # R3: policy gate + scrub claim before egress (see SHR-AUDIT-001).
        from shiroe.security import load_policy, require_connector, ConnectorDisabledError, NetworkDeniedError
        from shiroe.privacy import scrub
        root = _project_root()
        policy = load_policy(root)
        require_connector(policy, "litellm", purpose="grade-claim")
        scrubbed_claim, _rpt = scrub(claim, root / "REDACT.md", provenance="cli/grade/claim")
        import litellm  # type: ignore
        from shiroe.routing.gateway import ModelCallRequest, route
        # Claim grading is LOW criticality; the gateway holds it to "fast".
        _decision = route(ModelCallRequest(
            criticality="LOW",
            purpose="grade-claim",
            requested_class="fast",
            provider="openai",
        ))
        resp = litellm.completion(
            model=_decision.model_spec.model_id,
            messages=[{"role": "user", "content": (
                f"Grade this claim on recency, provenance, corroboration (high/medium/low each). "
                f"Claim: \"{scrubbed_claim}\"\n"
                f"Reply JSON only: {{\"recency\":\"?\",\"provenance\":\"?\",\"corroboration\":\"?\","
                f"\"grade\":\"?\",\"reasoning\":\"...\"}}"
            )}],
            max_tokens=200,
        )
        d = json.loads(resp.choices[0].message.content)
        grade, recency, provenance, corroboration = (
            d.get("grade", grade), d.get("recency", recency),
            d.get("provenance", provenance), d.get("corroboration", corroboration),
        )
        llm_note = f"\n  LLM reasoning: {d.get('reasoning', '')}"
    except (ConnectorDisabledError, NetworkDeniedError) as exc:
        llm_note = f"\n  (LLM egress denied — {exc.__class__.__name__}: {exc}. Heuristic grade used.)"
    except Exception:
        llm_note = "\n  (litellm unavailable — heuristic grade)"

    print(f"\nClaim:          {claim}")
    print(f"  Grade:         {grade.upper()}")
    print(f"  Recency:       {recency}")
    print(f"  Provenance:    {provenance}")
    print(f"  Corroboration: {corroboration}{llm_note}")
    if grade == "low":
        print("\n  ⚠ Suggested action: demote or remove from wiki.")
    return 0


def cmd_audit_privacy(args: argparse.Namespace) -> int:
    from shiroe.privacy import audit as _audit

    root = _project_root()
    redact = root / "REDACT.md"
    strict = bool(getattr(args, "strict", False))
    # In strict mode default to whole-project scan; otherwise scan memory/ only for speed.
    directory = Path(args.directory) if args.directory else (root if strict else root / "memory")

    max_hits = int(getattr(args, "max_hits", 0) or 0)
    max_files = int(getattr(args, "max_files", 0) or 0)

    print(f"Scanning {directory} …  (REDACT.md: {redact}, strict={strict})")
    results = _audit(directory=directory, redact_md_path=redact, strict=strict)

    print(f"\nFiles scanned:  {results['scanned']}")
    print(f"Total PII hits: {results['total_hits']}")
    print(f"Allowlisted:    {len(results.get('allowlisted', []))}")

    if results["by_class"]:
        print("\nHits by class:")
        for cls, cnt in sorted(results["by_class"].items(), key=lambda x: -x[1]):
            print(f"  [{cls}] {cnt} file(s)")

    if results["by_file"]:
        print("\nAffected files:")
        for fp, cnt in sorted(results["by_file"].items(), key=lambda x: -x[1]):
            print(f"  {cnt:3d}  {fp}")
    else:
        print("\n✔ No PII detected.")

    hits = results["total_hits"]
    files_hit = len(results["by_file"])

    # Severity-class mode (WS2): mirrors _check_privacy_scan in
    # shiroe/release/checks.py. Classes named in --fail-classes have ZERO
    # tolerance — any hit fails, regardless of count. This supersedes the
    # count ceilings below for CI use.
    fail_classes = [
        cls.strip()
        for cls in str(getattr(args, "fail_classes", "") or "").split(",")
        if cls.strip()
    ]
    if fail_classes:
        hits_by_class = results.get("hits_by_class", {})
        blocking = {cls: hits_by_class.get(cls, 0) for cls in fail_classes
                    if hits_by_class.get(cls, 0) > 0}
        if blocking:
            detail = ", ".join(f"{cls}={cnt}" for cls, cnt in sorted(blocking.items()))
            offenders = sorted(results.get("credential_files", {}))[:5]
            print(f"\n✘ Zero-tolerance class hit: {detail}")
            for offender in offenders:
                print(f"    {offender}")
            return 1
        informational = hits
        print(f"\n✔ 0 hits in zero-tolerance class(es) {','.join(fail_classes)} "
              f"({informational} informational hit(s) in non-blocking classes)")
        return 0

    # Legacy threshold-mode (pre-WS2 ceiling semantics, kept for compatibility).
    # Fail iff hits exceed --max-hits AND files exceed --max-files. Either 0 disables that dimension of the ceiling.
    if max_hits > 0 or max_files > 0:
        if hits == 0:
            print(f"\n✔ Zero hits under threshold (max_hits={max_hits or '-'}, max_files={max_files or '-'})")
            return 0
        over_hits = (max_hits > 0 and hits > max_hits)
        over_files = (max_files > 0 and files_hit > max_files)
        if over_hits or over_files:
            print(f"\n✘ Exceeded noise ceiling: hits={hits}/{max_hits or 'inf'}  files={files_hit}/{max_files or 'inf'}")
            return 1
        print(f"\n✔ {hits} residual hit(s) across {files_hit} spec/schema file(s) — under noise ceiling")
        return 0

    return 0 if hits == 0 else 1


def cmd_audit(args: argparse.Namespace) -> int:
    root = _project_root()
    if getattr(args, "audit_command", None) == "report":
        from shiroe.audit.reports import audit_report

        print(audit_report(root, since=args.since or "", format=args.format), end="")
        return 0

    script = root / "scripts" / "shiroe-validate.py"
    if not script.exists():
        script = root / "scripts" / "shiroe-validate-v4.py"
    if not script.exists():
        print("✘ shiroe-validate.py not found in scripts/")
        return 1
    return subprocess.run([sys.executable, str(script)], cwd=str(root)).returncode


def cmd_memory(args: argparse.Namespace) -> int:
    from shiroe.core.errors import GuardRejection
    from shiroe.guards.write_gate import propose_memory, write_from_proposal
    from shiroe.memory.atom_store import AtomStore
    from shiroe.memory.schemas import ATOM_TYPES, create_atom, utc_now_iso
    from shiroe.memory_state import card_to_dict, event_to_dict, item_to_dict, MemoryStore
    from shiroe.privacy import scrub

    root = _project_root()
    store = MemoryStore.from_root(root)
    atom_store = AtomStore(root)

    try:
        if args.memory_command == "propose":
            proposal = propose_memory(args.claim, output=Path(args.out))
            if args.json:
                print(json.dumps(proposal, indent=2, sort_keys=True))
            else:
                print(f"✔ proposal written to {args.out}")
            return 0

        if args.memory_command == "write":
            card = write_from_proposal(Path(args.from_path), store)
            print(json.dumps(card, indent=2, sort_keys=True) if args.json else f"✔ memory card written: {card['id']}")
            return 0

        if args.memory_command == "list":
            atom_type = args.type if args.type in ATOM_TYPES else None
            atoms = atom_store.load(atom_type=atom_type, status=args.status) if (args.atoms or atom_type) else []
            if args.atoms or atoms:
                if args.json:
                    print(json.dumps(atoms[:args.limit], indent=2, sort_keys=True))
                else:
                    for atom in atoms[:args.limit]:
                        print(f"{atom['id']}\t{atom['type']}\t{atom['status']}\t{atom['claim']}")
                    if not atoms:
                        print("(no atoms)")
                return 0

            cards = store.list_cards(type=args.type or "", status=args.status or "", limit=args.limit)
            if args.json:
                print(json.dumps([card_to_dict(card) for card in cards], indent=2, sort_keys=True))
            else:
                for card in cards:
                    print(f"{card.id} {card.type} {card.status} {card.title}")
                if not cards:
                    print("No memory cards found.")
            return 0

        # show/archive/supersede resolve against the canonical atom store
        # first and fall back to memory_cards, so ids written before the
        # convergence stay reachable instead of silently 404-ing.
        if args.memory_command == "show":
            atom = atom_store.get(args.id)
            if atom is not None:
                print(json.dumps(atom, indent=2, sort_keys=True))
                return 0
            card = store.get_card(args.id)
            if card is None:
                print(f"✘ memory {args.id} not found")
                return 1
            print(json.dumps(card_to_dict(card), indent=2, sort_keys=True))
            return 0

        if args.memory_command == "archive":
            if atom_store.get(args.id) is not None:
                atom = atom_store.patch(args.id, {"status": "archived"})
                print(json.dumps(atom, indent=2, sort_keys=True) if args.json else f"✔ archived {atom['id']}")
                return 0
            card = store.archive_card(args.id)
            print(json.dumps(card_to_dict(card), indent=2, sort_keys=True) if args.json else f"✔ archived {card.id}")
            return 0

        if args.memory_command == "supersede":
            replacement = atom_store.get(args.with_id)
            if atom_store.get(args.id) is not None and replacement is not None:
                # Both already exist as atoms: close the old row's transaction
                # interval in place rather than appending a duplicate.
                old_atom = atom_store.patch(
                    args.id,
                    {
                        "status": "superseded",
                        "superseded_at": utc_now_iso(),
                        "superseded_by": replacement["id"],
                    },
                )
                replacement = atom_store.patch(
                    replacement["id"],
                    {"supersedes": sorted({*replacement.get("supersedes", []), args.id})},
                )
                result = {"superseded": old_atom, "replacement": replacement}
                print(json.dumps(result, indent=2, sort_keys=True) if args.json
                      else f"✔ {old_atom['id']} superseded by {replacement['id']}")
                return 0
            old_card, new_card = store.supersede_card(args.id, args.with_id)
            result = {"superseded": card_to_dict(old_card), "replacement": card_to_dict(new_card)}
            print(json.dumps(result, indent=2, sort_keys=True) if args.json else f"✔ {old_card.id} superseded by {new_card.id}")
            return 0

        if args.memory_command == "add":
            if args.claim is not None or args.source is not None or args.type is not None:
                if not args.type or not args.claim or not args.source:
                    print("✘ atom add requires --type, --claim, and --source")
                    return 2
                redact = root / "REDACT.md"
                claim, claim_report = scrub(args.claim, redact, provenance="memory/add/claim")
                summary_raw = args.summary or args.claim
                summary, summary_report = scrub(summary_raw, redact, provenance="memory/add/summary")
                source, source_report = scrub(args.source, redact, provenance="memory/add/source")
                provenance_raw = args.provenance or "shiroe-cli memory add"
                provenance, provenance_report = scrub(
                    provenance_raw,
                    redact,
                    provenance="memory/add/provenance",
                )
                redacted = (
                    claim_report.redacted
                    + summary_report.redacted
                    + source_report.redacted
                    + provenance_report.redacted
                )
                if redacted:
                    provenance = f"{provenance} (pii_scrubbed={redacted})"

                atom = create_atom(
                    atom_type=args.type,
                    claim=claim,
                    summary=summary,
                    source=source,
                    source_type=args.source_type,
                    evidence=args.evidence,
                    confidence=args.confidence,
                    status=args.status,
                    entities=[args.entity] if args.entity else [],
                    tags=args.tag or [],
                    links=args.link or [],
                    privacy=args.privacy,
                    provenance=provenance,
                )
                written = atom_store.append(atom)
                if args.json:
                    print(json.dumps(written, indent=2, sort_keys=True))
                else:
                    print(f"✔ Atom appended: {written['id']} ({written['type']})")
                    if redacted:
                        print(f"  PII scrubbed from inputs: {redacted} token(s)")
                return 0

            item = store.add(
                kind=args.kind,
                title=args.title or input("Title: ").strip(),
                body=args.body or input("Body: ").strip(),
                entity=args.entity or "",
                tags=args.tag or [],
                layer=args.layer,
                source_ref=args.source_ref or "",
                confidence=args.confidence,
                authority=args.authority,
            )
            return _print_item_result(item, json_output=args.json, verb="added")

        if args.memory_command == "patch":
            updates = {}
            if args.status is not None:
                updates["status"] = args.status
            if args.summary is not None:
                summary, report = scrub(
                    args.summary,
                    root / "REDACT.md",
                    provenance="memory/patch/summary",
                )
                updates["summary"] = summary
                if report.redacted:
                    updates["provenance"] = f"shiroe-cli memory patch (pii_scrubbed={report.redacted})"
            if not updates:
                print("✘ No patch fields provided.")
                return 2
            patched = atom_store.patch(args.id, updates)
            if args.json:
                print(json.dumps(patched, indent=2, sort_keys=True))
            else:
                print(f"✔ Atom patched: {patched['id']}")
            return 0

        if args.memory_command == "index":
            from shiroe.memory.indexer import rebuild_index

            result = rebuild_index(root)
            if args.json:
                print(json.dumps(result, indent=2, sort_keys=True))
            else:
                print(f"✔ Indexed {result['atoms_indexed']} atom(s) at {result['path']}")
            return 0

        if args.memory_command == "health":
            from shiroe.memory.refine import build_health_report, write_health_report

            result = build_health_report(root)
            if not args.no_write:
                result = {**result, "written": write_health_report(root, result)}
            if args.json:
                print(json.dumps(result, indent=2, sort_keys=True))
            else:
                print(f"Memory health: {'pass' if result['passed'] else 'needs attention'}")
                print(f"Active atoms: {result['summary']['active_atoms']}")
                print(f"Duplicate groups: {result['summary']['duplicate_groups']}")
                if "written" in result:
                    print(f"Report: {result['written']['markdown']}")
            return 0 if result["passed"] or not args.strict else 1

        if args.memory_command == "refine":
            from shiroe.memory.refine import refine_memory

            result = refine_memory(root, dry_run=args.dry_run, strict=args.strict)
            if args.json:
                print(json.dumps(result, indent=2, sort_keys=True))
            else:
                mode = "dry run" if result["dry_run"] else "report written"
                print(f"Memory refine: {mode}")
                print(f"Proposals: {len(result['proposals'])}")
                for proposal in result["proposals"]:
                    target = proposal.get("atom_id") or ", ".join(proposal.get("atom_ids", []))
                    print(f"- {proposal['action']}: {target}")
            return 0 if result["passed"] or not args.strict else 1

        if args.memory_command == "render":
            from shiroe.memory.render import render_memory_view

            result = render_memory_view(root, args.view)
            if args.json:
                print(json.dumps(result, indent=2, sort_keys=True))
            else:
                if args.view == "all":
                    for item in result["rendered"]:
                        print(f"✔ Rendered {item['view']} -> {item['path']}")
                else:
                    print(f"✔ Rendered {result['view']} -> {result['path']}")
            return 0

        if args.memory_command == "search":
            # Canonical path: search the append-only atom store (same store
            # `memory add --claim` writes), so add -> search always round-trips.
            from shiroe.memory.search import search_atoms

            atom_kind = args.kind if args.kind in ATOM_TYPES else None
            atom_result = search_atoms(
                root,
                args.query or "",
                limit=args.limit,
                atom_type=atom_kind,
            )
            atom_matches = atom_result["matches"]
            if args.entity:
                wanted = args.entity.strip().lower()
                atom_matches = [
                    match for match in atom_matches
                    if any(
                        wanted in str(e.get("name", "") if isinstance(e, dict) else e).lower()
                        for e in match["atom"].get("entities", [])
                    )
                ]
            atom_rows = [
                {**match["atom"], "score": match["score"], "why_returned": match["why"]}
                for match in atom_matches
            ]

            # Legacy item store (memory/state) — deprecated, kept for
            # compatibility until callers migrate to atoms.
            items = store.search(
                args.query or "",
                entity=args.entity or "",
                kind=args.kind or "",
                layer=args.layer or "",
                limit=args.limit,
            )
            if items:
                print(
                    "⚠ deprecated: results include legacy memory items (memory/state). "
                    "The canonical store is the atom store — use `memory add --type/--claim/--source`.",
                    file=sys.stderr,
                )

            if args.json:
                rows = [item_to_dict(item) for item in items] + atom_rows
                print(json.dumps(rows, indent=2, sort_keys=True))
            else:
                for item in items:
                    _print_memory_item(item)
                for row in atom_rows:
                    print(f"{row['id']} [{row['type']}/{row['status']}] {row['claim']}")
                    print(f"  why: {row['why_returned']}")
                if not items and not atom_rows:
                    print("No memory items found.")
            return 0

        if args.memory_command == "get":
            item = store.get(args.id)
            if item is None:
                print(f"✘ memory item {args.id} not found")
                return 1
            return _print_item_result(item, json_output=args.json, verb="found")

        if args.memory_command == "update":
            item = store.update(
                args.id,
                kind=args.kind,
                title=args.title,
                body=args.body,
                entity=args.entity,
                tags=args.tag,
                layer=args.layer,
                source_ref=args.source_ref,
                confidence=args.confidence,
                authority=args.authority,
            )
            return _print_item_result(item, json_output=args.json, verb="updated")

        if args.memory_command == "history":
            events = store.history(args.id, limit=args.limit)
            if args.json:
                print(json.dumps([event_to_dict(event) for event in events], indent=2, sort_keys=True))
            else:
                for event in events:
                    item = f" item={event.item_id}" if event.item_id is not None else ""
                    print(f"{event.ts} {event.event}{item} {event.hash}")
                if not events:
                    print("No memory events found.")
            return 0

        if args.memory_command == "explain":
            item = store.explain(args.id, query=args.query or "")
            return _print_item_result(item, json_output=args.json, verb="explained")

        if args.memory_command == "views":
            written = store.generate_views()
            if args.json:
                print(json.dumps(written, indent=2, sort_keys=True))
            else:
                print("✔ generated markdown views")
                for name, path in sorted(written.items()):
                    print(f"  {name}: {path}")
            return 0
    except GuardRejection as exc:
        print(str(exc))
        return 1
    except (KeyError, ValueError, RuntimeError) as exc:
        print(f"✘ {exc}")
        return 1

    print("✘ unknown memory command")
    return 1


def cmd_factguard(args: argparse.Namespace) -> int:
    from shiroe.guards.fact_guard import check_claim, report, scan_path

    if args.factguard_command == "check":
        findings = check_claim(args.claim, source_refs=args.source_ref or [])
    elif args.factguard_command == "scan":
        findings = scan_path(Path(args.path))
    elif args.factguard_command == "report":
        findings = scan_path(_project_root() / "docs")
    else:
        print("✘ unknown factguard command")
        return 1

    print(report(findings, format=args.format))
    return 1 if any(f.severity == "high" for f in findings) else 0


def cmd_evidence(args: argparse.Namespace) -> int:
    from shiroe.guards.evidence_guard import (
        check_public_docs,
        check_store,
        grade_text,
        list_by_grade,
        report_findings,
        upgrade_evidence,
    )
    from shiroe.memory_state import card_to_dict, MemoryStore

    store = MemoryStore.from_root(_project_root())
    if args.evidence_command == "grade":
        if getattr(args, "source", None) is not None:
            from shiroe.memory.evidence import grade_claim

            result = grade_claim(
                args.path,
                source=args.source or "",
                source_type=args.source_type,
            )
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        text = Path(args.path).read_text(errors="ignore") if Path(args.path).exists() else args.path
        print(grade_text(text))
        return 0
    if args.evidence_command == "audit":
        from shiroe.memory.evidence import audit_evidence

        result = audit_evidence(_project_root())
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("passed", True) else 1
    if args.evidence_command == "check":
        path = Path(args.path)
        if path.exists() and path.name != "memory":
            issues = check_public_docs(path)
            print("\n".join(issues) if issues else "No EvidenceGuard findings.")
            return 1 if issues else 0
        findings = check_store(store)
        print(report_findings(findings), end="")
        return 1 if any(f.severity == "high" for f in findings) else 0
    if args.evidence_command == "list":
        cards = list_by_grade(store, args.grade)
        print(json.dumps([card_to_dict(card) for card in cards], indent=2, sort_keys=True))
        return 0
    if args.evidence_command == "upgrade":
        card = upgrade_evidence(store, args.id, args.source)
        print(json.dumps(card_to_dict(card), indent=2, sort_keys=True))
        return 0
    if args.evidence_command == "report":
        findings = check_store(store)
        print(report_findings(findings), end="")
        return 1 if any(f.severity == "high" for f in findings) else 0
    print("✘ unknown evidence command")
    return 1


def cmd_contradictions(args: argparse.Namespace) -> int:
    from shiroe.guards.contradiction_guard import (
        archive_conflict,
        format_conflicts,
        list_conflicts,
        resolve_conflict,
        show_conflict,
        write_conflicts,
    )
    from shiroe.memory_state import MemoryStore

    store = MemoryStore.from_root(_project_root())
    if args.contradictions_command == "scan":
        if getattr(args, "path", None) is None:
            from shiroe.memory.contradictions import scan_contradictions

            result = scan_contradictions(_project_root())
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        conflicts = list_conflicts(store)
        write_conflicts(store, conflicts)
        print(format_conflicts(conflicts, format=args.format), end="")
        return 1 if any(c.severity in {"high", "critical"} for c in conflicts) else 0
    if args.contradictions_command == "list":
        conflicts = list_conflicts(store)
        print(format_conflicts(conflicts, format=args.format), end="")
        return 0
    if args.contradictions_command == "show":
        try:
            from shiroe.memory.contradictions import show_contradiction

            print(json.dumps(show_contradiction(_project_root(), args.id), indent=2, sort_keys=True))
            return 0
        except KeyError:
            pass
        conflict = show_conflict(store, args.id)
        if conflict is None:
            print(f"✘ conflict {args.id} not found")
            return 1
        print(json.dumps(conflict.to_dict(), indent=2, sort_keys=True))
        return 0
    if args.contradictions_command == "propose":
        from shiroe.memory.contradictions import propose_resolution

        try:
            result = propose_resolution(_project_root(), args.id)
        except KeyError:
            print(f"✘ contradiction {args.id} not found")
            return 1
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.contradictions_command == "resolve":
        try:
            from shiroe.memory.contradictions import resolve_contradiction, show_contradiction

            show_contradiction(_project_root(), args.id)
            result = resolve_contradiction(
                _project_root(),
                args.id,
                winner=args.winner,
                reason=args.reason,
            )
        except KeyError:
            result = resolve_conflict(store, args.id, winner=args.winner, reason=args.reason)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.contradictions_command == "archive":
        result = archive_conflict(store, args.id)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    print("✘ unknown contradictions command")
    return 1


def cmd_privacy(args: argparse.Namespace) -> int:
    from shiroe.guards.privacy_guard import classify_text, format_findings, redact_file, scan_path

    root = _project_root()
    redact_md = root / "REDACT.md"
    if args.privacy_command == "scan":
        findings = scan_path(Path(args.path), redact_md_path=redact_md)
        print(format_findings(findings, format=args.format), end="")
        return 1 if findings and args.strict else 0
    if args.privacy_command == "classify":
        print(json.dumps(classify_text(args.text, redact_md_path=redact_md), indent=2, sort_keys=True))
        return 0
    if args.privacy_command == "redact":
        cleaned, finding = redact_file(Path(args.path), redact_md_path=redact_md)
        if args.suggest:
            print(cleaned)
        elif finding:
            print(format_findings([finding]), end="")
        else:
            print("No PrivacyGuard findings.")
        return 1 if finding else 0
    if args.privacy_command == "report":
        findings = scan_path(root / "docs", redact_md_path=redact_md)
        print(format_findings(findings, format=args.format), end="")
        return 1 if findings and args.strict else 0
    print("✘ unknown privacy command")
    return 1


def cmd_route(args: argparse.Namespace) -> int:
    from shiroe.routing.policy import classify_task, policy_json, route_report, validate_policy

    if args.route_command == "classify":
        decision = classify_task(args.text)
        print(json.dumps(decision.to_dict(), indent=2, sort_keys=True))
        return 0
    if args.route_command == "explain":
        decision = classify_task(args.text)
        print(f"{decision.domain} / {decision.weight} / {decision.lead}\n{decision.reason}")
        return 0
    if args.route_command == "policy":
        if args.policy_command == "show":
            print(policy_json(), end="")
            return 0
        if args.policy_command == "validate":
            issues = validate_policy()
            print("Route policy valid." if not issues else "\n".join(issues))
            return 1 if issues else 0
    if args.route_command == "report":
        print(route_report(), end="")
        return 0
    print("✘ unknown route command")
    return 1


def cmd_release(args: argparse.Namespace) -> int:
    from shiroe.release.checks import format_release, release_passed, run_release_check

    if args.release_command == "check":
        findings = run_release_check(_project_root())
        print(format_release(findings, format=args.format), end="")
        return 0 if release_passed(findings) else 1
    print("✘ unknown release command")
    return 1


def cmd_claims(args: argparse.Namespace) -> int:
    """SHR-66 / issue #172: capability evidence matrix + public-claim gate."""
    from shiroe.release.claim_gate import (
        build_capability_matrix, format_findings, format_matrix, scan_public_claims,
    )

    root = _project_root()
    if args.claims_command == "matrix":
        entries = build_capability_matrix(root)
        print(format_matrix(entries, format=args.format), end="")
        return 0
    if args.claims_command == "check":
        findings = scan_public_claims(root)
        print(format_findings(findings), end="")
        return 1 if findings else 0
    print("✘ unknown claims command")
    return 1


def cmd_team(args: argparse.Namespace) -> int:
    """vNext team compiler: compile | plan-show (PR 7)."""
    root = _project_root()
    sub = getattr(args, "team_command", None)

    if sub == "compile":
        from shiroe.teams import (
            NoEligibleCapabilityError, SelfReviewError, compile_team,
        )
        task_id = args.task_id or ("task_" + args.mission)
        try:
            plan = compile_team(
                root, task_id=task_id, mission_id=args.mission,
                policy_id=args.policy, active_harness=args.harness,
            )
        except (NoEligibleCapabilityError, SelfReviewError) as e:
            print(f"compile failed: {e}", file=sys.stderr)
            return 2
        print(json.dumps(plan.to_dict(), indent=2))
        return 0

    if sub == "plan-show":
        from shiroe.storage import StateDB
        db = StateDB(root); db.migrate()
        conn = db.connect()
        row = conn.execute(
            "SELECT task_id, mission_id, policy, state, created_at "
            "FROM team_runs WHERE id=?",
            (args.run_id,),
        ).fetchone()
        if row is None:
            print(f"unknown run_id {args.run_id!r}", file=sys.stderr)
            db.close()
            return 1
        task_id, mission, policy, state, created = row
        assignments = conn.execute(
            "SELECT seat_id, capability_id, score FROM team_assignments "
            "WHERE run_id=? ORDER BY seat_id",
            (args.run_id,),
        ).fetchall()
        steps = conn.execute(
            "SELECT step_name, state FROM execution_steps "
            "WHERE run_id=? ORDER BY id",
            (args.run_id,),
        ).fetchall()
        db.close()
        print(json.dumps({
            "run_id": args.run_id, "task_id": task_id,
            "mission": mission, "policy": policy, "state": state,
            "created_at": created,
            "assignments": [
                {"seat_id": s, "capability_id": c, "score": sc}
                for s, c, sc in assignments
            ],
            "steps": [{"step": s, "state": st} for s, st in steps],
        }, indent=2))
        return 0

    print("usage: shiroe team {compile|plan-show}", file=sys.stderr)
    return 1


def cmd_policy(args: argparse.Namespace) -> int:
    """vNext policy engine: show | check (ADR-0005)."""
    from shiroe.policy import (
        Action, ActionKind, AutonomyMode, evaluate, load_policy_stack,
    )
    root = _project_root()
    sub = getattr(args, "policy_command", None)
    if sub == "show":
        stack = load_policy_stack(root)
        for layer in stack:
            print(f"[{layer.name}]")
            if layer.denies:
                print("  deny: " + ", ".join(k.value for k in sorted(layer.denies, key=lambda x: x.value)))
            if layer.allows:
                print("  allow: " + ", ".join(k.value for k in sorted(layer.allows, key=lambda x: x.value)))
        return 0
    if sub == "check":
        try:
            kind = ActionKind(args.kind)
        except ValueError:
            print(f"unknown action kind: {args.kind}", file=sys.stderr)
            return 1
        try:
            mode = AutonomyMode(args.mode)
        except ValueError:
            print(f"unknown autonomy mode: {args.mode}", file=sys.stderr)
            return 1
        stack = load_policy_stack(root)
        d = evaluate(Action(kind, target=args.target or ""), stack, mode=mode)
        print(json.dumps({
            "verdict": d.verdict.value,
            "reason": d.reason,
            "deciding_layer": d.deciding_layer,
        }, indent=2))
        return 0 if d.allowed else 2
    print("usage: shiroe policy {show|check}", file=sys.stderr)
    return 1


def cmd_state(args: argparse.Namespace) -> int:
    """vNext canonical state: migrate | rebuild | verify (ADR-0001)."""
    from shiroe.storage import StateDB, EventLog
    from shiroe.storage import views as views_mod

    root = _project_root()
    db = StateDB(root)
    sub = getattr(args, "state_command", None)

    if sub == "migrate":
        applied = db.migrate()
        print(f"schema version: {db.schema_version()}")
        if applied:
            print("applied: " + ", ".join(applied))
        else:
            print("already up to date")
        print(f"tables: {len(db.tables())}")
        return 0

    if sub == "verify":
        db.migrate()
        log = EventLog(root, mirror_conn=db.connect())
        try:
            log.verify_chain()
        except Exception as e:  # noqa: BLE001
            print(f"CHAIN INVALID: {e}")
            return 2
        print("chain OK")
        return 0

    if sub == "rebuild":
        db.migrate()
        conn = db.connect()
        log = EventLog(root, mirror_conn=conn)
        n = log.replay_into(conn)
        written = views_mod.render_all(root, conn)
        print(f"replayed {n} event(s); regenerated {len(written)} view(s)")
        return 0

    print("usage: shiroe state {migrate|rebuild|verify}", file=sys.stderr)
    return 1


def cmd_doctor(args: argparse.Namespace) -> int:
    if getattr(args, "installation", False):
        from shiroe.release.manifest import build_manifest

        manifest = build_manifest(_project_root())
        if args.format == "json":
            print(json.dumps(manifest.to_dict(), indent=2, sort_keys=True))
        else:
            print(manifest.format_text(), end="")
        return 0

    from shiroe.release.doctor import doctor_passed, format_doctor, run_doctor

    checks = run_doctor(_project_root())
    print(format_doctor(checks, format=args.format), end="")
    return 0 if doctor_passed(checks) else 1


def cmd_version(args: argparse.Namespace) -> int:
    from shiroe import __version__ as _v

    if not getattr(args, "verbose", False):
        print(f"shiroe {_v}")
        return 0

    from shiroe.release.manifest import build_manifest

    manifest = build_manifest(_project_root())
    if args.format == "json":
        print(json.dumps(manifest.to_dict(), indent=2, sort_keys=True))
    else:
        print(manifest.format_text(), end="")
    return 0


def _print_item_result(item, *, json_output: bool, verb: str) -> int:
    from shiroe.memory_state import item_to_dict

    if json_output:
        print(json.dumps(item_to_dict(item), indent=2, sort_keys=True))
    else:
        print(f"✔ memory item {verb}: {item.id}")
        _print_memory_item(item)
    return 0


def _print_memory_item(item) -> None:
    print(f"[{item.id}] {item.title}")
    print(f"  kind={item.kind} layer={item.layer} entity={item.entity or '(none)'}")
    print(f"  source_ref={item.source_ref or '(none)'} confidence={item.confidence} authority={item.authority}")
    if item.why_returned:
        print(f"  why_returned={item.why_returned}")
    if item.tags:
        print(f"  tags={', '.join(item.tags)}")
    print(f"  body={item.body}")


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    from shiroe import __version__ as _v
    p = argparse.ArgumentParser(prog="shiroe", description=f"Shiroe CLI v{_v}")
    p.add_argument("--version", action="version", version=f"shiroe {_v}")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="Print hot.md + tier")

    wd = sub.add_parser("write-decision", help="Append decision to memory/DECISIONS.md")
    wd.add_argument("--title");  wd.add_argument("--why")
    wd.add_argument("--evidence"); wd.add_argument("--grade", choices=["high","medium","low"], default="medium")

    gr = sub.add_parser("grade", help="Grade a claim")
    gr.add_argument("claim", nargs="?", default="")

    ap = sub.add_parser("audit-privacy", help="Scan memory/ for PII (read-only)")
    ap.add_argument("--directory", help="Directory to scan (default: memory/)")
    ap.add_argument("--strict", action="store_true",
                    help="Exit non-zero on any unredacted hit (suitable for CI gate)")
    ap.add_argument("--fail-classes", default="",
                    help="Comma-separated redaction classes with ZERO tolerance "
                         "(e.g. 'credentials'); any hit in these classes fails the scan")
    ap.add_argument("--max-hits", type=int, default=0,
                    help="Legacy threshold ceiling: total hits allowed before failing (0=disabled)")
    ap.add_argument("--max-files", type=int, default=0,
                    help="Legacy threshold ceiling: files hit allowed before failing (0=disabled)")

    audit_p = sub.add_parser("audit", help="Structural validation and audit reports")
    audit_sub = audit_p.add_subparsers(dest="audit_command")
    audit_report = audit_sub.add_parser("report", help="Generate audit report")
    audit_report.add_argument("--since", default="")
    audit_report.add_argument("--format", choices=["text", "md", "json"], default="text")

    init_p = sub.add_parser("init", help="Scaffold memory/ + config/ + privacy templates")
    init_p.add_argument("--directory", help="Target dir (default: cwd)")
    init_p.add_argument("--name", help="Project name (non-interactive)")
    init_p.add_argument("--privacy", choices=["abstract","exact","local-only"])
    init_p.add_argument("--tier", choices=["auto","free","standard","god-mode"])
    init_p.add_argument("--parent", help="Parent project path")

    sub.add_parser("db-status", help="Report backend (sqlite/duckdb) + extras")

    memory = sub.add_parser("memory", help="Structured local memory state")
    memory_sub = memory.add_subparsers(dest="memory_command", required=True)

    mem_propose = memory_sub.add_parser("propose", help="Create a guarded memory proposal JSON file")
    mem_propose.add_argument("claim")
    mem_propose.add_argument("--out", default="proposal.json")
    mem_propose.add_argument("--json", action="store_true")

    mem_write = memory_sub.add_parser("write", help="Write a guarded memory proposal")
    mem_write.add_argument("--from", dest="from_path", required=True)
    mem_write.add_argument("--json", action="store_true")

    mem_list_cards = memory_sub.add_parser("list", help="List memory cards")
    mem_list_cards.add_argument("--type")
    mem_list_cards.add_argument("--status")
    mem_list_cards.add_argument("--limit", type=int, default=200)
    mem_list_cards.add_argument("--atoms", action="store_true",
                                help="List append-only JSONL atoms instead of memory cards")
    mem_list_cards.add_argument("--json", action="store_true")

    mem_show = memory_sub.add_parser("show", help="Show a memory card")
    mem_show.add_argument("id")

    mem_archive = memory_sub.add_parser("archive", help="Archive a memory card")
    mem_archive.add_argument("id")
    mem_archive.add_argument("--json", action="store_true")

    mem_supersede = memory_sub.add_parser("supersede", help="Mark one memory card superseded by another")
    mem_supersede.add_argument("id")
    mem_supersede.add_argument("--with", dest="with_id", required=True)
    mem_supersede.add_argument("--json", action="store_true")

    mem_add = memory_sub.add_parser("add", help="Add a structured memory item")
    mem_add.add_argument("--kind", default="note")
    mem_add.add_argument("--title")
    mem_add.add_argument("--body")
    mem_add.add_argument("--entity")
    mem_add.add_argument("--tag", action="append")
    mem_add.add_argument("--layer", choices=["L0", "L1", "L2", "L3"], default="L1")
    mem_add.add_argument("--source-ref")
    mem_add.add_argument("--confidence", choices=["high", "medium", "low", "unknown"], default="medium")
    mem_add.add_argument("--authority", choices=["canonical", "confirmed", "inferred", "unknown"], default="unknown")
    mem_add.add_argument("--type", choices=[
        "fact", "decision", "risk", "task", "preference",
        "contradiction", "source", "error", "test", "event",
    ], help="Atom type. With --claim and --source, appends a JSONL atom.")
    mem_add.add_argument("--claim")
    mem_add.add_argument("--summary")
    mem_add.add_argument("--source")
    mem_add.add_argument("--source-type", choices=[
        "user", "file", "tool", "session", "git", "manual", "unknown",
    ], default="manual")
    mem_add.add_argument("--evidence", choices=["A", "B", "C", "D", "F", "unverified"], default="unverified")
    mem_add.add_argument("--status", choices=["active", "stale", "superseded", "disputed", "archived"], default="active")
    mem_add.add_argument("--privacy", choices=["public-safe", "private", "local-only", "unknown"], default="unknown")
    mem_add.add_argument("--provenance")
    mem_add.add_argument("--link", action="append")
    mem_add.add_argument("--json", action="store_true")

    mem_patch = memory_sub.add_parser("patch", help="Patch one memory atom")
    mem_patch.add_argument("id")
    mem_patch.add_argument("--status", choices=["active", "stale", "superseded", "disputed", "archived"])
    mem_patch.add_argument("--summary")
    mem_patch.add_argument("--json", action="store_true")

    mem_index = memory_sub.add_parser("index", help="Rebuild SQLite memory index")
    mem_index.add_argument("--json", action="store_true")

    mem_health = memory_sub.add_parser("health", help="Generate memory health reports")
    mem_health.add_argument("--json", action="store_true")
    mem_health.add_argument("--strict", action="store_true")
    mem_health.add_argument("--no-write", action="store_true", help="Report without writing memory/reports")

    mem_refine = memory_sub.add_parser("refine", help="Propose safe memory cleanup actions")
    mem_refine.add_argument("--dry-run", action="store_true")
    mem_refine.add_argument("--json", action="store_true")
    mem_refine.add_argument("--strict", action="store_true")

    mem_render = memory_sub.add_parser("render", help="Render Markdown views from atoms")
    mem_render.add_argument("view", choices=[
        "hot.md", "index.md", "decisions", "risks", "contradictions", "all",
    ])
    mem_render.add_argument("--json", action="store_true")

    rec = sub.add_parser("recall", help="Recall memory atoms by query")
    rec.add_argument("query")
    rec.add_argument("--limit", type=int, default=5)
    rec.add_argument("--json", action="store_true")
    rec.add_argument("--type", choices=[
        "fact", "decision", "risk", "task", "preference",
        "contradiction", "source", "error", "test", "event",
    ])
    rec.add_argument("--status", choices=["active", "stale", "superseded", "disputed", "archived"], default="active")

    exp = sub.add_parser("explain-search", help="Explain memory search ranking")
    exp.add_argument("query")
    exp.add_argument("--limit", type=int, default=3)
    exp.add_argument("--json", action="store_true")
    exp.add_argument("--type", choices=[
        "fact", "decision", "risk", "task", "preference",
        "contradiction", "source", "error", "test", "event",
    ])
    exp.add_argument("--status", choices=["active", "stale", "superseded", "disputed", "archived"])

    cost = sub.add_parser("cost", help="Estimate and route memory operation cost")
    cost_sub = cost.add_subparsers(dest="cost_command", required=True)
    cost_est = cost_sub.add_parser("estimate", help="Estimate text token cost")
    cost_est.add_argument("--text", default="")

    cost_route = cost_sub.add_parser("route", help="Route an operation to the cheapest safe executor")
    cost_route.add_argument("--operation", required=True)
    cost_route.add_argument("--text", default="")
    cost_route.add_argument("--approval", action="store_true")
    cost_route.add_argument("--render-mode", action="store_true")
    cost_route.add_argument("--duplicate", action="store_true")
    cost_route.add_argument("--status-change", action="store_true")
    cost_route.add_argument("--public-claim", action="store_true")
    cost_route.add_argument("--contradiction", action="store_true")

    cost_sub.add_parser("report", help="Print cost policy summary")
    cost_audit = cost_sub.add_parser("audit", help="Audit artifact token budgets")
    cost_audit.add_argument("--strict", action="store_true")

    mem_search = memory_sub.add_parser("search", help="Search structured memory state")
    mem_search.add_argument("query", nargs="?", default="")
    mem_search.add_argument("--entity")
    mem_search.add_argument("--kind")
    mem_search.add_argument("--layer", choices=["L0", "L1", "L2", "L3"])
    mem_search.add_argument("--limit", type=int, default=10)
    mem_search.add_argument("--json", action="store_true")

    mem_get = memory_sub.add_parser("get", help="Get a memory item by id")
    mem_get.add_argument("id", type=int)
    mem_get.add_argument("--json", action="store_true")

    mem_update = memory_sub.add_parser("update", help="Update a memory item by id")
    mem_update.add_argument("id", type=int)
    mem_update.add_argument("--kind")
    mem_update.add_argument("--title")
    mem_update.add_argument("--body")
    mem_update.add_argument("--entity")
    mem_update.add_argument("--tag", action="append")
    mem_update.add_argument("--layer", choices=["L0", "L1", "L2", "L3"])
    mem_update.add_argument("--source-ref")
    mem_update.add_argument("--confidence", choices=["high", "medium", "low"])
    mem_update.add_argument("--authority", choices=["canonical", "confirmed", "inferred", "unknown"])
    mem_update.add_argument("--json", action="store_true")

    mem_history = memory_sub.add_parser("history", help="Show memory state event history")
    mem_history.add_argument("id", type=int, nargs="?")
    mem_history.add_argument("--limit", type=int, default=20)
    mem_history.add_argument("--json", action="store_true")

    mem_explain = memory_sub.add_parser("explain", help="Explain why a memory item is relevant")
    mem_explain.add_argument("id", type=int)
    mem_explain.add_argument("--query", default="")
    mem_explain.add_argument("--json", action="store_true")

    mem_views = memory_sub.add_parser("views", help="Generate Markdown views from structured state")
    mem_views.add_argument("--json", action="store_true")

    factguard = sub.add_parser("factguard", help="Scan or check unsupported claims")
    fact_sub = factguard.add_subparsers(dest="factguard_command", required=True)
    fact_scan = fact_sub.add_parser("scan", help="Scan Markdown path")
    fact_scan.add_argument("path")
    fact_scan.add_argument("--format", choices=["text", "md"], default="text")
    fact_check = fact_sub.add_parser("check", help="Check one claim")
    fact_check.add_argument("--claim", required=True)
    fact_check.add_argument("--source-ref", action="append")
    fact_check.add_argument("--format", choices=["text", "md"], default="text")
    fact_report = fact_sub.add_parser("report", help="Report on docs/")
    fact_report.add_argument("--format", choices=["text", "md"], default="text")

    evidence = sub.add_parser("evidence", help="Check and manage evidence grades")
    evidence_sub = evidence.add_subparsers(dest="evidence_command", required=True)
    ev_grade = evidence_sub.add_parser("grade", help="Grade a claim, file, or text")
    ev_grade.add_argument("path")
    ev_grade.add_argument("--source")
    ev_grade.add_argument("--source-type", default="unknown", choices=[
        "user", "file", "tool", "session", "git", "manual", "unknown",
    ])
    evidence_sub.add_parser("audit", help="Audit atom evidence")
    ev_check = evidence_sub.add_parser("check", help="Check memory or docs path")
    ev_check.add_argument("path")
    ev_list = evidence_sub.add_parser("list", help="List memory cards by evidence grade")
    ev_list.add_argument("--grade", required=True, choices=["A", "B", "C", "D", "F"])
    ev_upgrade = evidence_sub.add_parser("upgrade", help="Upgrade card evidence with a source")
    ev_upgrade.add_argument("id")
    ev_upgrade.add_argument("--source", required=True)
    evidence_sub.add_parser("report", help="Report low-evidence memory cards")

    facts = sub.add_parser("facts", help="Audit unsupported atom fact claims")
    facts_sub = facts.add_subparsers(dest="facts_command", required=True)
    facts_sub.add_parser("audit", help="Audit atoms for unsupported claims")

    contradictions = sub.add_parser("contradictions", help="Scan and resolve memory conflicts")
    contradictions_sub = contradictions.add_subparsers(dest="contradictions_command", required=True)
    con_scan = contradictions_sub.add_parser("scan", help="Scan memory cards for contradictions")
    con_scan.add_argument("path", nargs="?", default=None)
    con_scan.add_argument("--format", choices=["text", "json"], default="text")
    con_list = contradictions_sub.add_parser("list", help="List current contradictions")
    con_list.add_argument("--format", choices=["text", "json"], default="text")
    con_show = contradictions_sub.add_parser("show", help="Show one contradiction")
    con_show.add_argument("id")
    con_prop = contradictions_sub.add_parser("propose", help="Propose an atom contradiction resolution")
    con_prop.add_argument("id")
    con_resolve = contradictions_sub.add_parser("resolve", help="Resolve a contradiction")
    con_resolve.add_argument("id")
    con_resolve.add_argument("--winner", required=True)
    con_resolve.add_argument("--reason", required=True)
    con_archive = contradictions_sub.add_parser("archive", help="Archive a contradiction")
    con_archive.add_argument("id")

    privacy = sub.add_parser("privacy", help="Scan, classify, and redact sensitive text")
    privacy_sub = privacy.add_subparsers(dest="privacy_command", required=True)
    privacy_scan = privacy_sub.add_parser("scan", help="Scan a path for sensitive material")
    privacy_scan.add_argument("path")
    privacy_scan.add_argument("--format", choices=["text", "json"], default="text")
    privacy_scan.add_argument("--strict", action="store_true")
    privacy_redact = privacy_sub.add_parser("redact", help="Print redacted file content or findings")
    privacy_redact.add_argument("path")
    privacy_redact.add_argument("--suggest", action="store_true")
    privacy_classify = privacy_sub.add_parser("classify", help="Classify a text snippet")
    privacy_classify.add_argument("text")
    privacy_report = privacy_sub.add_parser("report", help="Scan docs/ for sensitive material")
    privacy_report.add_argument("--format", choices=["text", "json"], default="text")
    privacy_report.add_argument("--strict", action="store_true")

    route = sub.add_parser("route", help="Classify tasks against the local routing policy")
    route_sub = route.add_subparsers(dest="route_command", required=True)
    route_classify = route_sub.add_parser("classify", help="Classify a task")
    route_classify.add_argument("text")
    route_explain = route_sub.add_parser("explain", help="Explain a task route")
    route_explain.add_argument("text")
    route_policy = route_sub.add_parser("policy", help="Show or validate route policy")
    route_policy_sub = route_policy.add_subparsers(dest="policy_command", required=True)
    route_policy_sub.add_parser("show", help="Print route policy")
    route_policy_sub.add_parser("validate", help="Validate route policy")
    route_sub.add_parser("report", help="Generate route report")

    from shiroe import cli_capability
    cli_capability.register(sub)

    from shiroe import cli_providers
    cli_providers.register(sub)

    policy = sub.add_parser("policy", help="vNext policy engine (precedence + autonomy)")
    policy_sub = policy.add_subparsers(dest="policy_command", required=True)
    policy_sub.add_parser("show", help="Print the merged policy stack")
    p_check = policy_sub.add_parser("check", help="Evaluate one action against the current stack")
    p_check.add_argument("kind", help="ActionKind value, e.g. 'network', 'fs.write'")
    p_check.add_argument("--target", default=None)
    p_check.add_argument("--mode", default="auto-safe",
                         choices=["suggest", "auto-safe", "policy-bound"])

    team = sub.add_parser("team", help="vNext team compiler (PR 7)")
    team_sub = team.add_subparsers(dest="team_command", required=True)
    t_compile = team_sub.add_parser("compile", help="Compile a team plan for a mission")
    t_compile.add_argument("mission")
    t_compile.add_argument("--task-id", default=None)
    t_compile.add_argument("--policy", default="balanced")
    t_compile.add_argument("--harness", default="claude-code")
    t_show = team_sub.add_parser("plan-show", help="Print a persisted team plan")
    t_show.add_argument("run_id")

    state = sub.add_parser("state", help="vNext canonical state (SQLite v2)")
    state_sub = state.add_subparsers(dest="state_command", required=True)
    state_sub.add_parser("migrate", help="Apply pending SQLite v2 migrations")
    state_sub.add_parser("rebuild", help="Replay JSONL events; regenerate views")
    state_sub.add_parser("verify",  help="Verify JSONL hash chain")

    release = sub.add_parser("release", help="Run release readiness checks")
    release_sub = release.add_subparsers(dest="release_command", required=True)
    release_check = release_sub.add_parser("check", help="Run local release checks")
    release_check.add_argument("--format", choices=["text", "md", "json"], default="text")

    claims = sub.add_parser("claims", help="Capability evidence matrix + public-claim gate (SHR-66)")
    claims_sub = claims.add_subparsers(dest="claims_command", required=True)
    claims_matrix = claims_sub.add_parser("matrix", help="Print the capability evidence matrix")
    claims_matrix.add_argument("--format", choices=["text", "json"], default="text")
    claims_sub.add_parser("check", help="Scan public docs for blocked claim patterns")

    doctor = sub.add_parser("doctor", help="Run local Shiroe health checks")
    doctor.add_argument("--format", choices=["text", "json"], default="text")
    doctor.add_argument("--installation", action="store_true",
                        help="Report the installed-state manifest (identity, version, git SHA, content digests) instead of the standard health checks")

    version_p = sub.add_parser("version", help="Print version info")
    version_p.add_argument("--verbose", action="store_true",
                           help="Print the full installed-state manifest instead of just the version string")
    version_p.add_argument("--format", choices=["text", "json"], default="text")

    prompt = sub.add_parser("prompt", help="Classify and rewrite task prompts")
    prompt_sub = prompt.add_subparsers(dest="prompt_command", required=True)
    prompt_classify = prompt_sub.add_parser("classify", help="Classify a raw prompt")
    prompt_classify.add_argument("prompt")
    prompt_classify.add_argument("--json", action="store_true")
    prompt_rewrite = prompt_sub.add_parser("rewrite", help="Rewrite a prompt into a task brief")
    prompt_rewrite.add_argument("prompt")
    prompt_rewrite.add_argument("--json", action="store_true")
    prompt_brief = prompt_sub.add_parser("brief", help="Return structured brief fields")
    prompt_brief.add_argument("prompt")
    prompt_brief.add_argument("--json", action="store_true")
    prompt_inject = prompt_sub.add_parser("inject", help="Wrap a task brief for a target harness")
    prompt_inject.add_argument("prompt")
    prompt_inject.add_argument("--target", default="codex", choices=["codex", "claude", "cursor", "github", "human"])
    prompt_inject.add_argument("--json", action="store_true")

    handoff = sub.add_parser("handoff", help="Write cross-agent handoff artifacts")
    handoff_sub = handoff.add_subparsers(dest="handoff_command", required=True)
    for target in ["codex", "claude", "cursor", "github", "human"]:
        handoff_target = handoff_sub.add_parser(target, help=f"Write {target} handoff")
        handoff_target.add_argument("--objective", default="Continue from current Shiroe memory state.")
        handoff_target.add_argument("--include-private", action="store_true",
                                    help="Also export 'private'/'unknown' atoms (audited override); "
                                         "'local-only' atoms are never exported")
        handoff_target.add_argument("--json", action="store_true")

    loop = sub.add_parser("loop", help="Plan and run bounded observe-only loops")
    loop_sub = loop.add_subparsers(dest="loop_command", required=True)
    loop_plan = loop_sub.add_parser("plan", help="Create a loop contract")
    loop_plan.add_argument("goal")
    loop_plan.add_argument("--team", default="lean")
    loop_plan.add_argument("--max-iterations", type=int, default=3)
    loop_plan.add_argument("--json", action="store_true")
    loop_run = loop_sub.add_parser("run", help="Run a bounded deterministic loop")
    loop_run.add_argument("goal")
    loop_run.add_argument("--team", default="lean")
    loop_run.add_argument("--max-iterations", type=int, default=3)
    loop_run.add_argument("--json", action="store_true")
    loop_status = loop_sub.add_parser("status", help="Show latest loop status")
    loop_status.add_argument("--json", action="store_true")
    loop_report = loop_sub.add_parser("report", help="Show latest or selected loop report")
    loop_report.add_argument("--loop-id")
    loop_report.add_argument("--json", action="store_true")

    return p


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    handlers = {
        "status": cmd_status,
        "write-decision": cmd_write_decision,
        "grade": cmd_grade,
        "audit-privacy": cmd_audit_privacy,
        "audit": cmd_audit,
        "init": cmd_init,
        "db-status": cmd_db_status,
        "memory": cmd_memory,
        "recall": cmd_recall,
        "explain-search": cmd_explain_search,
        "cost": cmd_cost,
        "factguard": cmd_factguard,
        "evidence": cmd_evidence,
        "facts": cmd_facts,
        "contradictions": cmd_contradictions,
        "privacy": cmd_privacy,
        "route": cmd_route,
        "capability": lambda a: __import__("shiroe.cli_capability", fromlist=["handle"]).handle(a),
        "providers": lambda a: __import__("shiroe.cli_providers", fromlist=["handle"]).handle(a),
        "policy": cmd_policy,
        "team": cmd_team,
        "state": cmd_state,
        "release": cmd_release,
        "claims": cmd_claims,
        "doctor": cmd_doctor,
        "version": cmd_version,
        "prompt": cmd_prompt,
        "handoff": cmd_handoff,
        "loop": cmd_loop,
    }
    handler = handlers.get(args.command)
    if not handler:
        parser.print_help(); sys.exit(1)
    sys.exit(handler(args))


if __name__ == "__main__":
    main()
