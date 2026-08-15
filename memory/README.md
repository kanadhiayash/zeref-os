# memory/

`memory/` contains local runtime state for a Shiroe project. In this repository
it is a development fixture; user projects create their own tree with:

```bash
python3 -m shiroe init /path/to/project --name "My Project"
```

Canonical current state is `memory/state/shiroe.sqlite`. Canonical history is
the hash-chained event log under `memory/events/<yyyy>/<mm>/events.jsonl`.
Generated Markdown views, if present, are rebuildable projections and are not
the authority.

Write through `python3 -m shiroe memory ...` so privacy, evidence, policy, and
event-log checks run.
