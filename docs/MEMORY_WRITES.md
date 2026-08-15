# Memory Writes

Memory writes use a proposal file and a single canonical service path.

```bash
python3 -m shiroe memory write --from proposal.json
python3 -m shiroe memory recall "query"
python3 -m shiroe memory list --json
python3 -m shiroe memory show <memory-id> --json
python3 -m shiroe memory archive <memory-id>
```

The write path checks privacy class, evidence grade, source references,
redaction, blocked privacy classes, and supported contradiction patterns before
state changes are committed.

Accepted writes update SQLite and append a redacted event to the hash-chained
event log. Do not write generated Markdown views directly.
