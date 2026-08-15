# ADR-0004: Capability lifecycle

**Status:** Accepted; partially superseded by vNext (2026-08-12).
**Date:** 2026-07-12

## Post-vNext addendum (2026-08-12)

The core lifecycle machine below (discovered → quarantined → inspected →
approved → benchmarked → active, with digest-change → re-quarantine) is
still in force. The following details in the original ADR are wrong
against the shipped runtime and should be read with these corrections:

- The manifest schema id is `shiroe.capability/v1`, not
  `shiroe.capability/v1` (see `shiroe/capabilities/manifest.py`).
- The `shiroe` product name predates the rename to Shiroe; wherever this
  ADR reads "Shiroe", the shipped runtime is Shiroe.
- The `shiroe capability` CLI in the vNext release exposes only `list`,
  `adapters`, and `gate` subcommands. The broader verb set named in
  §Consequences (`discover|inspect|approve|benchmark|activate|...`) was
  retired with the Phase 07 CLI reshape; the underlying state machine
  still runs but is driven by library APIs and the execution supervisor,
  not by a discover/approve CLI surface.
- retired collaboration bundles and the mission compiler mentioned in §Consequences were
  retired in vNext (see [`docs/architecture/REMOVALS.md`](../architecture/REMOVALS.md));
  capability selection is done by the Work Graph store and the
  execution supervisor directly.

## Context

Shiroe discovers and coordinates external units of specialist execution — skills, agents, plugins, MCP servers, CLIs, repository tools, scripts, workflows, evaluators, and API services — collectively called **capabilities** (architecture plan §8.1). Prior behavior allowed discovered capabilities (e.g. anything found under a harness's skill directory) to be treated as usable without a separate trust or inspection step, which conflicts with the plan's rule (§1.7) that discovery and execution must be separate lifecycle states, and that global capabilities are never automatically trusted.

## Decision

Every external capability enters through one lifecycle, and no state may be skipped:

```
discovered → quarantined → inspected → approved → benchmarked → active
                                                  ↘ stale | revoked | compromised
```

- **No execution before `approved`.** A capability sitting at `discovered`, `quarantined`, or `inspected` may be listed and described, but must not be invoked.
- **A digest change re-quarantines.** If a capability's source digest changes (new version, edited file, updated package), it returns to `quarantined` regardless of its prior lifecycle state, unless a signed update policy explicitly permits the new version without re-review.
- Inspection (§8.5) runs digest calculation, license detection, manifest parsing/inference, secret and private-path scanning, entrypoint inspection, permission inference, prompt-injection detection, out-of-bounds write detection, and a sandbox smoke test before a trust report is produced.
- The manifest schema (`shiroe.capability/v1`) declares source, entrypoint/adapter, provided capabilities, required permissions (filesystem/network/secrets/subprocess/external-write), harness/OS compatibility, and current trust/lifecycle state.
- Discovery roots are adapter-discovered and user-configured (`~/.claude/skills`, `~/.codex/skills`, `~/.gemini/extensions`, etc.) — never a hardcoded personal path in public code — with privacy-safe display aliases, symlink policy, traversal-depth limits, and file-count/size limits.

## Consequences

- The capability commands (`shiroe capability discover|list|inspect|approve|benchmark|activate|deactivate|revoke|refresh|diff|trust-report`) must all respect this state machine; none may offer a shortcut that executes an unapproved capability.
- The selection resolver (mission compiler) must filter candidates to `active` (or `benchmarked`+`active`) capabilities only — `discovered`/`quarantined`/`inspected` capabilities are invisible to team compilation.
- Implementation (manifest schema, discovery, quarantine, inspection, approval, digest drift, revocation) lands in PR 4 per the architecture plan §20. This ADR is the accepted decision; PR 4 is where the state machine becomes enforced code with a test gate: "discovered capabilities cannot execute before approval."
- Capability adapters (skill/agent/CLI/MCP/repository-tool) that probe reachability and health are a separate, later concern (PR 5) — this ADR governs trust state, not connectivity.
