<!-- privacy-audit: allow-file "Public project overview and install commands. No user memory." -->

# Shiroe

Shiroe is a local-first governance and continuity plane for persistent AI Work
Graphs. It owns canonical state, policy, approvals, capability control,
execution supervision, verification, memory, and cross-harness continuation.

Current release: `v3.0.0-alpha.1`. The vNext core overhaul is complete; every
approved runtime engine and CLI surface is operational and covered by tests.
See
[`docs/superpowers/plans/2026-08-12-shiroe-vnext-completion-report.md`](docs/superpowers/plans/2026-08-12-shiroe-vnext-completion-report.md)
for the completion audit.

## Operational Boundary

Every declared product component is executable. Shiroe ships no
declaration-only components and no `contract` or `experimental` product
status. The authoritative boundary lives in
[`docs/architecture/CORE_SCOPE.md`](docs/architecture/CORE_SCOPE.md); retired
surfaces are recorded in
[`docs/architecture/REMOVALS.md`](docs/architecture/REMOVALS.md).

The runtime is organized around one Work Graph, one canonical SQLite state
store with a hash-chained append-only event history, one canonical memory
write path, and one conditional non-authorizing Approval Advisor.

## Install

Shiroe requires Python 3.11 or newer and has no mandatory runtime dependency.

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

`init` creates local configuration, privacy files, canonical state
directories, and the append-only event log. It does not enable connectors.

## CLI

Public commands: `init`, `status`, `plan`, `run`, `approve`, `memory`,
`verify`, `handoff`, `doctor`.

Operator commands: `policy`, `capability`, `state`, `version`.

The installed help is the source of truth:

```bash
python3 -m shiroe --help
```

## State And Privacy

Canonical state is local SQLite (`memory/state/shiroe.sqlite`) plus a
hash-chained append-only event log (`memory/events/<yyyy>/<mm>/events.jsonl`).
Markdown and indexes are generated projections rebuilt from those two stores;
they are never the source of truth (see
[`docs/adr/ADR-0001-canonical-store.md`](docs/adr/ADR-0001-canonical-store.md)).

All writes and external transmission are governed by `PRIVACY.md`,
`REDACT.md`, and `SHARING_POLICY.md`. Default privacy mode is `abstract`; all
connectors are disabled by default and none are installed on the user's
behalf.

## Verification

```bash
python3 -m compileall -q shiroe
python3 -m pytest -q
python3 -m shiroe doctor --json
python3 -m shiroe state verify --json
```

Acceptance is executable product evidence, not comparative scoring. Public
claims require executed evidence.

## License

MIT. See [`LICENSE`](LICENSE).
