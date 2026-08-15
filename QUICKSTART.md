<!-- privacy-audit: allow-file "Quickstart with example install and CLI commands. No real user data." -->

# Shiroe Quickstart

## 1. Install

```bash
python3 -m pip install -e .
python3 -m shiroe --help
```

## 2. Initialize A Project

```bash
python3 -m shiroe init /path/to/project --name "My Project" --privacy abstract --network-scope device-only
cd /path/to/project
python3 -m shiroe status --json
python3 -m shiroe doctor --json
```

`init` creates current project config, privacy files, `.shiroe/policy/`,
`memory/state/shiroe.sqlite`, and the event-log directory. It does not enable
connectors.

## 3. Work Graph Lifecycle

```bash
python3 -m shiroe plan --from-json graph.json --json
python3 -m shiroe run <graph-id>
python3 -m shiroe approve list --json
python3 -m shiroe approve decide <approval-id> --status approved --reason "approved"
python3 -m shiroe run <graph-id>
```

## 4. Memory And Verification

```bash
python3 -m shiroe memory write --from proposal.json
python3 -m shiroe memory recall "query"
python3 -m shiroe verify --graph <graph-id> --json
python3 -m shiroe state verify --json
python3 -m shiroe handoff --graph <graph-id> claude
```

Installed `--help` output is the source of truth for command syntax.
