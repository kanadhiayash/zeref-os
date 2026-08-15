# Source authority (SHR-003)

When two surfaces in this repository disagree, this file decides which one wins.
It is the machine-readable answer to "who is allowed to say what is true here",
and `scripts/check-canon-consistency.py` reads it on every test run.

## Why this exists

Shiroe accumulated five kinds of writing — executable code, decision records, the
agent spec, a glossary, generated views, and narrative prose — and let all five
make claims about the same subjects. Nothing said which one to believe. The
canonical-store question was the clearest casualty: `SOUL.md` and `AGENTS.md`
used to say canonical state was Markdown on disk, `ADR-0001` said SQLite is
canonical current state and Markdown is a generated view, and `README.md` agreed
with the ADR. A reader had no principled way to pick. This file gives them one,
and `fix/shr-canonical-state` used it to settle that particular case in the
ADR's favour.

## The precedence order

Ten tiers, highest authority first. A claim from a lower-numbered rank overrides
a conflicting claim from any higher-numbered rank.

| Rank | Tier | What it is | Why it ranks here |
|------|------|------------|-------------------|
| 1 | `code-and-schemas` | `shiroe/**`, `pyproject.toml` | It executes. It cannot be aspirational. |
| 2 | `accepted-adrs` | `docs/adr/ADR-*.md` | A deliberate, dated, reviewed decision that code is obliged to follow. |
| 3 | `operational-config` | `config/**` | Can alter runtime behavior and must not hide as evidence. |
| 4 | `harness-integration` | Harness shims and plugin metadata | Instructs hosts how to boot the runtime. |
| 5 | `release-gates` | `scripts/**` | Executable validation and release-decision gates. |
| 6 | `ci-release-ops` | `.github/**` | CI and repository automation. |
| 7 | `agents-spec` | `AGENTS.md`, `SOUL.md` | The contract every harness reads. Binding, but written ahead of the code. |
| 8 | `glossary` | `docs/GLOSSARY.md`, `docs/wiki/Glossary.md` | Fixes vocabulary so the tiers above can be compared at all. |
| 9 | `generated-docs` | `docs/wiki/**` | Derived from a rank-1 source. Authoritative about itself, never about intent. |
| 10 | `narrative-docs` | `README.md`, `docs/*.md`, `docs/architecture/*.md`, root manifests | Explanation and onboarding. Loudest, least binding. |

## The three evaluation rules

**1. `tiers` is evaluated before `archived`.** This ordering is load-bearing, not
incidental. An accepted ADR that happens to sit near superseded material stays
authoritative, while superseded prose is silenced no matter how confidently it is
written. Reversing the two would let an archive glob mute a live decision record.

**2. `unscoped` is evaluated last.** It is the explicit "not a canon surface"
list — tests, scripts, CI, fixtures, recorded evidence. `docs/security/**` sits
here for the same reason `docs/canon/**` and `docs/audits/**` do: a redaction
manifest records what was found in the object store at one commit and what the
owner decided about it. It makes no claim about how the product works, so it has
no authority to conflict with. Anything not matched by
`tiers`, `archived`, or `unscoped` is an **unclassified surface** and fails the
audit. There is no implicit default. That is the whole point: a new top-level
directory must be given an authority answer before it can ship.

**3. Ties within a rank are not conflicts.** Two globs in the same tier may match
the same file. Two globs in *different* tiers matching the same file is an
ambiguity and fails the audit.

## Archived surfaces

Archived material is excluded from the conflict scan entirely. It is allowed to
contradict current canon — that is what "superseded" means — but it must say so
in its first 15 lines, and no active surface may cite an archived directory as if
it were live.

`CHANGELOG.md` is archived for a narrower reason and carries no marker: it is
*about* prior releases, so it has to name what shipped at the time. Rewriting it
to read as current would falsify a record.

Every archived entry must therefore carry **either** a `marker` **or** a
`why_no_marker`; an entry with neither is rejected outright (exit 2). A markerless
entry silences its files from the conflict scan while looking indistinguishable
from the two legitimate cases above, so the exemption has to be stated rather than
inferred from an absent field.

## Conflict rules

