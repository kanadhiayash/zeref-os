<!-- privacy-audit: allow-file "Release verdict. Names commands, gates, and issue numbers. No user data." -->

# Release verdict — 3.0.0-alpha.1

**Verdict: NOT READY for a publication run. Ready for continued engineering.**

Bound to `dev` at the merge of the Shiroe migration series (#199, #200, #201,
#202, #203, #204).

## What this release is

The Zeref → Shiroe rebrand carried through every identity surface, plus three
defect fixes that were blocking on the retrieval and release-gate paths. It
is not a benchmark release. No external dataset was run, and no score is
claimed.

## Evidence

Every gate below was run on the merge commit, not quoted from a prior run.

| Gate | Result |
|---|---|
| `python3 -m pytest -q` | 963 passed, 1 skipped |
| `python3 scripts/shiroe-validate.py` | pass, incl. registry schema |
| `python3 scripts/check-version-consistency.py` | 6 version + 8 identity surfaces aligned |
| `python3 benchmarks/run-all.py` | `VERDICT: PASS` (internal axes) |
| `python3 -m shiroe audit-privacy --strict --fail-classes credentials` | 0 credential-class hits |
| `python3 -m shiroe release check` | no FAIL |
| CI (`shr-verify.yml`) | 12/12 on every merged PR |

The one SKIP in `release check` is `benchmarks`, whose lineage-intake CSV is a
local-only input. The one WARN is `target_profiles`, a stale third-party
profile with no authoritative publisher to re-verify against. Both predate
this release and neither is treated as passing evidence.

## What is verified

- The namespace migration is complete and the package installs, imports, and
  runs from a clean venv (CI `Clean-clone install + init/doctor`).
- Retrieval now ranks by Okapi BM25 on both the SQLite and JSONL paths, and
  the two agree on the same corpus.
- Existing projects survive the migration: environment variables, the
  canonical state DB, and the workspace policy directory each have a
  fallback or an adoption step, each with a test asserting end behaviour.
- No public surface carries an unverified superiority claim. The gate that
  enforces this now scans `references/` too, which is where the one real
  claim had been sitting unseen.

## What is NOT verified

- **Whether the retrieval fix closes the gap in #196.** The mechanism is
  fixed and unit-tested. It has not been re-measured against LoCoMo,
  LongMemEval, or PersonaMem, because benchmark runs are parked until
  hardening completes. #196 stays open.
- **Any external benchmark result.** No scored run has ever executed. The
  harness has only run in proxy mode.
- **The live provider and judge paths.** `AnthropicProvider.complete`,
  `GeminiProvider.complete`, and `GeminiJudgeClient.judge` remain
  implemented-but-untested against a mocked transport. Scoped, not delivered
  — tracked separately.
- **PyPI availability of the name `shiroe`.** Unverified; nothing was
  published.

## Blocking items before a publication run

1. Re-measure #196 on real datasets and publish the before/after.
2. Mocked-transport tests for the three live paths, before any paid quota is
   spent discovering one of them is broken.
3. Pin sha256 and enforce sample counts for the ConvoMem, RULER, and HELMET
   loaders — all three carry `PINNED_SHA256 = None`, so `--check` cannot
   detect a corrupt download.
4. A dry-run capacity manifest and an approved budget.

## Operator actions required

- Re-select the required status checks on `dev` and `main` in branch
  protection. The verify workflow was renamed `zrf-verify.yml` →
  `shr-verify.yml`, and GitHub binds required checks per workflow file, so
  the previous binding did not follow. Until that is done, `dev` is not gated.
- Create the `security+shiroe@kanadhiayash.dev` alias. The address is
  published in `SECURITY.md`; if it does not route, reports are lost.
