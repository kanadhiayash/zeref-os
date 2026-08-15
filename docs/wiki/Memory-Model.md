# Memory Model

## Authority

Canonical current state is `memory/state/shiroe.sqlite`. Canonical history is
the hash-chained JSONL event log under `memory/events/<yyyy>/<mm>/events.jsonl`.
Generated Markdown views can help humans read state, but they are rebuildable
and not authoritative.

## Write Path

```bash
python3 -m shiroe memory write --from proposal.json
python3 -m shiroe memory recall "query"
python3 -m shiroe memory list --json
```

Writes pass through privacy, evidence, policy, supported contradiction, and
event-log validation before canonical state changes.

## Verification

```bash
python3 -m shiroe state verify --json
python3 -m shiroe doctor --json
```

Replay from the event log must be able to rebuild state. Unknown event types
are rejected unless they carry an explicit schema.

## Related

- `docs/adr/ADR-0001-canonical-store.md`
- `docs/MEMORY_WRITES.md`
- `docs/DOCTOR.md`
