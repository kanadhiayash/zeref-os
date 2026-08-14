<!-- privacy-audit: allow-file "Benchmark-entry audit evidence packet. No credentials, no user data." -->

# Benchmark-Entry Audit — candidate SHA `f840674`

Fresh audit of the hardened candidate tree against the FINAL
benchmark-entry checklist. Measured locally on the candidate SHA; no
benchmark run was started (benchmark design and execution are a
separate post-hardening program, per the handoff).

**Candidate SHA:** `f840674815447c8f6799f93d584f29145a0b7777` (main)

## Result: **CLOSED**

Two veto axes are BLOCKED in this environment (offline host, single
wired harness). Per the checklist, any veto failure keeps benchmark
status CLOSED. Everything else measured PASS.

## Axis-by-axis

| Axis | Target | Measured | Verdict |
|------|--------|----------|---------|
| Runtime maturity | ≥93/100 | engines + CLI operational, all gates green | PASS (qualitative) |
| P0 correctness defects | 0 | none open | PASS |
| High correctness defects | 0 | none open | PASS |
| Mandatory invariant pass | 100% | `tests/invariant/` all green | PASS |
| Prescribed lifecycle | 100/100 | H5.2 stress = 100/100 | PASS |
| Canonical state integrity | 100% | `state verify` chain ok; replay-equivalence green | PASS |
| Human approval bypass | 0 | approval-advisor cannot write; policy pause/resume proven | PASS |
| Active dead-surface refs | 0 | dead-surface scanner green | PASS |
| Core acceptance skips | 0 | 1 documented follow-up skip + 2 env-venv skips (see below) | CAVEAT |
| Critical line coverage | ≥90% | **92.0%** (2069/2248) | PASS |
| Critical branch coverage | ≥80% | **81.3%** (465/572) | PASS |
| Supported harness continuity | 100% | packet contract PASS; live cross-harness runs BLOCKED | **BLOCKED** |
| vNext release readiness | PASS | `scripts/release_ready.py` rc=0 | PASS |
| Required CI | PASS on SHA | Shiroe Verify green on `f840674` | PASS |
| Provider/harness metadata | current + verified | intra-repo consistent; live refresh BLOCKED | **BLOCKED** |

## Test evidence

- Full suite: **949 passed, 3 skipped** (148.98s).
- Skips:
  - `tests/test_trust_registry.py` + `tests/test_quality_matrix.py`
    — pinned-venv interpreter missing (environmental, not a product
    skip; both run in CI where the venv exists).
  - `tests/test_audit_logs.py::...` — CLI-driven audit-emit path;
    Phase 07 CLI redesign dropped it, direct AuditLogger coverage is
    present, CLI-integrated emission is a documented post-vNext
    follow-up (see `docs/architecture/REMOVALS.md` Phase 08).
- Coverage (critical packages: policy, execution, work, storage,
  capabilities, memory): line 92.0%, branch 81.3%, combined 89%.
- Global line coverage: 75%.

## The two blockers

1. **Supported harness continuity** — only `claude_code` is wired on
   this host. The packet-level continuity contract is proven by
   `tests/integration/handoff/test_canonical_continuity.py` (H6.1),
   but live bounded continuation across Codex / Gemini CLI / Hermes /
   Kimi Code / Odysseus was not executed. See
   `docs/evidence/h6_2_harness_reachability.md`.
2. **Provider/harness metadata** — offline host; live model-catalog
   refresh from official provider docs was not performed. Intra-repo
   version consistency is PASS. See
   `docs/evidence/h7_3_provider_metadata_refresh.md`.

## Unblocking path

Run this audit from an online host that has each supported harness CLI
+ credentials wired:

1. Execute the bounded cross-harness continuation workflow (H6.2) and
   record PASS/UNKNOWN per harness.
2. Refresh provider model catalogs (H7.3) and reconcile against
   `shiroe/adapters/providers/*.json`.
3. Re-run this audit; if both axes flip to PASS and the caveat skip is
   closed or explicitly waived, benchmark status may open.

Until then: **CLOSED**. Do not claim benchmark leadership or entry.
