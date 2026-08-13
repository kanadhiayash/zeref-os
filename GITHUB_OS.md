<!-- privacy-audit: allow-file "Governance spec cites credential-shaped tokens in never-commit list." -->

# Shiroe — Repo Doctrine (per-repo GITHUB_OS)

Git and release conventions for this repository.

## Source of truth

- **Canonical spec**: `AGENTS.md` (root of this repo) — Shiroe behavioral constitution
- **This file**: git, release, and classification conventions for the repo

## Conventions

### Branch model

Protected trunk (`main`) plus short-lived topic branches. `main` is the only
long-lived branch and the only base a PR targets. Full model — allowed types,
branch lifetime, squash-merge and retention rules — in `docs/BRANCHING.md`.

### Branch naming

`<type>/shr-<short-description>`.

Examples:
- `feat/shr-approval-lifecycle-hardening`
- `fix/shr-validator-skills-count`
- `release/*` — frozen-baseline snapshot (never receives further commits after creation; named per `docs/RELEASE_PROCESS.md`)

Branches predating the rename carry `<type>/shiroe__<short-description>` and
`<type>/<legacy-product-name>__<short-description>`. Those are history; do not create new ones.

### Tags

SemVer `v<major>.<minor>.<patch>` on `main` only.

### Commits

Conventional Commits with scope `(shiroe)`. Examples:
- `chore(shiroe): release v1.0.0`
- `feat(shiroe): add prompt-context-engine Gate #3`
- `fix(shiroe): validator dynamic skill count from registry`
- `docs(shiroe): add R6 Zero Context Loss to _shared/rules.md`
- `ci(shiroe): add shiroe-validate workflow`

### Required gates before push

1. `python3 scripts/shiroe-validate.py` — passes (Skills count matches registry; PATTERNS lint 0)
2. Shiroe-scope sweep: every staged file matches allowlist (`AGENTS.md|CHANGELOG|...|scripts/|skills/|team-packs/|tests/|shiroe/`); no non-shiroe bleed
3. No `--force` to main; no `--no-verify`; no skipping hooks
4. R6 (Zero Context Loss) — `_shared/rules.md#R6` honored across all skill writes
5. Privacy gate — `PRIVACY.md` mode + `REDACT.md` classes enforced before any external transmission

### Model-resolver pinning

Per `_shared/model-resolver.md`: registry uses full Anthropic ids (`claude-haiku-4-5` / `claude-sonnet-4-6` / `claude-opus-4-7`). Bare aliases (`haiku`/`sonnet`/`opus`) accepted via `model_alias` field for back-compat. Cost-sensitive Opus work pins `claude-opus-4-6` (avoids +35% tokenizer inflation of 4.7).

### Memory layer discipline

Per AGENTS.md §0 reading order:
- Every ship cycle includes a `wiki-maintenance` pass before `/stop`
- `memory/{hot.md,index.md,DECISIONS.md,RISKS.md}` refreshed at every release
- `memory/patterns/PATTERNS.jsonl` records session-start + gate events + wiki-writes (validator allowlist enforced)

### Artifact naming (new files only)

`[scope]_[subject]_[type]_[state]_[owner]_[yyyy-mm-dd]_v[major.minor]`.

Existing repo files (SKILL.md, AGENTS.md, CHANGELOG.md, etc.) keep their established Shiroe-OS conventions.

### Classification

- `public`: README.md, CHANGELOG*.md, GitHub Releases, AGENTS.md, SKILL.md, PRIVACY.md/REDACT.md/SHARING_POLICY.md
- `internal`: memory/*, agents/, scripts/, tests/, shiroe/, _shared/
- `restricted`: never committed (no credentials / PII / client data)

## Repo-specific paths

- Plugin manifest: `.claude-plugin/plugin.json`
- Harness stubs: `CLAUDE.md` / `GEMINI.md` / `.cursor/rules/shiroe.mdc` / `.windsurfrules` / `.aider.conf.yml.example`

## Command center

Notion: private maintainer workspace. The URL is not published in this
repository (SHR-022).
