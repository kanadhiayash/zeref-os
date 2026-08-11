# Release Process

Shiroe releases must be evidence-based and reproducible.

## Release branch

Use:

    release/shiroe__vX.Y.Z

## Required gates

Run:

    python3 -m pytest -q
    python3 scripts/shiroe-validate.py
    python3 -m shiroe audit
    python3 -m shiroe audit-privacy --strict
    python3 scripts/check-version-consistency.py
    python3 -m shiroe release check
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
`.claude-plugin/`, `agents/`, `commands/`, `skills/`, `references/`,
`team/`, `team-packs/`, or `shiroe/`) must bump the version in lockstep
across `shiroe/VERSION`, `pyproject.toml`, `shiroe-registry.json`,
`.claude-plugin/plugin.json`, the README badge, and `docs/wiki/Installation.md`
— enforced by `scripts/check-version-consistency.py` (a required gate,
above). Skipping the bump is the single most common cause of a stale
install; `shiroe doctor --installation` / `shiroe version --verbose` report
the installed manifest (version, git SHA, content digests) so a stale cache
can be diagnosed from the outside.

## Tags

Use SemVer tags:

    vX.Y.Z

Do not delete tags unless there is a security, legal, or severe public-trust reason. Prefer deprecation notes over deletion.

## Benchmark claims

Allowed:

- Local deterministic benchmark gate passed.
- Fixture adapter passed.
- External benchmark run verified on a named date.

Not allowed without evidence:

- World best.
- Top ranked.
- 10/10 globally.
- Production secure.
