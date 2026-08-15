# Getting Started

```bash
python3 -m shiroe --version
python3 -m shiroe init /path/to/project --name "My Project" --privacy abstract --network-scope device-only
cd /path/to/project
python3 -m shiroe status --json
```

Write canonical memory through the CLI:

```bash
python3 -m shiroe memory write --from proposal.json
python3 -m shiroe memory recall "public-safe copy"
python3 -m shiroe memory list --json
```

Run a Work Graph through the approval lifecycle:

```bash
python3 -m shiroe plan --from-json graph.json --json
python3 -m shiroe run <graph-id>
python3 -m shiroe approve list --json
python3 -m shiroe approve decide <approval-id> --status approved --reason "approved"
python3 -m shiroe run <graph-id>
```

Verify state:

```bash
python3 -m shiroe doctor --json
python3 -m shiroe verify --graph <graph-id> --json
python3 -m shiroe state verify --json
```

Run the aggregate local gate before a release decision:

```bash
python3 scripts/release_ready.py
```
