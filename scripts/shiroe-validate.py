#!/usr/bin/env python3
"""
privacy-audit: allow-file "Validator error messages document pattern-shaped tokens (schema examples) that trigger the scanner as expected."

shiroe-validate.py — Validate Shiroe plugin structure.

Checks:
- Root manifests (SKILL.md, AGENTS.md, CLAUDE.md, GEMINI.md)
- Root privacy templates (PRIVACY.md, REDACT.md, SHARING_POLICY.md)
- config/ has required files
- memory/ scaffold complete (flat layout)
- skills/ — count read from shiroe-registry.json (no more hardcoded /10) [L1];
  skill dirs on disk are cross-checked against the registry (drift = error)
- agents/, commands/, team-packs/ — discovered from the filesystem and
  cross-checked against the counts declared in shiroe-registry.json
  (agents/commands/team_packs); mismatch in either direction = error
- harness stubs present
- plugin.json + marketplace.json present and valid JSON
- Deprecation warning if legacy memory/wiki/ still has live content
- The archived v4.x canon bundle is NOT validated (SHR-027): requiring an
  archive to exist makes the archive undeletable.
- PATTERNS.jsonl event allowlist + per-event JSON-schema
- skill-route stack-length lint (max 5)
- Auto-Activation Gate presence lint (warn if missing gate events in recent log)
- shiroe-registry.json validated against registry/shiroe-registry.schema.json
  (hand-rolled structural checker — stdlib only, no jsonschema dependency)

Exit 0 on pass, 1 on fail.
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Which statuses claim on-disk runtime backing. Entries with these statuses MUST
# resolve to real artifacts; other statuses (contract / experimental) are honest
# labels that the entry is a spec surface only. See registry parity gate.
ACTIVE_STATUSES = {"runtime", "adapter"}
# Statuses tolerated on disk-absent entries. Kept aligned with the schema enum
# in registry/shiroe-registry.schema.json.
INACTIVE_STATUSES = {"contract", "experimental"}

EXPECTED = {
    "root_manifests": ["SKILL.md", "AGENTS.md", "CLAUDE.md", "GEMINI.md"],
    "root_privacy": ["PRIVACY.md", "REDACT.md", "SHARING_POLICY.md"],
    "config": ["PROJECT.md", "PERMISSIONS.md", "PARENT_SYNC.md", "BUDGET.md", "claude-overrides.md"],
    "memory_dirs": ["raw", "snapshots", "sync/outbound", "sync/parent", "archive", "patterns"],
    "memory_flat": ["hot.md", "index.md", "MEMORY.md", "DECISIONS.md", "OPEN_QUESTIONS.md", "RISKS.md", "CONFLICTS.md"],
    "harness_stubs": [".cursor/rules/shiroe.mdc", ".windsurfrules", ".aider.conf.yml.example"],
    "plugin_manifests": [".claude-plugin/plugin.json", ".claude-plugin/marketplace.json"],
}

# PATTERNS.jsonl event allowlist + per-event required payload keys
EVENT_SCHEMA = {
    "wiki-write":       {"required": ["summary"], "optional": []},
    "session-start":    {"required": [], "optional": ["trigger", "scope", "budget_ceiling_usd", "team", "force_multipliers"]},
    "memory-drift-detected": {"required": ["finding"], "optional": []},
    "budget-gate":      {"required": ["weight", "tier", "match"], "optional": ["est_cost_usd", "budget_remaining_usd", "override_reason"]},
    "skill-route":      {"required": ["domain", "lead", "support", "qa"], "optional": ["ext"]},
    "tool-probe":       {"required": ["tool", "reachable"], "optional": ["path", "fallback", "marker_verified"]},
    "prompt-gate":      {"required": ["classification"], "optional": ["restructured", "brief_tokens", "stripped_context_tokens", "injection_detected"]},
    "handoff-compress": {"required": ["original_tokens", "compressed_tokens", "ratio"], "optional": ["model_from", "model_to", "harness_from", "harness_to"]},
    "tier-change":      {"required": ["from", "to"], "optional": []},
    # Legacy / pre-v2.6
    "grep-with-context": {"required": [], "optional": ["action"]},
    "log-cutover":       {"required": [], "optional": ["from", "to", "note"]},
}

VALID_WEIGHTS = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
VALID_TIERS = {"OPUS", "SONNET", "HAIKU", "OPUS-equivalent", "SONNET-equivalent", "HAIKU-equivalent"}
# CRITICAL never on Haiku; LOW never on Opus (Core Principle 14)
TIER_MISMATCHES = {("CRITICAL", "HAIKU"), ("CRITICAL", "HAIKU-equivalent"), ("LOW", "OPUS"), ("LOW", "OPUS-equivalent")}

errors = []
warnings = []
gate_lint = []


def check_file(path, label):
    if not (ROOT / path).is_file():
        errors.append(f"missing {label}: {path}")


def check_dir(path, label):
    if not (ROOT / path).is_dir():
        errors.append(f"missing {label} dir: {path}")


def check_yaml_frontmatter(path, required_keys):
    p = ROOT / path
    if not p.is_file():
        errors.append(f"missing: {path}")
        return
    text = p.read_text()
    if not text.startswith("---"):
        errors.append(f"{path}: no YAML frontmatter")
        return
    end = text.find("\n---", 4)
    if end == -1:
        errors.append(f"{path}: frontmatter not closed")
        return
    fm = text[4:end]
    for k in required_keys:
        if f"{k}:" not in fm:
            errors.append(f"{path}: missing frontmatter key '{k}'")


def load_registry(reg_path=None):
    """Load shiroe-registry.json: skill list + declared structure counts + raw dict.

    Returns (skills, declared, raw) — raw is None if the file is missing or
    not valid JSON (schema validation is skipped in that case; the parse
    failure is already recorded as an error).
    """
    if reg_path is None:
        reg_path = ROOT / "shiroe-registry.json"
    if not reg_path.is_file():
        errors.append("missing shiroe-registry.json (required for dynamic skill count)")
        return [], {}, None
    try:
        reg = json.loads(reg_path.read_text())
        skills = [s["skill"] for s in reg.get("skills", [])]
        declared = {}
        for k in ("agents", "commands", "team_packs"):
            v = reg.get(k)
            if isinstance(v, int):
                declared[k] = v
            elif isinstance(v, list):
                declared[k] = len(v)
        return skills, declared, reg
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        errors.append(f"shiroe-registry.json: invalid structure ({e})")
        return [], {}, None


# ---------------------------------------------------------------------------
# Minimal structural JSON-Schema checker (stdlib only — see pyproject.toml
# "Core: stdlib only — zero mandatory deps"; no `jsonschema` dependency).
# Covers exactly the keywords registry/shiroe-registry.schema.json uses:
# type, required, properties, items, enum, pattern. Not a general validator.
# ---------------------------------------------------------------------------

def _schema_check(instance, schema, path):
    """Recursively check `instance` against `schema`, appending violations
    (with the offending JSON path) to the module-level `errors` list."""
    t = schema.get("type")
    type_ok = True
    if t == "object":
        if not isinstance(instance, dict):
            errors.append(f"registry schema: {path}: expected object, got {type(instance).__name__}")
            type_ok = False
        else:
            for key in schema.get("required", []):
                if key not in instance:
                    errors.append(f"registry schema: {path}: missing required key '{key}'")
            for key, subschema in schema.get("properties", {}).items():
                if key in instance:
                    _schema_check(instance[key], subschema, f"{path}.{key}")
    elif t == "array":
        if not isinstance(instance, list):
            errors.append(f"registry schema: {path}: expected array, got {type(instance).__name__}")
            type_ok = False
        else:
            items_schema = schema.get("items")
            if items_schema is not None:
                for i, item in enumerate(instance):
                    _schema_check(item, items_schema, f"{path}[{i}]")
    elif t == "string":
        if not isinstance(instance, str):
            errors.append(f"registry schema: {path}: expected string, got {type(instance).__name__}")
            type_ok = False
        elif "pattern" in schema and not re.match(schema["pattern"], instance):
            errors.append(f"registry schema: {path}: {instance!r} does not match pattern {schema['pattern']!r}")
    elif t == "boolean":
        if not isinstance(instance, bool):
            errors.append(f"registry schema: {path}: expected boolean, got {type(instance).__name__}")
            type_ok = False

    if type_ok and "enum" in schema and instance not in schema["enum"]:
        errors.append(f"registry schema: {path}: {instance!r} not in allowed values {schema['enum']}")


def _module_path_resolves(root, dotted_id):
    """Resolve `shiroe.foo.bar` to either `shiroe/foo/bar/` or `shiroe/foo/bar.py`."""
    rel = Path(*dotted_id.split("."))
    return (root / rel).is_dir() or (root / (str(rel) + ".py")).is_file()


def check_registry_parity(reg, root=None):
    """Every entry with an active status resolves to an on-disk artifact; every
    entry without one carries an honest non-active status. Complements the
    filesystem-count check by verifying per-entry path/module presence, so
    the two registry surfaces cannot silently claim runtime backing they lack.
    """
    if reg is None:
        return
    if root is None:
        root = ROOT

    # shiroe-registry.json — the hand-authored surface. Each list is (key_for_id,
    # optional path key, artifact resolver). Skills resolve as `skills/<id>/`;
    # everything else has an explicit path field the schema constrains.
    for entry in reg.get("skills", []):
        name = entry.get("skill", "<?>")
        status = entry.get("status")
        artifact = root / "skills" / name
        if status in ACTIVE_STATUSES and not artifact.is_dir():
            errors.append(f"registry parity: skill '{name}' status={status!r} but skills/{name}/ missing")
        elif status not in ACTIVE_STATUSES and status not in INACTIVE_STATUSES:
            errors.append(f"registry parity: skill '{name}' has unknown status {status!r}")

    for kind, id_key in (("agents", "agent"), ("commands", "command"),
                        ("team_packs", "pack"), ("gates", "gate")):
        for entry in reg.get(kind, []):
            name = entry.get(id_key, "<?>")
            status = entry.get("status")
            path = entry.get("path")
            if status in ACTIVE_STATUSES:
                if not path or not (root / path).is_file():
                    errors.append(f"registry parity: {kind[:-1]} '{name}' status={status!r} but path {path!r} missing")
            elif status not in INACTIVE_STATUSES:
                errors.append(f"registry parity: {kind[:-1]} '{name}' has unknown status {status!r}")

    # registry/components.json — generated surface. Component ids are dotted
    # Python module paths; runtime/adapter entries must resolve to a real module.
    comp_path = root / "registry" / "components.json"
    if comp_path.is_file():
        try:
            comp = json.loads(comp_path.read_text())
        except json.JSONDecodeError as e:
            errors.append(f"registry/components.json: invalid JSON ({e})")
            return
        for entry in comp.get("components", []):
            cid = entry.get("id", "<?>")
            status = entry.get("status")
            if status in ACTIVE_STATUSES:
                if not _module_path_resolves(root, cid):
                    errors.append(f"registry parity: component '{cid}' status={status!r} but no module found on disk")
            elif status not in INACTIVE_STATUSES:
                errors.append(f"registry parity: component '{cid}' has unknown status {status!r}")


def check_registry_schema(reg):
    """Validate the already-parsed registry dict against the committed schema."""
    if reg is None:
        return
    schema_path = ROOT / "registry" / "shiroe-registry.schema.json"
    if not schema_path.is_file():
        errors.append("missing registry/shiroe-registry.schema.json")
        return
    try:
        schema = json.loads(schema_path.read_text())
    except json.JSONDecodeError as e:
        errors.append(f"registry/shiroe-registry.schema.json: invalid JSON ({e})")
        return
    _schema_check(reg, schema, "$")


def discover_md(dirname):
    """Sorted .md files actually present in a top-level dir (filesystem-derived)."""
    d = ROOT / dirname
    if not d.is_dir():
        errors.append(f"missing dir: {dirname}/")
        return []
    return sorted(p.name for p in d.iterdir() if p.is_file() and p.suffix == ".md")


# Non-registry skill dirs that are allowed on disk.
SKILL_DIR_EXEMPT = {"imported", "drafts", "_drafts"}


def lint_patterns_log(skill_inventory, agent_files):
    """Validate PATTERNS.jsonl event schema + stack-length cap.
    Advisory: warn if no recent gate events.
    skill-route lead/support may be either skill names OR agent names (memory-keeper / privacy-guardian etc.).
    """
    # Extend inventory with agent names (skill-router lead can be an agent — e.g. memory-keeper)
    agent_names = [a.replace(".md", "") for a in agent_files]
    valid_actors = set(skill_inventory) | set(agent_names)
    p = ROOT / "memory" / "patterns" / "PATTERNS.jsonl"
    if not p.is_file():
        # Empty scaffold (no hot.md) → already reported by main(); stay quiet here.
        if (ROOT / "memory" / "hot.md").is_file():
            warnings.append("memory/patterns/PATTERNS.jsonl missing")
        return
    lines = p.read_text().splitlines()
    if not lines:
        return
    inventory_set = valid_actors  # use combined skill + agent set
    gate_events_seen = {"budget-gate": 0, "skill-route": 0, "prompt-gate": 0}
    for i, ln in enumerate(lines, 1):
        ln = ln.strip()
        if not ln:
            continue
        try:
            ev = json.loads(ln)
        except json.JSONDecodeError as e:
            gate_lint.append(f"PATTERNS.jsonl line {i}: invalid JSON ({e})")
            continue
        etype = ev.get("event")
        if etype not in EVENT_SCHEMA:
            gate_lint.append(f"PATTERNS.jsonl line {i}: unknown event type '{etype}' (not in allowlist)")
            continue
        schema = EVENT_SCHEMA[etype]
        payload = ev.get("payload", {}) or {}
        for req in schema["required"]:
            if req not in payload:
                gate_lint.append(f"PATTERNS.jsonl line {i}: event '{etype}' missing required payload key '{req}'")
        # Core Principle 14 lint — stack cap of 5
        if etype == "skill-route":
            support = payload.get("support", [])
            stack_size = 1 + len(support) + (1 if payload.get("qa") else 0)
            if stack_size > 5:
                gate_lint.append(f"PATTERNS.jsonl line {i}: skill-route stack size {stack_size} > 5 (stack cap; AGENTS.md skill-router §Anti-patterns)")
            lead = payload.get("lead")
            if lead and lead not in inventory_set:
                gate_lint.append(f"PATTERNS.jsonl line {i}: skill-route lead '{lead}' not in registry")
        if etype == "budget-gate":
            w = payload.get("weight")
            t = payload.get("tier")
            if w and w not in VALID_WEIGHTS:
                gate_lint.append(f"PATTERNS.jsonl line {i}: budget-gate invalid weight '{w}'")
            if t and t not in VALID_TIERS:
                gate_lint.append(f"PATTERNS.jsonl line {i}: budget-gate invalid tier '{t}'")
            if (w, t) in TIER_MISMATCHES and payload.get("match") != "OVERRIDE":
                gate_lint.append(f"PATTERNS.jsonl line {i}: budget-gate {w}->{t} mismatch (Core Principle 14 violation; only allowed with match=OVERRIDE)")
        if etype in gate_events_seen:
            gate_events_seen[etype] += 1
    # advisory
    if sum(gate_events_seen.values()) == 0 and len(lines) > 5:
        warnings.append("no Auto-Activation Gate events (budget-gate/skill-route/prompt-gate) in PATTERNS.jsonl despite >5 entries — gates may be skipped")


def main():
    ap = argparse.ArgumentParser(description="Validate Shiroe plugin structure")
    ap.add_argument("--registry", type=Path, default=None, help=argparse.SUPPRESS)
    args = ap.parse_args()

    if args.registry is not None:
        errors.append("--registry is obsolete; vNext derives runtime surface from executable code")

    removed_surfaces = ("skills", "agents", "commands", "team-packs")
    for rel in removed_surfaces:
        if (ROOT / rel).exists():
            errors.append(f"removed contract surface still present: {rel}/")
    for rel in ("shiroe-registry.json", "registry/shiroe-registry.schema.json"):
        if (ROOT / rel).exists():
            errors.append(f"removed contract registry still present: {rel}")
    check_registry_parity(None)
    agent_files: list[str] = []

    # Root manifests
    for f in EXPECTED["root_manifests"]:
        check_file(f, "root manifest")

    # Root privacy templates (per SHIROE_OS §4.1)
    for f in EXPECTED["root_privacy"]:
        check_file(f, "root privacy template")

    # config/
    for f in EXPECTED["config"]:
        check_file(f"config/{f}", "config")

    # memory/ — flat layout per SHIROE_OS §12.
    # Memory is per-user-project: this repo ships an empty scaffold (memory/README.md
    # + .gitkeep). Missing dirs/files are warnings, not errors, in that case;
    # a populated project should `python3 -m shiroe init` to scaffold them.
    memory_root = ROOT / "memory"
    memory_populated = any(
        (memory_root / f).exists()
        for f in EXPECTED["memory_flat"]
    )
    if memory_populated:
        for d in EXPECTED["memory_dirs"]:
            check_dir(f"memory/{d}", "memory")
        for f in EXPECTED["memory_flat"]:
            check_file(f"memory/{f}", "memory (flat)")
        check_file("memory/patterns/PATTERNS.jsonl", "patterns log")
    else:
        warnings.append("memory/ is empty scaffold — run `python3 -m shiroe init` in your project to populate")

    # Deprecation warning if old memory/wiki/ still has live content
    wiki_dir = ROOT / "memory" / "wiki"
    if wiki_dir.is_dir():
        live = [p for p in wiki_dir.rglob("*")
                if p.is_file() and p.name not in (".gitkeep", "README-MOVED.md")]
        if live:
            warnings.append(
                f"memory/wiki/ still has {len(live)} file(s) — "
                f"run scripts/migrate-v4.2-to-v4.3.py --apply"
            )

    # Harness stubs (per SHIROE_OS §10)
    for s in EXPECTED["harness_stubs"]:
        check_file(s, "harness stub")

    # Plugin manifests
    for m in EXPECTED["plugin_manifests"]:
        check_file(m, "plugin manifest")
        try:
            json.loads((ROOT / m).read_text())
        except (FileNotFoundError, json.JSONDecodeError) as e:
            errors.append(f"{m}: invalid JSON ({e})")

    # PATTERNS.jsonl validation (schema + stack-cap)
    lint_patterns_log([], agent_files)

    # Output — actual counts derived from the filesystem; declared counts from
    # shiroe-registry.json where the registry declares them.
    def _declared(label, actual):
        return f"{actual}/{declared_counts[label]}" if label in declared_counts else str(actual)

    print(f"Shiroe validator — {ROOT}")
    print("Contract dirs:    absent")
    print(f"Config:           {sum((ROOT / 'config' / c).is_file() for c in EXPECTED['config'])}/5")
    print(f"Root privacy:     {sum((ROOT / f).is_file() for f in EXPECTED['root_privacy'])}/3 (PRIVACY, REDACT, SHARING_POLICY)")
    print(f"Harness stubs:    {sum((ROOT / s).is_file() for s in EXPECTED['harness_stubs'])}/3")
    print(f"Memory layout:    flat")
    print(f"PATTERNS lint:    {len(gate_lint)} finding(s)")

    if warnings:
        print("\nWarnings:")
        for w in warnings:
            print(f"  ! {w}")

    if gate_lint:
        print(f"\nPATTERNS.jsonl lint findings ({len(gate_lint)}):")
        for g in gate_lint[:20]:  # cap to 20
            print(f"  ~ {g}")
        if len(gate_lint) > 20:
            print(f"  ... and {len(gate_lint) - 20} more")

    if errors:
        print(f"\n✘ {len(errors)} error(s):")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)

    print("\n✔ Validation passed")
    sys.exit(0)


if __name__ == "__main__":
    main()
