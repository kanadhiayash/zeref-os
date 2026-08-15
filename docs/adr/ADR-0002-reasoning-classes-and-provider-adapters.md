# ADR-0002: Reasoning classes and provider adapters

**Status:** Accepted
**Date:** 2026-07-12

## Context

Core Shiroe schemas and code previously named concrete Anthropic models (Haiku/Sonnet/Opus tiers) directly in registry entries, mission logic, and routing decisions. This made Anthropic the de facto canonical execution model for the whole system, contrary to the architecture plan's requirement (§3.5, §3.6) that Shiroe remain provider-neutral and support multiple harnesses and model vendors without favoring one.

## Decision

- Core defines six provider-neutral **reasoning classes**: `fast`, `balanced`, `deep`, `frontier`, `local`, `private` (`shiroe/core/reasoning.py`). Task criticality (`LOW`/`MEDIUM`/`HIGH`/`CRITICAL`) maps to a class via `resolve_class()`; `LOW`→`fast`, `MEDIUM`→`balanced`, `HIGH`→`deep`, `CRITICAL`→`frontier`.
- **`frontier` is reserved for `CRITICAL` tasks only.** This is cost discipline, not a style preference: the top-cost model is bought only for critical, ambitious work, and everything routine rides the cheapest class that clears its gate.
- Concrete provider model ids are canonical **only** under `shiroe/adapters/providers/<provider>.json` (e.g. `anthropic.json` maps `frontier`→`claude-fable-5` at `effort=high`, `deep`→`claude-opus-4-8`, `balanced`→`claude-sonnet-5`, `fast`→`claude-haiku-4-5`). No other file in the repository may hardcode a provider model id in a canonical schema or core code path.
- Enforcement is in code, not prose: `shiroe.core.reasoning.validate_request(criticality, requested_class)` raises `ReasoningPolicyError` if a caller requests a class above its criticality's entitlement (an explicit request may always downgrade to something cheaper, never upgrade). `local` and `private` are placement constraints, not cost tiers, and are permitted at any criticality.
- Providers are resolved through `shiroe.adapters.providers.resolve_model(reasoning_class, provider)`, backed by a declarative `JsonProviderAdapter` — adding a new provider means adding a new JSON file, not touching core.

## Consequences

- Registry entries (`shiroe-registry.json`) now carry `reasoning_class` instead of `model`/`model_alias`. Any tooling reading the old fields must be updated; the alias layer in `removed deprecation register` covers the tier-name rename (`haiku`→`fast`, `sonnet`→`balanced`, `opus`→`deep`) but does not resurrect model-id fields in core schemas.
- Adding support for a new AI provider (OpenAI, etc.) is a matter of shipping a new `shiroe/adapters/providers/<provider>.json` file; it requires no change to `shiroe/core/reasoning.py` or any mission/capability schema.
- Any future code path that wants to name a specific model must go through a provider adapter. A code review finding a hardcoded model id outside `shiroe/adapters/providers/` is a policy violation, not a style nit.
- `AGENTS.md`'s routing section was rewritten from "Model-Tier Routing" to "Reasoning-Class Routing" to match; the weight → class → effort table and hard constraints now live there.
