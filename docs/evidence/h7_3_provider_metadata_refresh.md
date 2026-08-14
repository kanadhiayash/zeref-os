<!-- privacy-audit: allow-file "H7.3 provider-metadata refresh marker. No credentials, no user data." -->

# H7.3 — provider / harness metadata refresh (recorded, not guessed)

Per the H7.3 handoff rule: "Refresh provider and harness model metadata
from official provider documentation at execution time. Do not guess
model IDs or lifecycle state."

## What this file records

The version-consistency check (`scripts/check-version-consistency.py`)
was expanded to cover the root `SKILL.md` frontmatter version in this
wave (H7.3). That closes the intra-repo drift half of the requirement.

The other half -- refreshing provider (model) and harness metadata
from **official provider documentation at execution time** -- was NOT
performed in this hardening session because:

  - The session ran in an offline execution environment; no network
    access to provider docs (Anthropic, OpenAI, Google, DeepMind, xAI,
    Alibaba, etc.).
  - Fabricating "current" model IDs / lifecycle rows without a live
    fetch would violate the handoff rule.

## Concrete unblocking recipe

To unblock this half of H7.3, a session with network access must:

  1. Fetch official provider model catalogues (e.g. Anthropic
     ``anthropic.com/api``, OpenAI ``platform.openai.com/docs/models``,
     Google ``ai.google.dev/gemini-api/docs/models``, xAI
     ``docs.x.ai/docs/models``).
  2. Reconcile the fetched catalog against
     `shiroe/adapters/providers/*.json` and
     `shiroe/adapters/harnesses/*.py` model-id fields.
  3. Update any stale ids / lifecycle marks and commit the diff.
  4. Append the fetch timestamp + source URL per provider below.

## Consequence for benchmark gating

Per the FINAL benchmark-entry checklist:

    Provider/harness metadata = current and verified

This axis is BLOCKED in this hardening session for the reasons above.
Intra-repo version consistency (SKILL.md, pyproject.toml, plugin.json,
Installation.md, __init__.py loader) is PASS.

## Do not

- Do not fabricate model ids to unblock this file.
- Do not delete this file to silently pass the wave gate; the marker's
  purpose is to keep the gate honestly CLOSED until a live refresh
  lands.
