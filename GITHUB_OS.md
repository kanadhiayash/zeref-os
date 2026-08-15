<!-- privacy-audit: allow-file "Repository governance doc with public command examples." -->

# Repository Governance

`AGENTS.md` is the canonical operational specification. This file records
repository-level conventions only.

## Branches

Use short-lived topic branches. `main` is protected and release-bound.

Branch naming:

```text
<type>/shr-<short-description>
```

Examples:

- `feat/shr-node-dispatcher`
- `fix/shr-policy-deny`
- `docs/shr-runtime-docs`

## Commits

Use Conventional Commits with scope `(shiroe)`:

```text
feat(shiroe): add node lease store
fix(shiroe): keep default deny semantic
docs(shiroe): refresh runtime quickstart
```

## Required Local Gates

```bash
python3 -m compileall -q shiroe
python3 -m pytest -q
python3 -m shiroe doctor --json
python3 -m shiroe state verify --json
```

Do not push, merge, publish, deploy, change credentials, or modify external
infrastructure without explicit maintainer approval.

## Classification

- `public`: README, changelog, release notes, root operational docs, privacy
  policy files, and architecture docs intended for users.
- `internal`: tests, scripts, local evidence, generated development artifacts.
- `restricted`: credentials, private user data, unpublished customer data, and
  local absolute paths. Restricted material is never committed.
