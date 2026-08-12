<!-- privacy-audit: allow-file "Release verdict. Documents gate results and evidence-class scope; no user data." -->

# Release Verdict — 2.0.0-alpha.3 (hardening integration + external benchmark truth gate)

_Date: 2026-07-27. Branch: `test/zeref__external-benchmark-truth-gate`, built from
`feat/zeref__context-budget-allocator` (3a29abf) plus
`test/zeref__routing-classifier-evals`, `fix/zeref__unicode-hybrid-retrieval`,
and `fix/zeref__plugin-identity-install-freshness`. HEAD at time of writing:
`ae7fe41`._

**Headline: not production-ready.** Every local gate is green, but "every
local gate is green" is a narrower claim than "production-ready" — no
external benchmark has ever run against this engine, and one internal gate
(the fixture-based internal quality axes) is structurally skipped on a clean
checkout rather than actually executed. Both are stated plainly below rather
than smoothed over.

---

## Facts

Commands actually run against this branch, with actual results:

- `python3 -m pytest -q` — **0 failures**, 1 skip, exit 0. Confirmed
  repeatedly across every merge step and after every subsequent change.
- `python3 scripts/zeref-validate.py` — passes, one informational warning
  (`memory/` is an empty tracked scaffold on a fresh checkout — expected).
- `python3 scripts/check-version-consistency.py` — all 6 tracked surfaces
  plus git tag lineage aligned on `2.0.0-alpha.3`.
- `git diff --check` — clean, no whitespace errors.
- `python3 -m zeref release check` — exit 0. 14 PASS, 1 SKIP
  (`benchmarks`), 1 WARN (`target_profiles`). Full text captured in this PR.
- `python3 -m zeref doctor` — exit 0. 9 PASS, 1 WARN (`target_profiles`).
- `python3 -m zeref claims check` — exit 0, "No claim-gate findings." — the
  live public surface (README, docs/) currently contains none of the three
  blocked claim shapes.

Integration merges (PR3, PR7, PR9 onto the PR1/2/4/5/6 base) were **all
clean** — zero conflicts across all three `git merge` operations. No manual
conflict resolution was required anywhere in the stated "expected conflict
zones" (PR6/PR7 context-or-search overlap, PR9's 39-file surface).

Zero mandatory dependencies (`dependencies = []` in `pyproject.toml`)
remains true after this work — the truth gate and freshness-grading code
added here use only `re`, `json`, `pathlib`, and `dataclasses`.

## Assumptions

- Both on-disk target-model profiles (`gpt-5-5-instant`, `claude-opus-4-8`)
  are graded `source_authority: third_party` because their `source_url`
  points at `github.com/asgeirtj/system_prompts_leaks`, a community mirror
  repo with no vendor byline. This is a factual read of the URL, not a
  vendor confirmation — nobody at OpenAI or Anthropic verified these
  extractions. If either vendor later publishes an authoritative version of
  these prompts, `source_authority` should be revisited, not just the date.
- The claim-gate's public-claim scanner is **pattern-based**, tuned to the
  three constraint shapes this program named explicitly (routing-accuracy/
  CRITICAL-recall claims, contested-vendor comparisons + missing baselines,
  unscored external-benchmark scores). It is not a general-purpose claim
  parser. A claim that overstates evidence in a shape the patterns don't
  cover would not be caught. This is a scope decision, not an oversight —
  documented here so it isn't mistaken for exhaustive coverage.
- "Full-context beats purpose-built memory products at small-to-medium
  lengths" (the premise behind the required-baseline-pair constraint) is
  taken from the program's own instructions (Mem0's published baseline:
  full-context 72.9% vs Mem0 66.9%; Letta grep 74.0%) and was not
  independently re-derived in this session.

## Unknowns

- **Whether Zeref's memory engine actually helps, hurts, or is neutral
  relative to full-context or a lexical baseline on any real external
  dataset.** No LoCoMo/LongMemEval/PersonaMem/RULER/HELMET run has ever
  been executed — `benchmarks/external/results/` does not exist. The
  harness (loaders, baselines, provider adapters) is real infrastructure,
  not a placeholder, but infrastructure existing is not evidence of
  performance.
- Whether the routing criticality classifier generalizes beyond its
  48-entry corpus. The corpus and the classifier were authored together
  (documented in the test file itself); this is fixture-coverage by
  construction, not a generalization result, and no held-out or
  independently-labeled corpus exists to check it against.
- Whether the pattern-based claim scanner would hold up against a
  determined or careless attempt to phrase an overclaim just outside its
  regexes — it was not adversarially tested beyond the 9 unit cases and one
  live-repo regression case in `tests/test_claim_gate.py`.

