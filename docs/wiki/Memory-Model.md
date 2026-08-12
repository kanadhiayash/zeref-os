# Memory Model

> Hand a six-month-old project to a new collaborator. Where do they read first? What do they read second? When do they stop? Shiroe answers those three questions with files on disk.

## The store invariant

"What is the source of truth?" has one answer. Everything else is derived.

| Layer | Role |
|---|---|
| SQLite | Canonical current state. |
| JSONL | Canonical append-only history. Appended, never rewritten. |
| Markdown | Generated human-readable view. Carries a do-not-edit header. |
| TOON | Optional generated model-input view. |

The Markdown you read in `memory/` is a view, not the record. Editing it by hand edits the projection rather than the source; regeneration overwrites your change. Write through the CLI or a session so the write passes verification.

Recorded in [`docs/adr/ADR-0001-canonical-store.md`](https://github.com/kanadhiayash/shiroe/blob/main/docs/adr/ADR-0001-canonical-store.md).

## Layout

```
memory/
├── hot.md                   read FIRST — current context, kept short
├── index.md                 domain index — read when hot is insufficient
├── MEMORY.md                session notes
├── DECISIONS.md             confirmed decisions with provenance + evidence grade
├── OPEN_QUESTIONS.md        unresolved questions with owners
├── RISKS.md                 identified risks with severity
├── CONFLICTS.md             contradiction queue awaiting arbitration
├── glossary.md              project-specific terms
├── state/                   canonical structured state
├── views/                   generated views
├── audit/                   append-only traces
├── patterns/                append-only event log
├── snapshots/               point-in-time state with manifests
├── archive/                 superseded content — archived, not deleted
├── raw/                     untouched source material
└── sync/
    ├── outbound/            staged updates awaiting approval
    └── parent/              received updates
```

## Boundary-first reading

This is the property that keeps context bounded as a project grows.

1. **First** — read `memory/hot.md`. Current context, deliberately short.
2. **Second** — read `memory/index.md` only if hot is insufficient. Locate the relevant domain row.
3. **Third** — read only the named section of the named page.
4. **Never** — load a full page just to scan it.

The cost of a read tracks the question being asked, not the age or size of the project. A two-year-old project and a two-week-old one cost the same to resume.

The discipline matters more than it looks. Once an agent is allowed to "just load everything," context spend grows with project age, relevance drops as unrelated material crowds the window, and the failure mode is silent — the agent still answers, just worse.

## The guarded write path

Every write flows through one canonical service path. No component writes to
`memory/` directly.

```
claim
  ↓ privacy verification
  ↓ evidence verification
  ↓ fact verification
  ↓ contradiction verification
  ↓ canonical write
SQLite + event log
```

Concurrency is handled by an advisory lock in `shiroe/lock.py`. A second concurrent writer aborts with a clear error rather than interleaving, and writes are atomic, so an interrupted write does not leave a half-written file.

## Contradiction handling

When a new claim conflicts with a stored one:

1. Halt the write.
2. Fingerprint the claim against stored decisions, open questions, and risks.
3. Append both sides, with provenance, to `memory/CONFLICTS.md`.
4. Surface to the user — immediately, or at session end, by their choice.
5. Wait. The user arbitrates.
6. On resolution, record the outcome with both sides' provenance preserved.

Nothing is auto-resolved. Four shortcuts are refused:

| Refused | Why |
|---|---|
| Recency-wins | Newer is not truer. |
| Grade-wins | Better-sourced is not automatically right for this project. |
| Silent-drop | Discards information without a decision being made. |
| Indefinite-snooze | Defers forever, which is a decision in disguise. |

The stored conflict keeps both sides intact, so arbitrating later loses nothing.

## Evidence grading

Two scores, stored separately, never collapsed.

**Evidence quality** grades the source: provenance, directness, recency, authority, corroboration, reproducibility, and known contradictions.

**Review robustness** grades the deliberation: method diversity, independent agreement, recorded dissent, counterarguments considered.

Agreement among reviewers never upgrades weak source evidence to a strong grade. Confidence in a process is not evidence about the world, and merging the two would let the second quietly launder the first.

## The append-only event log

`memory/events/` holds the canonical append-only JSONL event log. Each event is
a single JSON line carrying a timestamp, the actor, the event type, a target, a
payload, a previous hash, and an integrity hash.

The log is never edited in place. Entries are appended; replay reconstructs
state.

Event types are allowlisted by `shiroe.storage.events`. Unknown event types are
rejected unless the caller explicitly declares a versioned schema.

## Snapshots and archival

Session close copies the memory state to a timestamped snapshot directory with a manifest. Superseded content moves to `archive/` rather than being deleted, so a bad consolidation is recoverable and provenance chains stay intact.

## Validation

```bash
python3 -m shiroe state verify --json
python3 -m shiroe doctor --json
```

Checks that canonical state, event replay integrity, root privacy files, and the
runtime surface are valid. Exits non-zero on blocking findings.

## Related

- [[Architecture]] — Work Graph, approval, capabilities, routing
- [[Privacy-Model]] — modes, classes, export policy
- [[Glossary]] — canonical terms
