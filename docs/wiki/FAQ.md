# FAQ

## What is Shiroe?

Shiroe is a local-first control plane for AI-assisted project work. It keeps
canonical state on disk, enforces approval and policy boundaries, runs bounded
Work Graphs, and compiles handoffs for humans or other harnesses.

## Does Shiroe call model APIs?

No. Shiroe records reasoning classes such as `fast`, `balanced`, `deep`, and
`frontier`. Provider descriptors map those classes to concrete model IDs at the
edge, and the harness performs inference.

## Where is state stored?

Current state lives in `memory/state/shiroe.sqlite`. Append-only replay history
lives under `memory/events/`. Markdown files under `memory/views/` are generated
views.

## Can approval be delegated to an advisor?

No. The Approval Advisor can recommend a decision when an executable reasoning
capability is available. It cannot authorize, mutate approval records, or bypass
policy.

## How does recall work?

Recall goes through `MemoryService` and one deterministic token-overlap search
path. There is no alternate ranking backend in the active runtime.

## Which commands are active?

Public commands: `init`, `status`, `plan`, `run`, `approve`, `memory`,
`verify`, `handoff`, and `doctor`.

Operator commands: `policy`, `capability`, `state`, and `version`.

Run `python3 -m shiroe --help` for the exact installed surface.

## How do I verify a checkout?

```bash
python3 -m compileall -q shiroe
python3 -m pytest -q
python3 -m shiroe doctor --json
python3 -m shiroe version
```

## Where do removed features live?

Removed surfaces are listed in `docs/architecture/REMOVALS.md`. Git history is
the archive for implementation details.
