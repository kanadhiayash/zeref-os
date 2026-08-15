<!-- privacy-audit: allow-file "Public project overview and install commands. No user memory." -->

# Shiroe

Shiroe is a local-first governance and continuity plane for persistent AI Work
Graphs. It owns canonical state, policy and approval gates, executable
capability invocation, verification, memory, and bounded handoff on the
operator's machine.

Shiroe is not a harness, hosted backend, bundled connector collection, or model
provider.

Current release: `v3.0.0-alpha.1`.

## Install

```bash
git clone https://github.com/kanadhiayash/shiroe.git
cd shiroe
python3 -m pip install -e .
python3 -m shiroe --help
```

Initialize a project:

```bash
python3 -m shiroe init /path/to/project --name my-project --privacy abstract --network-scope device-only
cd /path/to/project
python3 -m shiroe status --json
python3 -m shiroe doctor --json
```

## CLI Surface

Installed `--help` output is the source of truth.

| Command | Purpose |
|---|---|
| `init` | Scaffold a Shiroe project |
| `status` | Show project or Work Graph status |
| `plan` | Persist a Work Graph |
| `run` | Run or resume a Work Graph |
| `approve` | List, advise, or decide approvals |
| `memory` | Canonical memory operations |
| `verify` | Verify Work Graph or memory state |
| `handoff` | Compile a bounded handoff |
| `doctor` | Run semantic runtime health checks |
| `policy` | Inspect policy |
| `capability` | Inspect executable capabilities |
| `state` | Inspect canonical state |
| `version` | Print version |

## Runtime Invariants

- Canonical current state is `memory/state/shiroe.sqlite`.
- Canonical history is the hash-chained event log under `memory/events/`.
- Markdown views are projections, not authority.
- Default policy is deny unless an explicit allow applies.
- Only explicit human action creates an authorization record.
- Connectors are disabled by default.

## Verify

```bash
python3 -m compileall -q shiroe
python3 -m pytest -q
python3 -m shiroe doctor --json
python3 -m shiroe state verify --json
python3 scripts/release_ready.py
```

Release-readiness and public claims require fresh executed evidence.

## More

- [Quickstart](QUICKSTART.md)
- [Install](INSTALL.md)
- [Core scope](docs/architecture/CORE_SCOPE.md)
- [Canonical store ADR](docs/adr/ADR-0001-canonical-store.md)
- [Doctor](docs/DOCTOR.md)

## License

MIT. See [LICENSE](LICENSE).
