# Changelog — Shiroe

All notable changes to **Shiroe AI Tactician** are documented here.

Versioning: [Semantic Versioning](https://semver.org/) — `MAJOR.MINOR.PATCH`.

## Naming lineage

The project shipped as **Shiroe OS** / **Shiroe Memory Engine** through
`2.0.0-alpha.3`, and as **Shiroe AI Tactician** from `3.0.0-alpha.1`. Entries
at or before `2.0.0-alpha.3` keep the old name — they record what was true
when written, and rewriting them would falsify the record. The same applies
to `docs/adr/`, `docs/audits/release-evidence/`, and the `SHR-AUDIT-###`
work-item identifiers cited in closed issues and pull requests; new work
items use the `SHR-` prefix.

---

## [3.0.0-alpha.1] — 2026-07-31 — Shiroe: rebrand, namespace migration, retrieval fix

Renames every identity surface from Shiroe to Shiroe and fixes the retrieval
defect behind issue #196. Major version because the Python module, the CLI,
and the distribution name all change — importing `shiroe` or invoking `shiroe`
no longer works.

### Changed — breaking

- **Python module** `shiroe` → `shiroe`; **CLI** `shiroe` → `shiroe`;
  **distribution** `shiroe-os` → `shiroe`; **plugin/marketplace id**
  `shiroe-os` → `shiroe`; slash commands `/shiroe-os:<cmd>` → `/shiroe:<cmd>`.
  No compatibility shim: alpha software, clean break. Reinstall the plugin.
- **Repository** renamed to `kanadhiayash/shiroe`. GitHub redirects the old
  slug, so existing links keep resolving.
- **Environment variables** `SHIROE_*` → `SHIROE_*`. The old names still work
  and emit a `DeprecationWarning` (`shiroe/env.py`). They live in shell
  profiles and CI configs this repo cannot rewrite, and an unset variable
  does not error — it falls back to its default, so dropping
  `SHIROE_ALLOW_NETWORK` outright would have silently re-armed a network
  guard an operator had deliberately opened.
- **Canonical state DB** `memory/state/shiroe2.sqlite` → `shiroe.sqlite`,
  adopted by rename on first open. Left un-migrated it would present as
  total memory loss rather than a rename. When both exist the new one wins.
- **Workspace directory** `.shiroe/` → `.shiroe/`, still reading the old
  location when the new one has no file at that path. These are deny rules
  and write scopes; a rename that stopped loading them would not error, the
  guard would just quietly stop denying.
- **Search index** `memory/indexes/shiroe.sqlite` → `shiroe.sqlite`. Derived
  from the JSONL atoms, so the stale file is deleted, not migrated.
- `ShiroeError` → `ShiroeError`. Workflow `zrf-verify.yml` → `shr-verify.yml`
  — **re-select the required status checks in branch protection**, GitHub
  binds them per workflow file and the old binding does not follow a rename.

### Fixed

- **Retrieval ranked by substring counts, not BM25** (#196). `search_atoms`
  used the SQLite FTS5 `bm25()` path only when the index existed, and
  nothing on the ingest path ever built it — so every recall fell through to
  a raw `haystack.count(token)` sum with no IDF, no length normalisation, no
  term-frequency saturation, and substring rather than word matching. It also
  double-counted, `summary` being conventionally a prefix of `claim`. Now
  real Okapi BM25 over the already-loaded corpus. This also closes a
  coherence bug: the two paths ranked the same corpus by different functions,
  so results changed depending on whether anyone had run `shiroe memory
  index`. Not re-measured against datasets — benchmark runs are parked —
  so #196 stays open pending re-measurement.
- **Target-profile check failed open** (#153) when the profiles directory was
  absent. Profiles ship now, so a missing or unreadable directory fails
  closed. Source-authority grading (#175) is preserved.
- **Append-scaling test was timing-based and flaky** (#191). It asserted a
  wall-clock ratio and failed CI at 20.6 against a threshold of 20 on one
  runner while passing on two others. It now counts bytes scanned through
  `AtomStore._ids_from_bytes`, the invariant it was always about.
- `fact_guard`'s superlative blocklist had been narrowed by a bulk
  substitution to a single unreachable literal. Replaced with a generic
  pattern.

### Added

- **Canonical identity manifest** (`shiroe/IDENTITY.json`) with
  `check-version-consistency.py` validating 8 identity surfaces alongside the
  6 version surfaces, so no manifest can drift unnoticed.
- **A registry schema that exists.** `$schema` pointed at
  `shiroe-os.dev/registry.schema.json` — a host the project does not own,
  serving a file that never existed, validating nothing. There is now a
  committed draft 2020-12 schema, a `$schema` URL that resolves, and
  enforcement in `shiroe-validate.py` via a stdlib checker (no new
  dependency).

### Removed

- **Unevidenced self-ratings.** `MODEL_DEBATE.md` scored the product out of
  10 across ten parameters with nothing measuring any of them, two rows
  claiming "Best-in-class" and "Strongest differentiator vs. comparable
  systems" against no named comparison. Removed, with a note recording why.
  The claim gate now scans `references/` and blocks unverified superiority
  claims anywhere on a public surface — no claim of superiority ships
  without a public benchmark-verified result, and none exists yet.
- **Franchise references.** No Fairy Tail, no Dragneel, no origin story.
- **Shiroe-branded hero and icon art**, and the "not an operating system"
  disclaimer set, which the new name makes moot.

---

## [2.0.0-alpha.3] — 2026-07-27 — Hardening integration: routing, retrieval, install freshness, claim gate

Integrates the routing-classifier eval corpus, Unicode-aware hybrid
retrieval, and plugin identity/install-freshness workstreams, plus a new
external benchmark truth gate. Version bump required so the plugin content
changed in this release (`.claude-plugin/plugin.json`, `marketplace.json`)
is not served from a stale cached payload — Claude Code resolves an
installed plugin's version from `plugin.json` first.

### Added

- **Source-authority freshness grading** — target-model profiles carry a
  `source_authority` field (`official` | `third_party` | `derived`); a
  stale `official`-sourced profile still hard-fails release, a stale
  `third_party`/`derived` one now emits a non-blocking WARNING surfaced in
  both the release report and `shiroe doctor`, instead of the gate refusing
  to pass.
- **External benchmark truth gate** — a capability evidence matrix
  (namespace: conformance/integration/performance/external_benchmark/
  security_review; evidence tier: fixture-tested/external-tested) plus a
  public-claim scanner wired into `shiroe release check` and a new
  `shiroe claims` command. Blocks routing-accuracy claims resting on a
  self-authored fixture corpus, comparative rankings resting on contested
  vendor figures, Shiroe benchmark numbers published without baselines, and
  external-benchmark score claims before any dataset run is on record.
- **Upgrade-from-stale-cache regression fixture** for the install-freshness
  manifest.

### Version

- `2.0.0-alpha.3` across `shiroe/VERSION`, `pyproject.toml`,
  `shiroe-registry.json`, `.claude-plugin/plugin.json`, README badge,
  `docs/wiki/Installation.md`.

---

## [2.0.0-alpha.2] — 2026-07-14 — Hardening: consistency + claim accuracy

Consistency and claim-accuracy hardening release. No runtime behavior change.

### Changed

- **Council removal completed** — the FAANG-MANGOES Council subsystem removal (started in 2.0.0-alpha.1) is finished: remaining dependents rewired and the subsystem deleted (#129).
- **Sync-cruft guard** — repository guard against macOS/cloud-sync duplicate artifacts (#128).
- **Claim-accuracy sweep** — live public surfaces (README, top-level docs, wiki, skill docs) no longer carry unsupported quantitative claims: the "~40-60% token reduction" handoff-compression figure is replaced with "compressed handoffs; reduction varies by content", and stale validator-output examples are updated to current counts. Fixture-based external-benchmark adapters (LoCoMo, LongMemEval, BEAM, PersonaMem) remain explicitly fixture-only; full dataset runs are pending.
- **Validator** — `scripts/shiroe-validate.py` derives agent/command/team-pack counts from the tree and cross-checks skill directories against `shiroe-registry.json`, instead of reporting hardcoded expected counts that mask drift.

### Version

- `2.0.0-alpha.2` across `shiroe/VERSION`, `pyproject.toml`, `shiroe-registry.json`, `.claude-plugin/plugin.json`, README badge, `docs/RELEASE_LOG.md`, `docs/wiki/Installation.md`.

---

## [2.0.0-alpha.1] — 2026-07-12

vNext architecture reset, PR 1 of the `SHIROE_VNEXT_AGENTIC_OPERATIONS_UPGRADE_PLAN.md` sequence. Breaking architectural pivot. Not a documentation refresh: terminology, registry shape, and one runtime enforcement path all change.

### Removed

- **FAANG-MANGOES council** — `team-packs/faang-mangoes-council.md` deleted completely: pack, registry entry (`shiroe-registry.json` `team_packs` 10 → 9), and all references from `SOUL.md` and imported-skill READMEs. No alias or compatibility shim — hard removal, not a rename. See `docs/adr/ADR-0003-council-removal.md`. Its reusable protocol ideas move to an optional, experimental evaluator adapter (`Council of High Intelligence`) in a later PR (§11 of the plan) — not a hardcoded Shiroe council.

### Added

- **`shiroe/core/reasoning.py`** — six provider-neutral reasoning classes (`fast`, `balanced`, `deep`, `frontier`, `local`, `private`). Criticality → class map: `LOW`→`fast`, `MEDIUM`→`balanced`, `HIGH`→`deep`, `CRITICAL`→`frontier`. `frontier` is CRITICAL-only, enforced in code via `ReasoningPolicyError` (`validate_request`), not left to prose convention.
- **`shiroe/adapters/providers/`** — `JsonProviderAdapter` + declarative `<provider>.json` files (`anthropic.json`, `openai.json`) map reasoning classes to concrete provider model ids and effort levels. This is now the *only* place a provider model id may be canonical. `resolve_model()` in `shiroe/adapters/providers/__init__.py` is the resolution entry point.
- **`shiroe/core/deprecations.py`** — one-cycle alias layer (`resolve_alias`) for the terminology pivot: `small`→`lean`, `medium`→`balanced`, `enterprise`→`assured`, `skill-router`→`capability-resolver`, `fleet-activator`→`capability-prober`, `skill-importer`→`capability-manager`, `haiku`→`fast`, `sonnet`→`balanced`, `opus`→`deep`. Warns once per process via `DeprecationWarning`; removal target 2.1.0. See `docs/DEPRECATIONS.md`.
- **`shiroe-registry.json`** — skill entries now carry `reasoning_class` + `status` (`runtime`|`contract`) fields, replacing the old `model`/`model_alias` fields. Registry version bumped to `2.0.0-alpha.1`.
- **`docs/GLOSSARY.md`, `docs/DEPRECATIONS.md`, `docs/adr/ADR-0001` through `ADR-0005`** — final vNext glossary, deprecation map, and architecture decision records for the canonical store invariant, reasoning classes/provider adapters, council removal, capability lifecycle, and policy precedence.

### Changed

- **`AGENTS.md`** — "Model-Tier Routing" section replaced by "Reasoning-Class Routing": weight → reasoning class → effort table, cascade pattern, and hard constraints now reference `shiroe/core/reasoning.py` and `shiroe/adapters/providers/` instead of naming Anthropic tiers directly.
- **`shiroe/prompt/inject.py`, `shiroe/cli.py`** — provider ids moved out of inline logic into `shiroe/adapters/harness_targets.json` and `shiroe/adapters/providers/`.
- **Version** — `2.0.0-alpha.1` across `shiroe/VERSION`, `pyproject.toml`, `shiroe-registry.json`, `.claude-plugin/plugin.json`, README badge, `docs/RELEASE_LOG.md`, `docs/wiki/Installation.md`. This is presented as a breaking architectural release, not a minor patch, per the plan's versioning guidance (§19.4).

### Migration

Breaking: the 1.x → 2.0.0-alpha.1 migration changes the alias table and registry fields.

---

## [1.1.1] — 2026-07-11

Post-v1.1.0 CI green-up + branch cleanup. No behavioral changes to product code; the audit remediation carried forward with tighter tooling.

### Fixed

- **`agents/evidence-curator.md`, `agents/pattern-observer.md`, `commands/review-skill.md`** — moved `<!-- privacy-audit: allow-file "..." -->` marker from before the `---` YAML frontmatter to after the closing `---`. Unblocks `scripts/shiroe-validate.py` frontmatter detection + `tests/test_validator.py` (R13).
- **`.github/workflows/privacy-audit.yml`** — added editable install step; workflow now calls `python3 -m shiroe audit-privacy --strict --max-hits 30 --max-files 25`, matching the `_check_privacy_scan` ceiling in `shiroe/release/checks.py` so CI + release-check share the same enforcement (R14).
- **`.github/workflows/branch-retention.yml`** — trigger now filters to protected refs only (`main`, `dev`, `release/*`). Auto-deletion of merged feature-branch heads no longer red-flags the workflow (R15).
- **All 4 workflows** — bumped `actions/checkout` pin from v4.2.2 (Node 20) to v7.0.0 (Node 24) SHA `9c091bb2...`. Silences GitHub's Node 20 deprecation warnings (R16).

### Changed

- **`shiroe/cli.py cmd_audit_privacy`** — added `--max-hits` + `--max-files` threshold flags. When either is >0, exit code follows the ceiling instead of any-hit-fails. Preserves original behavior when both are 0 (backwards compatible) (R14).

### Removed (remote housekeeping)

- **7 empty `audit/shiroe__ws-*` branches** on remote (R17). Never received commits; created for the Phase 0.4 audit swarm and superseded by the merged v1.1.0 remediation on `main`.

### dev branch sync

`dev` was force-synced to `main` HEAD (delete + recreate via ruleset temporary-disable + restore). Divergent-hash history from the pre-v1.0.0 lineage era resolved. `dev` is now the canonical integration layer per `GITHUB_OS.md`.

---

## [Unreleased — v1.2.0 canary] — Phases 13-16 (2026-07-11)

Target-model profile system. Ships the loader + inject wrapper + release-check
subcheck + benchmark axis with 2 canary profiles (Claude Opus 4.8, GPT-5.5 Instant).
Full Tier-1 batch (10 remaining profiles) pending; v1.2.0 tag holds until full
batch lands.

### Added
- `skills/imported/system-prompts-leaks/README.md` — reference-only fleet
  boundary + refresh cadence for `github.com/asgeirtj/system_prompts_leaks`
  catalog.
- `references/target-model-profiles/` — YAML profile schema + first 2 profiles
  (`claude-opus-4-8.md`, `gpt-5-5-instant.md`) + `README.md`. Derived summaries
  only; **no source text vendored**.
- `shiroe/prompt/target_profile.py` — typed loader (frozen dataclass), schema
  validation, freshness gate, cost helpers, skip-list export. Zero deps.
- `shiroe/release/checks.py` — new `target_profiles` subcheck (schema-valid +
  `<=60d` stale). Fail-open when profiles/ absent.
- `benchmarks/token_efficiency.py` — new `target_aware_reduction` sub-axis.
  Canary aggregate: **75% theoretical reduction (Opus 4.8=83%, GPT-5.5=67%)**;
  scores 10/10 against 15% release-gate floor.

### Changed
- `shiroe/prompt/inject.py` — `inject_prompt(target, profile_id=None)`
  consults the target profile; emits `_target-profile:<id> — skip: <csv>_`
  preamble line for caveman-handoff to trust. Fail-open when no profile.
- `skills/caveman-handoff/SKILL.md` — new "Target-aware skip lists" section.
  Expected additional 15-30% reduction on Tier-1 targets.
- `_shared/model-resolver.md` — new Target-profile column; rows for
  `claude-opus-4-8` + `gpt-5-5-instant`.

### Council decisions (canary-scoped)
- Inline reconciler synth used for the "ship canary now vs wait for full
  Tier-1" call. Verdict: **canary now** — the runtime plumbing is the
  reusable primitive; remaining Tier-1 profiles are mechanical adds. Full
  12-persona batch deferred to owner opt-in.

### Not shipped in this canary
- Tier-1 profiles 3-12 (10 remaining). Extraction is mechanical against
  the schema in `references/target-model-profiles/README.md`.
- `shiroe/memory/cost_router.py` deep integration — kept surgical; callers
  invoke `estimate_input_tokens` / `relative_cost` from the profile module
  directly. Deeper wiring lands with the full Tier-1 batch.
- Empirical (runtime measured) token-reduction numbers — the 75% aggregate
  is theoretical (derived from `already_knows` × 250-token synthetic
  category size vs 3000-token baseline). Real-token measurement lands in
  the Phase-16 v2 pass, after Tier-1 completes.

---

## [1.1.0] — 2026-07-10

Audit remediation release — closes the Repository-Wide Consistency Audit.
The audit record is maintained as an operator record outside this repository.
Baseline commit `b82c641`.

### Added

- **`SOUL.md`** — 5 operating principles at repo root; boot step 0 per AGENTS.md §0
  is now fulfilled (SHR-AUDIT-015).
- **`shiroe/security/policy.py`** — typed loaders for PRIVACY.md, REDACT.md,
  SHARING_POLICY.md, config/PERMISSIONS.md; every LLM/network call gates through
  `require_connector` / `require_network` (SHR-AUDIT-001, 002, 006, 007).
  Session-override lanes: `SHIROE_ALLOW_NETWORK=1`, `SHIROE_ALLOW_CONNECTOR=<csv>`.
- **`shiroe-registry.json`** — Registry v1.1 adds `agents[]`, `commands[]`,
  `team_packs[]`, `gates[]` arrays; `skill-importer` registered
  (SHR-AUDIT-016, 017).
- **`team-packs/faang-mangoes-council.md`** — 12-persona architectural decision
  panel (opt-in only).
- **`skills/imported/{gstack,ecc,mantishack,raptor,hacker-bob}/README.md`** —
  reference-only fleet import boundary docs.
- **`docs/audits/`** — full audit corpus + remediation artifacts.

### Changed

- **`pyproject.toml`** — `build-backend` corrected from
  `setuptools.backends.legacy:build` to `setuptools.build_meta`; `pip install .`
  now works (SHR-AUDIT-009). Python 3.13 and 3.14 classifiers added.
- **`shiroe/privacy.py`** — `audit()` default target = project root; `--strict`
  extends scan to `.py / .json / .yml / .yaml / .toml / .jsonl`; `_SKIP`
  narrowed to `docs/archive` + `tests/fixtures` only (SHR-AUDIT-005).
- **`shiroe/memory/core.py`** — `discover_project_root` prefers
  `config/PROJECT.md`, falls back to `AGENTS.md`; `scaffold_project` no
  longer writes absolute host paths into tracked config
  (SHR-AUDIT-003, 010).
- **`shiroe/cli.py`** — `cmd_init` skips prompts under non-TTY stdin; `cmd_grade`
  now scrubs and gates before LLM egress (SHR-AUDIT-001, 023).
- **`shiroe/lineage/importer.py`** — every `urlopen` gated through security
  policy (SHR-AUDIT-002).
- **`shiroe/release/checks.py`** — 6 → 12 subchecks; SHA-bound evidence blob
  under `docs/audits/release-evidence/` (SHR-AUDIT-021, R9).
- **`.github/workflows/ci.yml`** — YAML block-collection repaired; SemVer tag
  guard + shiroe-scope sweep now execute (SHR-AUDIT-011).
- **`scripts/check-version-consistency.py`** — also compares against latest git
  tag; documented lineage restart via `docs/PIVOT_LOG.md` marker
  (SHR-AUDIT-020).
- **`benchmarks/run-all.py`** — trust axis override requires
  `docs/TRUST_AUDIT.md` `Bound-commit-SHA` matching HEAD; else deterministic
  draft published (SHR-AUDIT-013).
- **`benchmarks/lineage_common.py`** — `_fake_resolver` renamed to
  `_stub_resolver` with explicit conformance-scope note (SHR-AUDIT-014).
- **`docs/HARNESS_MATRIX.md`** — evidence-state matrix replaces self-attested
  ✅ marks (SHR-AUDIT-022, D7).
- **`.github/ISSUE_TEMPLATE/{bug_report,feature_request}.md`** — security
  redirect banner added (SHR-AUDIT-026). `config.yml` URL corrected to
  `kanadhiayash/shiroe-memory-engine` (SHR-AUDIT-028).
- Multiple doc drift fixes across `QUICKSTART.md`, `MIGRATION.md`,
  `docs/HARDENING_OVERVIEW.md`, `docs/wiki/Home.md`, `AGENTS.md`,
  `commands/{start,status}.md`, `benchmarks/run-all.py` docstring, and
  `pyproject.toml` classifiers.

### Fixed

- Two absolute-path leaks: `config/PROJECT.md`, `references/shared-anti-hallucination.md`
  (SHR-AUDIT-003, 004).
- Docstring vs code drift in `benchmarks/run-all.py` (SHR-AUDIT-038).
- Stale wiki links + hero image URL (SHR-AUDIT-031).
- `God Mode` → `Enterprise` tier vocabulary across AGENTS.md + commands
  (SHR-AUDIT-036).

### Notes

- Version bump `1.0.0 → 1.1.0` per council-ratified D3 decision.
- Compatibility identifier retained per council-ratified D2:
  `shiroe-os` for install URLs (`pyproject.name`, `plugin.name`,
  `marketplace.name`); `shiroe:` namespace alias remains available.
- Tag lineage divergence with `v2.6.x` retained via `restart-from-2.6.1`
  marker in `docs/PIVOT_LOG.md`.

---

## [1.0.0] — 2026-06-19

Public launch. Trust-repair pivot — single source of truth for the active
version, operationally verified guarantees on every public surface. The
v2.6.x architecture (4-gate Auto-Activation, 14 skills, 6 agents,
R6 Zero Context Loss, three privacy modes, flat memory layout) is carried
forward unchanged. Pre-v1 history is archived to
`kanadhiayash/shiroe-os-archive`.

### Added

- **`shiroe/VERSION`** — single source of truth for the active version.
  `shiroe/__init__.py`, `shiroe/cli.py`, `pyproject.toml`,
  `shiroe-registry.json`, `.claude-plugin/plugin.json`, README badge, wiki
  installation copy, and `docs/RELEASE_LOG.md` all align with this file.
- **`scripts/check-version-consistency.py`** — fails CI on any drift
  between version surfaces.
- **`tests/`** — reproducible pytest suite covering version consistency,
  privacy redaction (positive + negative cases for every supported
  pattern), CLI contract, init scaffold, write-decision round-trip,
  db-status surface, and the structural validator. Coverage target on
  `shiroe/` is ≥85%; CI publishes the coverage report.
- **11 expanded privacy patterns** in `shiroe/privacy.py`:
  - `sk-proj-…` (OpenAI project keys)
  - bare `sk-…` provider-shaped tokens
  - `github_pat_…`, `ghp_…` (GitHub PATs)
  - `xoxb-…` (Slack bot tokens)
  - `AIza…` (Google API keys)
  - `AKIA…` (AWS access key IDs)
  - PEM private-key blocks (`-----BEGIN … PRIVATE KEY-----`)
  - natural-language `API key <token>`, `secret key <token>`,
    `access token <token>`
- **`shiroe audit-privacy --strict`** — exits non-zero on any unredacted
  hit, suitable for CI gates.
- **`SECURITY.md` rewrite** — vulnerabilities now route through GitHub
  Private Vulnerability Reporting plus a PGP-encrypted fallback contact;
  no public-issue disclosure path. See also new
  `SECURITY_CONTACTS.md`.
- **CI hardening** — every GitHub Action pinned to its full commit SHA
  with a human-readable tag comment; `.github/dependabot.yml` refreshes
  pins weekly. New workflows: `test.yml` (pytest matrix),
  `privacy-audit.yml` (strict scrub on PR), `version-consistency.yml`,
  `branch-retention.yml`.
- **Portability layer** — `scripts/harness-probe.py` detects the host
  harness and validates required-tool surface; new
  `docs/HARNESS_MATRIX.md` documents the install + smoke-test result
  per harness.
- **Adaptivity layer** — `skills/skill-importer/` pulls a skill from the
  user's broader skill directory into the project with provenance
  metadata; `skill-router` ranks candidates by trigger match + recency.
- **Scalability layer** — `team-packs/small.md`, `medium.md`,
  `enterprise.md` encode token / credit envelopes per team size;
  `budget-governor` enforces the envelope.
- **`benchmarks/`** — four-axis harness (portability, adaptivity,
  scalability, trust) with public rubric in `benchmarks/RUBRIC.md`;
  `benchmarks/run-all.py` produces `docs/BENCHMARK_REPORT.md` and
  machine-readable `benchmarks/results.json`.
- **`docs/PIVOT_LOG.md`** — full pre-v1 design lineage (Pivot 1 → 4).
- **`docs/RISK_LOG.md`** — accepted risks for the v1.0.0 launch.

### Changed

- All version surfaces aligned on `1.0.0` (was: `pyproject.toml` 2.0.0,
  `__init__.py` 2.0.0, plugin manifest 1.0.0, README 2.6.1,
  registry 2.6.1-phaseD).
- `shiroe-registry.json` `version` and `generated` fields refreshed.
- `README.md` reframed for public launch; install matrix unchanged.
- `docs/RELEASE_LOG.md` rewritten with v1.0.0 as the first public release;
  pre-v1 tags listed as archived.

### Architecture (carried forward unchanged from v2.6.1)

- 6 background agents.
- 14 disciplined skills with strict triggers.
- 4-gate Auto-Activation chain (budget → router → fleet → prompt).
- R6 Zero Context Loss invariant.
- 6 on-demand team packs (now extended with size variants).
- Three privacy modes (default `abstract`).
- Flat per-project markdown memory layout.

### Removed

- Public-issue route for security disclosures (now private only).
- Moving-major-tag GitHub Action references (now SHA-pinned).
- Stale `2.0.0` / `2.6.1-phaseD` strings in version surfaces.

### Migration from v2.6.1

No data migration required. `memory/`, `PRIVACY.md`, `REDACT.md`,
`SHARING_POLICY.md`, `config/` keep their paths. Reinstall the plugin to
pick up v1.0.0:

```bash
claude plugin uninstall shiroe-os@shiroe-os
claude plugin marketplace add kanadhiayash/shiroe-os
claude plugin install shiroe-os@shiroe-os
claude plugin list | grep "shiroe-os.*1.0.0"
```

If you need to stay on v2.6.1, install from the archive repo
`kanadhiayash/shiroe-os-archive` (branch `legacy/v2.6.1`).

---

## Pre-v1.0.0 history (archived)

The entries below describe the v2.6.x line that preceded the v1.0.0
public launch. The corresponding git history lives in
`kanadhiayash/shiroe-os-archive`.

---

## [2.6.1] — 2026-06-08

Polish release on top of v2.6.0. Hardens the four Auto-Activation Gates with
code-backed enforcement, normalizes model identifiers across the pack, and
extends R6 (Zero Context Loss) coverage.

### Added

- **Model resolver** (`_shared/model-resolver.md`) — canonical Anthropic id
  mapping (`claude-haiku-4-5-20251001`, `claude-sonnet-4-6`, `claude-opus-4-7`)
  + aliases. Single source of truth for tier → model id.
- **Event-schema validator** — eleven known event types with required and
  optional payload keys; rejects unknown events at validate time.
- **Marker-file probe** in `fleet-activator` — per-tool marker file required
  before any external tool is declared reachable.
- **Prompt injection filter** in `prompt-context-engine` — pattern-scans for
  override markers; wraps suspicious content in `<context type="untrusted-input">`.
- **Irreversibility cool-down** in `prompt-context-engine` — 60s window;
  auto-approve allows only read-only / dry-run / draft-to-temp until 90s.
- **NFKC + homoglyph guard** in `caveman-handoff` — normalizes path strings,
  flags non-ASCII and Cyrillic / Greek / fullwidth lookalikes.
- **Dual-key override** in `budget-governor` — single-key override insufficient;
  requires `OVERRIDE: …` plus an `<override-acknowledged>` block. Repeat
  overrides become reclassification candidates.
- **Stack-cap lint** in `skill-router` — validator rejects routes with more
  than five skills active simultaneously.
- **R6 sweep** — Zero Context Loss extended from four to nine SKILL.md files.

### Changed

- `scripts/shiroe-validate.py` — skill count read dynamically from registry
  (no hardcode). PATTERNS.jsonl lint reports unknown event types.
- `shiroe-registry.json` — model identifiers normalized to full Anthropic ids.

### Removed

- Hardcoded skill counts in the validator.

### Documentation

- `_shared/rules.md` R6 doctrine clarified.
- Wiki Architecture page updated with v2.6 4-gate diagram.

---

## [2.6.0] — 2026-06-08

Major feature release introducing the **4-gate Auto-Activation chain**. Every
major task now self-classifies cost, stack, prompt, and handoff before any
token spend.

### Added

- **skill-router** — declares `[skill-router] domain=<D> lead=<L> support=[…] qa=<Q>`
  inline before every major action. Stack cap five.
- **fleet-activator** — probes external tool reachability and declares
  `[fleet-activator] <tool>: reachable|UNREACHABLE-…` per tool.
- **prompt-context-engine** — classifies prompt as STRUCTURED, AMBIGUOUS, or
  HOSTILE; restructures when needed; declares `[prompt-context-engine] …`.
- **caveman-handoff** — model-tier-aware handoff compression with
  byte-equal-on-decompress invariant.
- **budget-governor** rewrite — gate-style `[budget-governor] weight=… tier=… est=…`
  declaration before any spend, with override grammar.
- **Core Principle 13** — Auto-Activation Gates.
- **Core Principle 14** — R6 Zero Context Loss.

### Changed

- Skills count 10 → 14.
- Every major task surfaces a gate declaration to the user before spend.

### Migration

Additive. No breaking changes from v2.5.x.

---

## Earlier history

Earlier releases (v2.5 and the pre-rebrand line) are not maintained on this
branch. The v2.6 pack is the canonical surface.

---

## Command center

Notion: private maintainer workspace. The URL is redacted here rather than the
section removed (SHR-022) — this file is append-only history, and the link was
never part of a release entry.
