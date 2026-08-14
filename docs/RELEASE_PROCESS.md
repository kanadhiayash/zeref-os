# Release Process

Shiroe releases must be evidence-based and reproducible.

## Release branch

Use:

    release/shiroe__vX.Y.Z

## Required gates

Run:

    python3 -m pytest -q
    python3 scripts/shiroe-validate.py
    python3 -m shiroe doctor --json
    python3 -m shiroe verify --memory --json
    python3 -m shiroe state verify --json
    python3 scripts/check-version-consistency.py
    git diff --check

## Release notes

Release notes must include:

- Summary.
- Compatibility notes.
- Security notes.
- Known risks.
- Migration notes if needed.

## Version bump on every published change

Claude Code resolves an installed plugin's freshness from `plugin.json`'s
`version` field first, before marketplace metadata or commit SHA. If that
field does not change, a host may keep serving a previously cached payload
even though the source repository has moved on.

Every change that ships to the plugin marketplace (any edit under
`.claude-plugin/`, `references/`, or `shiroe/`) must bump the version in
lockstep across the surfaces `scripts/check-version-consistency.py`
enforces (a required gate, above): `shiroe/VERSION` (canonical),
`shiroe/__init__.py` loader, `pyproject.toml`,
`.claude-plugin/plugin.json`, `docs/wiki/Installation.md`, and the root
`SKILL.md` frontmatter. Skipping the bump is the single most common
cause of a stale install; `shiroe version --json` and
`shiroe doctor --json` report the installed manifest and runtime health
so a stale cache can be diagnosed from the outside.

## Tags

Use SemVer tags:

    vX.Y.Z

Do not delete tags unless there is a security, legal, or severe public-trust reason. Prefer deprecation notes over deletion.

## Public claims

Allowed:

- Full local test suite passed (`python3 -m pytest -q`).
- `shiroe doctor --json` returns `status: pass` on a clean project.
- Named verification commands with reproducible output.

Not allowed without evidence:

- World best.
- Top ranked.
- 10/10 globally.
- Production secure.
- Comparative benchmark leadership of any kind.

Benchmark machinery was retired in vNext (see
[`docs/architecture/REMOVALS.md`](architecture/REMOVALS.md)); a
separate program will re-introduce measured comparison later.
