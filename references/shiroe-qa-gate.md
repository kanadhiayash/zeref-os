# Shiroe QA Gate

Run before public claims, handoffs, and release decisions.

## Checks

1. Facts, assumptions, unknowns, and risks are separated.
2. Commands, file paths, versions, and errors are preserved exactly.
3. Privacy and sharing policy are checked before persistence or output.
4. Canonical state is inspected through the CLI, not generated Markdown.
5. Irreversible actions have explicit user approval.
6. Work Graph, policy, capability, and approval state are current.
7. Evidence grade and source references are attached where claims are stored.
8. Supported contradiction checks surface conflicts without silent resolution.

## Runtime Gate

```bash
python3 -m shiroe doctor --json
python3 -m shiroe state verify --json
python3 -m shiroe verify --graph <graph-id> --json
```

If a check fails, stop, report the reason, and correct the source condition.
