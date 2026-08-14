<!-- privacy-audit: allow-file "H6.2 harness-reachability marker. No credentials, no user data." -->

# H6.2 — harness reachability (recorded, not simulated)

Per the H6.2 handoff rule: "Never fake unavailable harness runs. Mark
an unavailable harness as UNKNOWN/BLOCKED, which keeps the benchmark
gate closed if it is claimed as supported."

## Environment probed

- Recorded on the current hardening session's host during the H5+H6+H7
  wave. The host has the Shiroe repo cloned and a working Python
  toolchain; it does not have secondary harness CLIs (Codex, Gemini
  CLI, Cursor CLI, Kimi Code, Odysseus, Hermes) installed with live
  credentials.

## Reachability matrix

| Harness       | Adapter present in `shiroe/adapters/harnesses/` | CLI + credentials wired on this host | Bounded continuation run executed |
|---------------|-------------------------------------------------|--------------------------------------|-----------------------------------|
| claude_code   | yes                                             | yes (session runtime)                | yes -- implicit (this session)    |
| codex         | yes                                             | UNKNOWN                              | BLOCKED                           |
| gemini_cli    | yes                                             | UNKNOWN                              | BLOCKED                           |
| hermes        | yes                                             | UNKNOWN                              | BLOCKED                           |
| kimi_code     | yes                                             | UNKNOWN                              | BLOCKED                           |
| odysseus      | yes                                             | UNKNOWN                              | BLOCKED                           |

## Canonical continuity contract

The packet contract itself is proven by
`tests/integration/handoff/test_canonical_continuity.py` (H6.1):
every supported handoff **target** (`codex`, `claude`, `cursor`,
`github`, `human`) produces byte-identical values on the shared
continuity fields (graph identity, pending_nodes, pending_approvals,
active_decisions, open_risks, next_actions) from the same canonical
state.

## Consequence for benchmark gating

Because bounded live continuation runs across secondary harnesses were
not executed in this environment, the H6 wave-gate answer to
"Supported harness continuity = 100%" is:

  - PASS on packet contract (H6.1 integration test, 3/3 green).
  - BLOCKED on end-to-end live continuation across all harnesses
    beyond `claude_code`.

Per handoff, this keeps the benchmark gate CLOSED for any harness
claimed as fully supported end-to-end. Unblocking requires running the
prescribed bounded workflow on a host that has each harness CLI +
credentials wired, and appending the observed reachability results to
this file.

## Do not

- Do not commit credentials or personal secrets to unblock this file.
- Do not replace UNKNOWN/BLOCKED rows with speculative PASS rows.
- Do not delete this file to silently pass the wave gate; the marker's
  purpose is to keep the gate honestly CLOSED until real evidence
  lands.
