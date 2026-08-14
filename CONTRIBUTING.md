<!-- privacy-audit: allow-file "Contribution doc references example maintainer email + branch names as spec." -->

# Contributing to Shiroe

Shiroe is a local-first AI work control plane for AI-assisted work. Contributions should improve the runtime, docs, guards, install path, or release safety.

## Before starting

For large changes, open an issue first.

For security issues, do not open a public issue. Read `SECURITY.md`.

## Branches

`main` is the only long-lived branch. Everything else is a short-lived topic
branch: cut from current `main`, one PR's worth of work, deleted when that PR
lands. PRs target `main`; there is no other base.

Use:

    <type>/shr-<short-description>

Examples:

    docs/shr-public-surface-overhaul
    fix/shr-privacy-redaction-edge-case
    test/shr-approval-lifecycle-regression

`docs/BRANCHING.md` is the branch model of record — allowed types, branch
lifetime, merge and retention rules. Read it before opening your first PR.

## Pull request expectations

A PR should include:

- Summary.
- Why the change is needed.
- User-visible behavior.
- Security impact.
- Verification commands and outputs.
- Risks and rollback notes.

Keep PRs focused. Prefer several clear commits over one large mixed commit.

## Required local gates

One command runs the full aggregate gate and prints a machine-readable
JSON result:

    python3 scripts/release_ready.py

It composes the individual checks below; run them directly when you want
to iterate on one:

    python3 -m pytest -q
    python3 scripts/check-canon-consistency.py --root .
    python3 scripts/check-active-identity.py --root .
    python3 scripts/shiroe-validate.py
    python3 scripts/check-version-consistency.py
    python3 scripts/check-trust-registry.py
    python3 -m shiroe doctor --json
    python3 -m shiroe state verify --json
    git diff --check
    git status --short

## Public claims

Do not add unsupported claims.

Allowed:

- Full local test suite passed (`python3 -m pytest -q`).
- `python3 -m shiroe doctor --json` returns `status: pass` on a clean project.
- Fixture adapter passed.

Not allowed without evidence:

- Best.
- World top.
- 10/10 globally.
- Production secure.
- Comparative benchmark leadership of any kind.

## Security rules

- Never commit secrets.
- Never weaken privacy gates to pass CI. The scanner defeats unicode-invisible strip, base32/base64/hex encoding, and nested-archive smuggling up to depth 3 by design; loosening any of these is a security regression.
- Never publish private paths or credentials.
- Never hide failures in verification evidence.
- Never claim a workspace was updated unless a file was actually written.
- Never delete release history unless there is a clear security, legal, or public-trust reason.
- Adding a public visual under `assets/` or citing a new external URL from `README.md` / root spec files requires an entry in `docs/canon/TRUST_REGISTRY.json` with an approved source + rights status. The `check-trust-registry.py` gate fails otherwise.
- Irreversible actions (push, merge, publish, delete, external message, secret read, …) are on the mandatory-approval list in `shiroe/policy/autonomy.py`. Execution pauses on them and cannot proceed without a human approval decision — never weaken that list to auto-run one.

## Branch retention

Protected refs — `main` and any frozen `release/*` baseline — are never deleted. If a branch name is unsafe, rename it to `archive/<original-name>` rather than deleting history.

Topic branches are the exception: deleting them once their PR lands is expected, and `.github/workflows/branch-retention.yml` deliberately does not fire on them.

## Releases

Release tags use:

    vX.Y.Z

Release notes must include:

- Summary.
- Compatibility.
- Security notes.
- Known risks.
- Migration notes if needed.

Read `docs/RELEASE_PROCESS.md`.

## Maintenance surfaces and ownership

`docs/OPERATIONS.md` maps every maintenance surface (canonical store,
registry, trust registry, provider adapters, release evidence, rollback
runbook, task + knowledge graphs, privacy scanner, policy precedence)
to an owner and a review cadence. Read that page before touching any
of them; `tests/test_operations_owners.py` fails when a row loses its
owner or cadence, so a silent drift is caught in CI.