## Risks

- **Regression risk on the claim gate is currently a pattern list, not a
  parser.** Anyone editing README.md/docs/*.md in the future could phrase a
  real overclaim in a way that slips past the specific regexes here. The
  gate is a floor, not a ceiling.
- **The internal quality-axes benchmark check is a SKIP, not a PASS, on a
  clean checkout**, because it depends on a local-only lineage intake CSV
  (`ZRF_64_repo_lineage_intake.csv`) that is intentionally not committed.
  `release_passed()` correctly does not let a SKIP count as a PASS, and the
  CLI output says so loudly — but it means the 22-axis internal
  self-check literally does not run in CI or on a fresh clone unless that
  fixture is supplied out-of-band. This was true before this session and is
  unchanged by it; flagging it here so it isn't assumed to be exercised by
  "the suite is green."
- **`source_authority: third_party` on both current profiles means the new
  `official`-stale hard-fail path has never fired against real production
  data** — only against the synthetic fixtures added in
  `tests/test_target_profile_freshness.py`. If a future profile is
  genuinely vendor-sourced and goes stale, this is the first time that path
  will be exercised for real.
- Bumping the plugin version without a corresponding publish is itself a
  no-op — the version-bump in this branch only fixes the stale-cache defect
  once it reaches whatever ships the plugin (not addressed here per
  governance: no push, no PR, no publish in this session).

## What's enforced at runtime vs. contract-only

| Claim | Enforcement |
|---|---|
| Profile freshness graded by source authority | **Runtime** — `zeref release check` and `zeref doctor` both call the same `grade_profile_freshness()`; a stale `official` profile fails the process exit code, not just a doc note. |
| Public claims can't exceed evidence class (3 named constraints) | **Runtime** — wired into `zeref release check` as the `claim_gate` finding (hard fail on any hit) and available standalone via `zeref claims check`. |
| Routing-accuracy claim blocked pending held-out corpus | **Runtime** for the pattern-matched phrasing; **contract-only** beyond that — the underlying fact ("this corpus is fixture-coverage") is prose in the test file, machine-readable only via the capability matrix's hardcoded entry, not derived from the corpus itself. |
| External benchmark "explicitly unscored" posture | **Runtime** for score-shaped claims (`\d+%` near a benchmark name without a run on record); the absence of a real run is checked by looking for `benchmarks/external/results/*.json`, which is a real, falsifiable check. |
| Capability evidence matrix (registry × maturity × tier × claim-allowed) | **Runtime**, generated live from `zeref-registry.json` + `tests/` on every `zeref claims matrix` call — not a stored/stale document. |
| Version-surface consistency | **Runtime** — `scripts/check-version-consistency.py`, wired into `zeref release check` as `version_consistency`. |
| Install-freshness / stale-cache detection | **Runtime** for the manifest math (`is_stale`); **not wired into CI or a publish hook** in this session — nothing here automatically blocks a future publish that forgets to bump the version again. That remains a process discipline, not a code gate. |

## What this session did not do (publish losses / exclusions)

- **No external benchmark was run.** Zero LoCoMo/LongMemEval/PersonaMem/
  RULER/HELMET numbers exist for Zeref, a full-context baseline, or a
  lexical baseline. The correct public posture remains "explicitly
  unscored," and that is now enforced, not just written down.
- **No held-out or independently-labeled routing corpus was created.**
  Building one was out of scope for this task; the gate blocks the claim
  instead of fabricating the evidence.
- No push, no PR, no publish — per governance, all work is local commits on
  `test/zeref__external-benchmark-truth-gate`.
- The claim-gate scanner does not yet cross-reference the capability
  evidence matrix against specific prose claims by capability name (e.g.
  tying a doc sentence about `skill:budget-governor` to its `contract`
  maturity). It currently enforces the three named constraints and nothing
  broader; `build_capability_matrix` is real and queryable
  (`zeref claims matrix`) but is not yet the enforcement substrate for
  every capability, only the three constraints this program specified.
- `docs/_evidence/` and `docs/_research/` were intentionally left unstaged
  per governance.

## Verdict

**Green, not ready.** All local gates pass from a clean state
(`pytest`, `zeref-validate.py`, `check-version-consistency.py`,
`git diff --check`, `zeref release check`, `zeref doctor`). That is a real,
verified statement about local invariants and honesty discipline — it is
not a statement about how well the memory engine performs, because no
external measurement has ever been taken. The only claim this branch is
entitled to make publicly about comparative or absolute memory performance
is "unscored, infrastructure exists" — and that is now the claim the code
itself enforces, not just the claim the docs happen to make today.