Named questions with a single settled authority. The authority must be an ADR
with `**Status:** Accepted`. A registered authority is exempt from the conflict
scan for the obvious reason: `docs/adr/ADR-0001-canonical-store.md`'s Context
section has to quote the contradiction it retired in order to explain the
decision, and `docs/adr/ADR-0006-graph-projection-invariant.md` has to say what
a graph is *not* in order to say what it is.

## The map

```json shiroe.source-authority/v1
{
  "schema": "shiroe.source-authority/v1",
  "tiers": [
    {
      "rank": 1,
      "id": "code-and-schemas",
      "paths": [
        "shiroe/**/*.py",
        "shiroe/**/*.json",
        "shiroe/VERSION",
        "pyproject.toml"
      ]
    },
    {
      "rank": 2,
      "id": "accepted-adrs",
      "paths": ["docs/adr/ADR-*.md"]
    },
    {
      "rank": 3,
      "id": "operational-config",
      "paths": ["config/**"]
    },
    {
      "rank": 4,
      "id": "harness-integration",
      "paths": [
        ".claude-plugin/**",
        ".cursor/**",
        ".windsurfrules",
        ".aider.conf.yml.example",
        "CLAUDE.md",
        "CODEX.md",
        "GEMINI.md",
        "LLAMA.md"
      ]
    },
    {
      "rank": 5,
      "id": "release-gates",
      "paths": ["scripts/**"]
    },
    {
      "rank": 6,
      "id": "ci-release-ops",
      "paths": [".github/**"]
    },
    {
      "rank": 7,
      "id": "agents-spec",
      "paths": ["AGENTS.md", "SOUL.md"]
    },
    {
      "rank": 8,
      "id": "glossary",
      "paths": ["docs/GLOSSARY.md", "docs/wiki/Glossary.md"]
    },
    {
      "rank": 9,
      "id": "generated-docs",
      "paths": ["docs/wiki/**"],
      "exclude": ["docs/wiki/Glossary.md"]
    },
    {
      "rank": 10,
      "id": "narrative-docs",
      "paths": [
        "README.md",
        "QUICKSTART.md",
        "INSTALL.md",
        "CONTRIBUTING.md",
        "SECURITY.md",
        "SECURITY_CONTACTS.md",
        "SHARING_POLICY.md",
        "PRIVACY.md",
        "REDACT.md",
        "GITHUB_OS.md",
        "SKILL.md",
        "docs/*.md",
        "docs/architecture/*.md",
        "references/*.md"
      ],
      "exclude": ["docs/GLOSSARY.md"]
    }
  ],
  "archived": [
    {
      "id": "changelog",
      "paths": ["CHANGELOG.md"],
      "why_no_marker": "A changelog is about the pre-rename project and is still appended to. Stamping it 'Superseded' would falsify a live record."
    }
  ],
  "unscoped": [
    "tests/**",
    "benchmarks/**",
    ".superpowers/**",
    ".superpowers/**",
    "assets/**",
    "memory/**",
    "docs/canon/**",
    "docs/security/**",
    "docs/audits/**",
    "docs/_evidence/**",
    "docs/evidence/**",
    "docs/archive/**",
    "retired Superpowers planning snapshots",
    ".gitignore",
    ".coverage",
    "pytest.ini",
    "LICENSE"
  ],
  "conflict_rules": [
    {
      "question": "canonical-store",
      "authority": "docs/adr/ADR-0001-canonical-store.md",
      "resolution": "sqlite=current-state, jsonl=history, markdown=generated-view"
    },
    {
      "question": "graph-projection",
      "authority": "docs/adr/ADR-0006-graph-projection-invariant.md",
      "resolution": "graphs=rebuildable-provenance-bound-projections, never-canonical-state"
    }
  ]
}
```

## Extending this file

Adding a directory means adding it to exactly one of `tiers`, `archived`, or
`unscoped`. Adding it to two different tiers fails the audit. Adding it to none
fails the audit. Deleting a directory without deleting its glob fails the audit
as a dead glob. All three failures are intentional: the map is only worth having
if it cannot silently rot.

Two further rules exist because both were reachable ways to remove a live surface
from every scan without leaving anything for a reviewer to see:

- A new `archived` entry must carry a `marker` or a `why_no_marker`. Neither
  fails the audit at exit 2.
- Using a tier's `exclude` to carve out a file that an `unscoped` glob then
  absorbs is reported as `excluded-into-unscoped`. Excluding a file into another
  *tier* is the intended use and stays silent.
