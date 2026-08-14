<!-- privacy-audit: allow-file "Public project overview and install commands. No user memory." -->

<div align="center">

<img src="assets/shiroe-banner-motion.svg" alt="Shiroe" width="820">

# Shiroe

**A local-first governance and continuity plane for persistent AI Work Graphs.**

Canonical state · policy · approvals · capability control · execution supervision · verification · memory · cross-harness handoff — all on your machine, all governed, nothing phoned home.

Current release: `v3.0.0-alpha.1`.

[![release](https://img.shields.io/badge/release-alpha-blue?style=flat-square)](https://github.com/kanadhiayash/shiroe/releases)
[![python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-3776AB?style=flat-square)](https://github.com/kanadhiayash/shiroe)
[![dependencies](https://img.shields.io/badge/runtime%20deps-zero-success?style=flat-square)](https://github.com/kanadhiayash/shiroe)
[![tests](https://img.shields.io/badge/tests-949%20passing-brightgreen?style=flat-square)](https://github.com/kanadhiayash/shiroe/actions)
[![license](https://img.shields.io/badge/license-MIT-black?style=flat-square)](LICENSE)

</div>

---

## Why Shiroe

Every AI harness — Claude Code, Codex, Gemini, Cursor — starts each session
from zero. It cannot prove what it did last time, cannot pause on a risky
action and safely resume, and cannot hand work to a different tool without
losing the thread.

Shiroe is the layer that fixes that. It is **not a harness and not an agent**.
It sits underneath whichever harness you use and owns the durable, auditable
state that AI-assisted work needs to be cumulative instead of stateless:

- **One Work Graph** — the unit of work, with a dependency-ordered set of nodes and a compare-and-swap state machine.
- **One canonical store** — local SQLite for current state, a hash-chained append-only event log for history. Markdown is a *generated projection*, never the source of truth.
- **One approval path** — policy-required actions pause execution and wait for a human decision; the Approval Advisor can advise but can never write a decision itself.
- **One memory write path** — every write is scrubbed, graded, and logged; three privacy modes, connectors off by default.
- **One handoff contract** — the same graph, approvals, decisions, and next-step resume identically across every supported harness.

<div align="center">
<img src="assets/shiroe-character-snapshot-motion.svg" alt="Shiroe at work" width="620">
</div>

---

## Install

Shiroe requires **Python 3.11+** and has **no mandatory runtime dependency**.

```bash
git clone https://github.com/kanadhiayash/shiroe.git
cd shiroe
python3 -m pip install -e .
python3 -m shiroe --help
```

Scaffold a project:

```bash
python3 -m shiroe init /path/to/project --name my-project --privacy abstract --tier auto
cd /path/to/project
python3 -m shiroe status --json
```

`init` creates local configuration, the privacy files (`PRIVACY.md`,
`REDACT.md`, `SHARING_POLICY.md`), the canonical state directories, and the
append-only event log. It does **not** enable connectors and installs nothing
on your behalf.

Full install channels: [`INSTALL.md`](INSTALL.md) · Five-minute tour:
[`QUICKSTART.md`](QUICKSTART.md).

---

## The lifecycle

```bash
shiroe plan --from-json graph.json --json    # register a Work Graph (canonical SQLite)
shiroe run <graph-id>                         # execute; pauses on require_approval
shiroe approve list --json                    # inspect pending approvals
shiroe approve decide <id> --status approved --reason "…"
shiroe run <graph-id>                         # resume — same command, no lost state
shiroe verify --graph <graph-id> --json       # graph invariants
shiroe state verify --json                     # event-log hash chain
shiroe handoff --graph <graph-id> claude       # compile a cross-harness handoff
```

A rejected approval **fails** the node. A "revise" **blocks** it. An approved
one lets `run` resume exactly where it paused — the pause/resume roundtrip is
backed by a single durable approval request, never re-minted.

---

## CLI reference

The installed `--help` is always the source of truth. Current surface:

| Command | Purpose |
|---|---|
| `init` | Scaffold a new project |
| `status` | Project or Work Graph status |
| `plan` | Persist a Work Graph from JSON |
| `run` | Execute or resume a Work Graph |
| `approve` | List, advise, or decide approvals |
| `memory` | Canonical memory operations (`write`/`recall`/`list`/…) |
| `verify` | Verify Work Graph or memory state |
| `handoff` | Compile a canonical cross-harness handoff |
| `doctor` | Run installed runtime health checks |
| `policy` | Inspect the policy stack |
| `capability` | Inspect executable capabilities |
| `state` | Inspect canonical state / verify the event chain |
| `version` | Print version |

---

## State and privacy

Canonical state is local SQLite (`memory/state/shiroe.sqlite`) plus a
hash-chained append-only event log
(`memory/events/<yyyy>/<mm>/events.jsonl`). Markdown and indexes are
generated projections rebuilt from those two stores — they are never
authoritative (see
[`docs/adr/ADR-0001-canonical-store.md`](docs/adr/ADR-0001-canonical-store.md)).

All writes and external transmission are governed by `PRIVACY.md`,
`REDACT.md`, and `SHARING_POLICY.md`. Default privacy mode is `abstract`; all
connectors are disabled by default.

---

## Operational boundary

Every declared product component is executable. Shiroe ships **no**
declaration-only components and **no** `contract` or `experimental` product
status. The authoritative boundary lives in
[`docs/architecture/CORE_SCOPE.md`](docs/architecture/CORE_SCOPE.md); retired
surfaces are recorded in
[`docs/architecture/REMOVALS.md`](docs/architecture/REMOVALS.md).

---

## Verify a checkout

```bash
python3 -m compileall -q shiroe
python3 -m pytest -q                          # 949 passing
python3 -m shiroe doctor --json               # runtime health
python3 -m shiroe state verify --json         # event-log chain
python3 scripts/release_ready.py              # aggregate release-readiness gate
```

Acceptance is **executable product evidence, not comparative scoring**. Public
claims require executed evidence — see the benchmark-entry audit at
[`docs/evidence/benchmark-entry-audit.md`](docs/evidence/benchmark-entry-audit.md)
(current status: **CLOSED** pending live cross-harness and provider-metadata
evidence).

---

## FAQ

**Is Shiroe an AI agent?** No. It is the state and governance layer *under*
your agent. It never calls a model on its own.

**Does it phone home?** No. Local-first by construction; connectors are off by
default and none are installed for you.

**What happens to my existing SQLite state on upgrade?** Schema changes are
additive; the v1 layout is read, never renamed or deleted. See
[`MIGRATION.md`](MIGRATION.md).

**Where is the source of truth?** SQLite (current state) + JSONL event log
(history). Every Markdown file is a rebuildable projection.

**Can the approval advisor approve things?** Never. It advises; only a human
actor can write an approval decision.

---

## Contributing

Read [`CONTRIBUTING.md`](CONTRIBUTING.md) and [`SECURITY.md`](SECURITY.md)
before opening a PR. Every change runs the full local gate
(`python3 scripts/release_ready.py`) and the CI matrix on Python 3.11 / 3.12 /
3.13.

---

## License

MIT. See [`LICENSE`](LICENSE).

<div align="center">
<sub>Built to make AI work cumulative instead of stateless — on every harness, on your machine.</sub>
</div>
