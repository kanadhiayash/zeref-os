<!-- privacy-audit: allow-file "Public project overview and install commands. No user memory." -->

# Shiroe

Shiroe is a local-first governance and continuity plane for persistent AI Work
Graphs. It owns canonical state, policy, approvals, capability control,
execution supervision, verification, memory, and cross-harness continuation.

Current release: `3.0.0-alpha.1`. The vNext overhaul is in progress, so only
interfaces shown by the installed CLI are operational.

## Operational Boundary

Every declared product component must be executable. Shiroe does not ship
declaration-only product components or `contract` and `experimental` product
statuses. The authoritative boundary and phased removals are documented in
[`docs/architecture/CORE_SCOPE.md`](docs/architecture/CORE_SCOPE.md) and
[`docs/architecture/REMOVALS.md`](docs/architecture/REMOVALS.md).

The approved final runtime is organized around one Work Graph, one canonical
SQLite state store with append-only event history, one canonical memory write
path, and one conditional non-authorizing Approval Advisor.

## Install

Shiroe requires Python 3.11 or newer and has no mandatory runtime dependency.

```bash
git clone https://github.com/kanadhiayash/shiroe.git
cd shiroe
python3 -m shiroe init
python3 -m shiroe doctor --format json
```

## Current CLI

Run the CLI help for the executable surface at the checked-out revision:

```bash
python3 -m shiroe --help
```

The final vNext public command target is `init`, `status`, `plan`, `run`,
`approve`, `memory`, `verify`, `handoff`, and `doctor`. The operator target is
`policy`, `capability`, `state`, and `version`. A target command is not an
operational claim until its implementation phase has landed and its tests pass.

## State And Privacy

Canonical state is local SQLite plus hash-chained append-only events. Markdown
and indexes are generated projections. All writes and external transmission are
governed by `PRIVACY.md`, `REDACT.md`, and `SHARING_POLICY.md`; connectors are
disabled by default.

## Verification

```bash
python3 -m compileall -q shiroe
python3 -m pytest -q
python3 -m shiroe doctor --format json
```

The overhaul does not use a benchmark score as an acceptance gate. Public
claims require executed evidence.

## License

MIT. See [`LICENSE`](LICENSE).
