<!-- privacy-audit: allow-file "Quickstart with example install / CLI commands. No real user data." -->

# Shiroe — Quickstart

Five steps from zero to a first Work Graph run. Match
[INSTALL.md](INSTALL.md) for the canonical install channels.

---

## 1. Install

```bash
git clone https://github.com/kanadhiayash/shiroe
cd shiroe
pip install -e .
shiroe --help
```

Public surface (installed help is the source of truth): `init`, `status`,
`plan`, `run`, `approve`, `memory`, `verify`, `handoff`, `doctor`,
`policy`, `capability`, `state`, `version`.

---

## 2. Initialise a Project

```bash
cd ~/my-project
shiroe init . --name "My Project" --privacy abstract --tier auto
```

Scaffolds `config/PROJECT.md`, `PRIVACY.md`, `REDACT.md`,
`SHARING_POLICY.md`, `config/BUDGET.md`, `memory/` (flat layout), and the
canonical state directories under `memory/state/` and `memory/events/`.
No connectors are enabled.

Inspect:

```bash
shiroe status --json
shiroe doctor --json
```

---

## 3. Persist a Work Graph

Draft a Work Graph as JSON (see `docs/wiki/WorkGraph.md` for the schema)
and register it:

```bash
shiroe plan --from-json path/to/graph.json --json
```

The graph is stored in canonical SQLite; markdown/index views are
generated projections.

---

## 4. Run and Approve

```bash
shiroe run <graph-id>            # execute; pauses on require_approval
shiroe approve list --json       # see pending approvals
shiroe approve decide <id> --status approved --reason "…"
shiroe run <graph-id>            # resume — same command
```

---

## 5. Verify

```bash
shiroe verify --graph <graph-id> --json     # graph invariants
shiroe verify --memory --json               # memory chain + digest
shiroe state verify --json                  # event-log hash chain
```

---

## Cheat Sheet

| Command | Purpose |
|---|---|
| `shiroe init` | Scaffold a new project |
| `shiroe status` | Project or Work Graph status |
| `shiroe plan --from-json` | Persist a Work Graph |
| `shiroe run` | Execute or resume a Work Graph |
| `shiroe approve` | List, advise, decide approvals |
| `shiroe memory write --from` | Canonical memory write |
| `shiroe verify` | Graph / memory verification |
| `shiroe handoff` | Compile a canonical handoff |
| `shiroe doctor` | Runtime health checks |
| `shiroe state verify` | Event-log chain check |
| `shiroe policy` | Inspect policy stack |
| `shiroe capability` | Inspect executable capabilities |

---

## Next

- `AGENTS.md` — canonical harness spec
- `README.md` — project overview and release
- `docs/architecture/CORE_SCOPE.md` — operational boundary
- `docs/wiki/` — full documentation
