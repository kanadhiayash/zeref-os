"""
privacy-audit: allow-file "CLI help text names example commands and env-var-shaped tokens (SHIROE_ALLOW_*, GITHUB_TOKEN) as documentation of the security policy."

shiroe.cli — Reference CLI for Shiroe (Sprint 2).

Commands:
    shiroe status          Print hot.md summary + active tier
    shiroe write-decision  Write a decision to canonical memory
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
    """Write a decision through canonical memory and regenerate views."""
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
    except ValueError as e:
        print(f"✘ {e}")
        return 2

    print(f"✔ Decision written to canonical memory; regenerated {result.target}")
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
    from shiroe.memory.recall import recall, recall_to_legacy_dict

    recall_result = recall(
        _project_root(),
        args.query,
        limit=args.limit,
        atom_type=args.type,
        status=args.status,
    )
    result = recall_to_legacy_dict(recall_result)
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
    print("✘ cost command was removed in vNext; use execution budget primitives")
    return 2


def cmd_facts(args: argparse.Namespace) -> int:
    print("✘ facts command was removed in vNext; use verify")
    return 2



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
    from dataclasses import asdict

    from shiroe.audit.logger import AuditLogger
    from shiroe.memory.models import MemoryWrite
    from shiroe.memory.search import search_memory
    from shiroe.memory.service import MemoryNotFoundError, MemoryService
    from shiroe.memory.views import render_views
    from shiroe.verification import VerificationEngine

    root = _project_root()
    service = MemoryService(root)

    def _record_payload(record) -> dict:
        data = asdict(record)
        data["type"] = record.kind
        data["evidence"] = record.evidence_grade
        data["privacy"] = record.privacy_class
        data["tags"] = list(record.tags)
        return data

    try:
        if args.memory_command == "write":
            payload = json.loads(Path(args.from_path).read_text(encoding="utf-8"))
            proposal = _memory_write_from_payload(payload)
            report = VerificationEngine(root).verify_memory_write(proposal)
            audit = AuditLogger.from_root(root)
            if report.status.value == "block":
                reason = "; ".join(
                    finding.message
                    for check in report.checks
                    for finding in check.findings
                ) or "verification blocked"
                audit.append(
                    event_type="guard_failure",
                    status="blocked",
                    reason=reason,
                    file=str(args.from_path),
                    guards_run=[check.name for check in report.checks],
                )
                audit.append(
                    event_type="memory_write",
                    status="blocked",
                    reason=reason,
                    file=str(args.from_path),
                    guards_run=[check.name for check in report.checks],
                )
                print(json.dumps(_verification_report_to_dict(report), indent=2, sort_keys=True))
                return 1
            record = service.write(proposal)
            audit.append(
                event_type="memory_write",
                status="accepted",
                reason="accepted guarded write",
                file=str(args.from_path),
                memory_id=record.id,
                guards_run=[check.name for check in report.checks],
            )
            if args.json:
                print(json.dumps(_record_payload(record), indent=2, sort_keys=True))
            else:
                print(f"✔ memory written: {record.id}")
            return 0

        if args.memory_command == "list":
            records = service.list(
                kinds=(args.type,) if args.type else None,
                statuses=(args.status,) if args.status else ("active",),
                limit=args.limit,
            )
            if args.json:
                print(json.dumps([_record_payload(record) for record in records], indent=2, sort_keys=True))
            else:
                for record in records:
                    print(f"{record.id} {record.kind} {record.status} {record.title}")
                if not records:
                    print("No memory records found.")
            return 0

        if args.memory_command == "show":
            record = service.get(args.id)
            print(json.dumps(_record_payload(record), indent=2, sort_keys=True))
            return 0

        if args.memory_command == "archive":
            record = service.archive(args.id)
            print(json.dumps(_record_payload(record), indent=2, sort_keys=True) if args.json else f"✔ archived {record.id}")
            return 0

        if args.memory_command == "supersede":
            old = service.supersede(args.id)
            replacement = service.get(args.with_id)
            result = {"superseded": _record_payload(old), "replacement": _record_payload(replacement)}
            print(json.dumps(result, indent=2, sort_keys=True) if args.json else f"✔ {old.id} superseded by {replacement.id}")
            return 0

        if args.memory_command == "add":
            record = service.write(
                MemoryWrite(
                    kind=args.type or args.kind,
                    title=args.title or (args.claim or input("Title: ").strip()),
                    claim=args.claim or args.body or input("Body: ").strip(),
                    summary=args.summary or "",
                    source_refs=(args.source or args.source_ref or "user-input",),
                    evidence_grade=args.evidence,
                    privacy_class=_canonical_privacy(args.privacy),
                    confidence=args.confidence,
                    tags=tuple(args.tag or ()),
                )
            )
            if args.json:
                print(json.dumps(_record_payload(record), indent=2, sort_keys=True))
            else:
                print(f"✔ memory written: {record.id}")
            return 0

        if args.memory_command == "search":
            result = search_memory(root, args.query or "", limit=args.limit, kinds=(args.kind,) if args.kind else None)
            if args.json:
                print(json.dumps({
                    "query": result.query,
                    "tokens": list(result.tokens),
                    "abstained": result.abstained,
                    "hits": [
                        {"record": _record_payload(hit.record), "score": hit.score, "why": hit.why}
                        for hit in result.hits
                    ],
                }, indent=2, sort_keys=True))
            else:
                for hit in result.hits:
                    print(f"{hit.record.id} score={hit.score} {hit.record.claim}")
                if not result.hits:
                    print("No matching memory records found.")
            return 0

        if args.memory_command == "views":
            paths = render_views(root)
            payload = {"rendered": [str(path) for path in paths]}
            print(json.dumps(payload, indent=2, sort_keys=True) if args.json else "\n".join(payload["rendered"]))
            return 0

        if args.memory_command == "history":
            events = service.history(args.id)
            events = events[:args.limit]
            if args.json:
                print(json.dumps([asdict(event) for event in events], indent=2, sort_keys=True))
            else:
                for event in events:
                    print(f"{event.timestamp} {event.event_type} {event.target or ''}")
                if not events:
                    print("No memory events found.")
            return 0

        if args.memory_command == "get":
            record = service.get(args.id)
            print(json.dumps(_record_payload(record), indent=2, sort_keys=True) if args.json else record.claim)
            return 0

        if args.memory_command == "patch":
            if args.status == "archived":
                record = service.archive(args.id)
            elif args.status == "superseded":
                record = service.supersede(args.id)
            else:
                print("✘ canonical patch currently supports --status archived|superseded")
                return 2
            print(json.dumps(_record_payload(record), indent=2, sort_keys=True) if args.json else f"✔ patched {record.id}")
            return 0

        if args.memory_command == "render":
            from shiroe.memory.render import render_memory_view

            result = render_memory_view(root, args.view)
            print(json.dumps(result, indent=2, sort_keys=True) if args.json else f"✔ Rendered {args.view}")
            return 0

        if args.memory_command in {"propose", "health", "refine", "update", "explain"}:
            print(f"✘ memory {args.memory_command} was removed in vNext; use memory write/list/show/search/views")
            return 2

    except MemoryNotFoundError as exc:
        print(f"✘ memory {exc.args[0]} not found")
        return 1
    except (KeyError, ValueError, RuntimeError) as exc:
        print(f"✘ {exc}")
        return 1

    print("✘ unknown memory command")
    return 1


def _memory_write_from_payload(payload: dict) -> "MemoryWrite":
    from shiroe.memory.models import MemoryWrite

    return MemoryWrite(
        kind=str(payload.get("kind") or payload.get("type") or "note"),
        title=str(payload.get("title") or payload.get("claim") or "Memory"),
        claim=str(payload.get("claim") or payload.get("body") or ""),
        summary=str(payload.get("summary") or ""),
        source_refs=tuple(str(ref) for ref in (payload.get("source_refs") or payload.get("sources") or ["user-input"])),
        confidence=str(payload.get("confidence") or "unknown"),
        evidence_grade=str(payload.get("evidence_grade") or payload.get("evidence") or "C"),
        privacy_class=_canonical_privacy(str(payload.get("privacy_class") or payload.get("privacy") or "internal")),
        tags=tuple(str(tag) for tag in (payload.get("tags") or ())),
    )


def _canonical_privacy(value: str) -> str:
    return {
        "public-safe": "public",
        "private": "internal",
        "local-only": "restricted",
        "unknown": "internal",
    }.get(value, value or "internal")


def _verification_report_to_dict(report) -> dict:
    from dataclasses import asdict

    return asdict(report)

def cmd_factguard(args: argparse.Namespace) -> int:
    print("✘ factguard command was removed in vNext; use verify")
    return 2


def cmd_evidence(args: argparse.Namespace) -> int:
    print("✘ evidence command was removed in vNext; use verify")
    return 2


def cmd_contradictions(args: argparse.Namespace) -> int:
    print("✘ contradictions command was removed in vNext; use verify")
    return 2


def cmd_privacy(args: argparse.Namespace) -> int:
    print("✘ privacy command was removed in vNext; use verify")
    return 2



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

    wd = sub.add_parser("write-decision", help="Write decision to canonical memory")
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

    mem_health = memory_sub.add_parser("health", help="Generate memory health reports")
    mem_health.add_argument("--json", action="store_true")
    mem_health.add_argument("--strict", action="store_true")
    mem_health.add_argument("--no-write", action="store_true", help="Report without writing memory/reports")

    mem_refine = memory_sub.add_parser("refine", help="Propose safe memory cleanup actions")
    mem_refine.add_argument("--dry-run", action="store_true")
    mem_refine.add_argument("--json", action="store_true")
    mem_refine.add_argument("--strict", action="store_true")

    mem_render = memory_sub.add_parser("render", help="Render Markdown views from canonical memory")
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
        "route": cmd_route,
        "capability": lambda a: __import__("shiroe.cli_capability", fromlist=["handle"]).handle(a),
        "providers": lambda a: __import__("shiroe.cli_providers", fromlist=["handle"]).handle(a),
        "policy": cmd_policy,
        "state": cmd_state,
        "release": cmd_release,
        "claims": cmd_claims,
        "doctor": cmd_doctor,
        "version": cmd_version,
        "prompt": cmd_prompt,
        "handoff": cmd_handoff,
    }
    handler = handlers.get(args.command)
    if not handler:
        parser.print_help(); sys.exit(1)
    sys.exit(handler(args))


if __name__ == "__main__":
    main()
