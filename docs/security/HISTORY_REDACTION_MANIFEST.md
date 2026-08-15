# History redaction manifest (SHR-029, SHR-031)

**Nothing in this repository's history has been rewritten.** This file is the
decision package that lets the owner decide whether any of it should be. It
classifies every sensitive-data candidate found in the object store as exactly
one of three things, with the evidence for each, so the answer to "do we need a
`filter-repo` run?" stops being a guess.

The procedure to execute *if* a rewrite is approved lives in
[`HISTORY_REWRITE_RUNBOOK.md`](HISTORY_REWRITE_RUNBOOK.md). No step in it may run
without written owner approval of a specific version of this file.

---

## How to read this

**The three classifications, and what each one commits you to:**

| Classification | Meaning | Cost |
|---|---|---|
| `current-tree cleanup` | Already removed from the working tree, or removable by an ordinary commit. History keeps the string; the live surface does not. | A commit. Reversible. |
| `all-history removal` | The string is only removable by rewriting every commit that carries it. | Every SHA changes. Force push. Every collaborator re-clones. Owner approval required. |
| `preserved historical lineage` | Deliberately kept. Either it is not sensitive (a test fixture, a pattern name, a public identity), or removing it would falsify a record. | None. But it is a decision, not an oversight, and it is recorded here as one. |

**A note on notation.** This document names one private host and describes, but
does not spell, two operator account names.

* The Notion host is written **defanged** — `copper-tv-288[.]notion[.]site` —
  the ordinary IOC convention. It is unambiguous to a reader, it is exact enough
  to build a replacement rule from, and it does not re-publish a working link.
  It is also why this file passes `tests/test_no_private_operational_references.py`
  (SHR-022) without that guard being weakened: the guard matches a literal dot,
  the defanged form has none, and no allowlist entry was added to it. See
  [Guard interactions](#guard-interactions).
* The two operator account names are **not written at all**, defanged or
  otherwise. A rewrite needs them, but it needs them at run time, in a local
  `expressions.txt` the runbook tells you to create and never commit. Putting
  them in a tracked file to describe removing them from tracked files would be
  self-defeating.

---

## Scan method

Produced by `scripts/scan-history-sensitive.sh`, which is read-only and
re-runnable. Re-run it to check this manifest is still true:

```
bash scripts/scan-history-sensitive.sh
```

**Coverage at the commit this manifest was recorded** (`74da95a`):

| | |
|---|---|
| Refs scanned | 29 — every local branch, remote-tracking ref, tag, **and the stash** |
| Commits reachable from `--all` | 243 |
| Objects in the store | 4994 |
| Blobs, each scanned once | 2944 |
| Of those, unreachable | 89 |

**Why blob-level rather than `git grep` over every commit.** The PR 01 inventory
(`docs/canon/GITHUB_SURFACE_INVENTORY.md` §3) grepped each commit's tree, which
re-counts an unchanged file once per commit: it reported `notion.site` 1265
times, `AKIA` 2440 times, `sk-` 4375 times. Those numbers describe how long
files sat still, not how much sensitive data exists. Scanning each blob once
gives the number a redaction decision needs — how many distinct file versions
carry the string — and it reaches the 89 unreachable blobs that `rev-list --all`
cannot see at all. Two of those turned out to matter (candidate `SHR-029-C3`).

**Why strict shapes rather than substrings.** Every credential pattern is
matched at full shape (`AKIA` *plus* the sixteen characters an AWS key ID
actually has), not as a substring. This is what collapses PR 01's four-figure
hit counts to zero: see [Credential re-verification](#credential-re-verification).

**What this scan does not cover.** Objects that have already been garbage
collected out of this clone. Objects that exist on GitHub's servers but were
never fetched here — GitHub retains unreferenced objects and serves them by SHA
for a period after a force push. Anything in a fork, a mirror, a CI cache, or a
third party's clone. Those are blast-radius facts, recorded per candidate below;
no local command can settle them.

---

## Candidates

Twelve candidates. **2 `current-tree cleanup`, 3 `all-history removal`,
7 `preserved historical lineage`.** None unclassified.

### The one that actually matters

**`SHR-029-C2` — the private Notion workspace URL, in reachable history.**
`copper-tv-288[.]notion[.]site/...-358d695d836a81af9f6adf30770217c3`, across
**14 distinct file paths, 56 reachable blobs, 224 of 243 commits**, first
introduced 2026-05-12 (`c8205f2`) and last carried 2026-08-04 (`a30aeda`).

It is present at the tip of **21 of 29 refs**, including **`origin/main` and all
three tags** (`v1.1.0`, `v1.1.1`, `v2.0.0-alpha.1`). That is the fact the
current-tree cleanup does not change: the cleanup commit (`3da7ff2`) lives on an
unpushed local branch, so as of this writing the URL is live in the published
repository regardless of what HEAD looks like locally.

It is not a credential. It is an unguessable-ID Notion published page. If that
page is set to "share to web", the URL is the entire access control, and the
cheap fix is not a history rewrite — it is un-publishing or re-publishing the
page, which invalidates every copy of the URL everywhere at once, including the
ones in forks and caches a rewrite can never reach. **The rewrite is the
expensive option and the weaker one. Do the page-level fix first.**

### The full table

| id | What | Classification | Still live | Objects | Owner |
|---|---|---|---|---|---|
| `SHR-029-C1` | Notion URL — current tree | current-tree cleanup | no | 0 at HEAD | kanadhiayash |
| `SHR-029-C2` | Notion URL — reachable history | **all-history removal** | yes | 56 blobs / 14 paths | kanadhiayash |
| `SHR-029-C3` | Notion URL — unreachable objects | **all-history removal** | yes | 2 blobs | kanadhiayash |
| `SHR-029-C4` | Operator home paths — current tree | current-tree cleanup | no | 0 at HEAD | kanadhiayash |
| `SHR-029-C5` | Operator home paths — reachable history | **all-history removal** | yes | 11 blobs / 8 paths | kanadhiayash |
| `SHR-029-C6` | Operator working-copy paths | current-tree cleanup | no | 0 anywhere | kanadhiayash |
| `SHR-029-C7` | Cloud-sync path literal in a guard draft | preserved historical lineage | yes | 1 blob | kanadhiayash |
| `SHR-031-C8` | AWS access key IDs | preserved historical lineage | no | 0 anywhere | kanadhiayash |
| `SHR-031-C9` | GitHub tokens | preserved historical lineage | no | 0 anywhere | kanadhiayash |
| `SHR-031-C10` | Provider API keys (`sk-`) | preserved historical lineage | yes | 8 blobs / 3 paths | kanadhiayash |
| `SHR-031-C11` | PEM private keys | preserved historical lineage | yes | 4 blobs / 2 paths | kanadhiayash |
| `SHR-031-C12` | Commit author email | preserved historical lineage | yes | 243 commits | kanadhiayash |

### Credential re-verification

PR 01 reported large hit counts for five credential patterns and triaged them by
hand as false positives. Re-verified here by shape rather than by substring,
across all 2944 blobs:

| Pattern | PR 01 substring hits | Strict-shape blobs | What the difference was |
|---|---|---|---|
| `AKIA[0-9A-Z]{16}` | 2440 | **0** | The bare word `AKIA` in redaction docs and CI regexes, deliberately fake fixtures (`_AKIA = "A" + "KIA"`), and base64 image bytes inside `assets/*.svg` |
| `gh[pousr]_[A-Za-z0-9]{36}` | 1379 | **0** | Pattern documentation and short fixture strings that never reach 36 characters |
| `sk-(ant-)?[A-Za-z0-9_-]{20,}` | 4375 | **8** | Substrings of ordinary words (`task-`, `risk-`, `desk-`). The 8 real matches are two fixtures and one English phrase — see `SHR-031-C10` |
| `-----BEGIN … PRIVATE KEY-----` | 186 | **4** | One test fixture, repeated across the commits that touched it — see `SHR-031-C11` |
| `BEGIN OPENSSH` | 0 | **0** | — |

**PR 01's conclusion holds: no real credential exists anywhere in this
repository's history.** The method is different and stricter, and it agrees.

### Corrections to the leads this PR was given

Recorded because the brief said to verify rather than trust, and two leads did
not survive verification. Neither changes any classification.

1. **"Two operator paths were redacted in PR 05."** They were not. PR 05
   (`3da7ff2`) removed no home-rooted path; its two deleted scripts
   (`scripts/shiroe-cleanup-branches.sh`, `scripts/shiroe-publish-releases.sh`)
   contained none. The last commit whose tree carried a real operator home path
   is `8cd8c47` (2026-07-10), and the removals happened across
   `23f3824`, `15b83ec`, `3050eed` and earlier. The *outcome* the lead asserts is
   correct — zero real operator home paths at HEAD, verified — only the
   attribution is wrong.
2. **"Two deleted scripts" carried the Notion URL.** One did.
   `scripts/shiroe-publish-releases.sh` carried it and was deleted in PR 05;
   `scripts/shiroe-cleanup-branches.sh` never contained it. The second
   URL-carrying script is `scripts/shiroe-publish-releases.sh`, deleted much
   earlier at the namespace rename.

### Cross-reference to the surface inventory

`docs/canon/GITHUB_SURFACE_INVENTORY.md` §7 row 3 ("Private Notion URL live in
four current-tree files") is **closed** — see `SHR-029-C1`. Row 4 (the
full-history question) is the live item and is answered by `SHR-029-C2` and
`SHR-029-C3` here. That inventory is recorded audit evidence and is not edited
by this PR; this cross-reference is the update.

---

## Guard interactions

Two gates in this repository are designed to fail on exactly the strings a
redaction manifest has to discuss. Neither was weakened.

**`tests/test_no_private_operational_references.py` (SHR-022).** Its Notion
matcher is `\b[A-Za-z0-9][A-Za-z0-9-]*[.]notion[.]site\b`, where `[.]` is a
literal dot. Writing the host defanged as `copper-tv-288[.]notion[.]site`
carries literal square brackets and cannot match. **No allowlist entry was added
and no pattern was relaxed** — the guard has no allowlist mechanism by design
(its own docstring explains why an exemption roster is the same trap as a hit
roster), and adding one for this file would have been the first crack in it.
The same guard is why the operator account names are absent rather than
defanged: its home-path matcher rejects placeholder segments but would correctly
flag a defanged real one, and it is right to.

**`scripts/check-active-identity.py` (SHR-032).** This one could not be
side-stepped. Three of the fourteen historical paths carrying the Notion URL are
named with the pre-rename identity, and so are the commit subjects that
introduced and removed it. Redacting those would destroy the evidence the
manifest exists to provide. This file — not the `docs/security/` directory, so a
second file here inherits nothing — was therefore added to `ALLOWLIST` with its
reason, and `MAX_ALLOWLISTED_PATHS` in
`tests/test_legacy_compatibility_boundary.py` was raised from 16 to 17 with the
reason in the same diff, which is the escape hatch that test's own comment
provides. The register grew by exactly one and says why. The runbook needed no
exemption.

---

## The map

```json shiroe.redaction-manifest/v1
{
  "schema": "shiroe.redaction-manifest/v1",
  "recorded_at_commit": "74da95a1332a74e8c4976a3059e180a0bdcb24f9",
  "rewrite_performed": false,
  "scan": {
    "script": "scripts/scan-history-sensitive.sh",
    "refs": 29,
    "commits": 243,
    "objects": 4994,
    "blobs": 2944,
    "unreachable_blobs": 89
  },
  "classification_counts": {
    "current-tree cleanup": 2,
    "all-history removal": 3,
    "preserved historical lineage": 7
  },
  "candidates": [
    {
      "id": "SHR-029-C1",
      "pattern_class": "private-notion-workspace",
      "what": "The private Notion workspace URL (host copper-tv-288[.]notion[.]site, page id 358d695d836a81af9f6adf30770217c3) as it stood in the working tree. It was live in four tracked files at a30aeda: CHANGELOG.md, GITHUB_OS.md, retired research resource, and scripts/shiroe-publish-releases.sh.",
      "classification": "current-tree cleanup",
      "still_live": false,
      "owner": "kanadhiayash",
      "evidence": {
        "refs": ["HEAD (security/shr-redaction-manifest)"],
        "paths": [
          "CHANGELOG.md",
          "GITHUB_OS.md",
          "retired research resource",
          "scripts/shiroe-publish-releases.sh"
        ],
        "objects": 0,
        "first_commit": "c8205f2 (2026-05-12) — chore: Shiroe Agent OS v2.0.0",
        "last_commit": "a30aeda (2026-08-04) — last commit whose tree carried it; removed by 3da7ff2 (PR 05)",
        "verify": "git grep -n -i -e 'notion[.]site' HEAD -- ':!docs/security' ':!tests/test_no_private_operational_references.py'  # exits 1, no output"
      },
      "blast_radius": "None outstanding. Already done, by an ordinary commit, reversible. Two of the four files were edits; scripts/shiroe-publish-releases.sh was deleted outright, which is the only irreversible-feeling part and is a file deletion, not a history change.",
      "rotation": "n/a at this level — the URL is not a credential, and the page-level mitigation is tracked under SHR-029-C2."
    },
    {
      "id": "SHR-029-C2",
      "pattern_class": "private-notion-workspace",
      "what": "The same URL, permanently readable in reachable git history. 56 distinct blobs across 14 file paths, carried by 224 of 243 reachable commits. Present at the tip of 21 of 29 refs, including origin/main and all three tags — so it is live in the published repository right now, independent of the current-tree cleanup, which sits on an unpushed branch.",
      "classification": "all-history removal",
      "still_live": true,
      "owner": "kanadhiayash",
      "approval": "NOT GRANTED. Requires written owner approval of this manifest version before any step of docs/security/HISTORY_REWRITE_RUNBOOK.md runs.",
      "evidence": {
        "refs": ["origin/main", "refs/tags/v1.1.0", "refs/tags/v1.1.1", "refs/tags/v2.0.0-alpha.1", "refs/stash", "+16 local branches"],
        "paths": [
          ".claude-plugin/plugin.json",
          "CHANGELOG.md",
          "GITHUB_OS.md",
          "README.md",
          "docs/RELEASE_LOG.md",
          "docs/wiki/Home.md",
          "docs/wiki/Installation.md",
          "docs/wiki/README.md",
          "docs/wiki/_Sidebar.md",
          "retired research resource",
          "scripts/shiroe-publish-releases.sh",
          "scripts/shiroe-publish-releases.sh",
          "wiki/projects/shiroe-v2-rebuild.md",
          "wiki/sources/shiroe-reference-links.md"
        ],
        "objects": 56,
        "first_commit": "c8205f2 (2026-05-12) — chore: Shiroe Agent OS v2.0.0 — description rewrites, references layer, registry, manifests",
        "last_commit": "a30aeda (2026-08-04) — fix(compat): isolate legacy identity behind a boundary",
        "verify": "bash scripts/scan-history-sensitive.sh | grep private-notion-workspace"
      },
      "blast_radius": "Every one of 243 commit SHAs changes. All three tags must be re-created and re-pushed. All 23 local branches and origin/main must be force-pushed. Every existing clone, fork, CI cache and open PR is invalidated and must be re-cloned — a fetch will not converge. GitHub retains the old objects and serves them by SHA until a support request purges cached views; PRs referencing old SHAs keep them readable. Any fork made before the rewrite keeps the URL permanently and is outside the owner's control. Cost is high and coverage is incomplete, which is precisely why the page-level mitigation below is the better first move.",
      "rotation": "REQUIRED AND CHEAPER THAN THE REWRITE. This is a Notion published-page URL, not a credential: if the page is web-shared, the unguessable id is the whole access control. Un-publishing or re-publishing the page invalidates every copy of the URL everywhere at once — including forks, caches and third-party clones a rewrite can never reach. Status: unknown; the page's visibility was not fetched, because probing a private URL from an audit is itself a disclosure. Owner action: check the page's share setting first, and decide whether the rewrite is still worth its cost afterwards."
    },
    {
      "id": "SHR-029-C3",
      "pattern_class": "private-notion-workspace",
      "what": "The same URL in two unreachable blobs — pre-cleanup drafts of GITHUB_OS.md (ccd7ccb, 3508 bytes) and CHANGELOG.md (d0ede32, 30241 bytes), left behind by amends or discarded index writes during PR 05's own cleanup. No commit references them. `git rev-list --all` cannot see them, so the PR 01 inventory did not either, and a filter-repo run that rebuilds from refs will not remove them from an existing clone.",
      "classification": "all-history removal",
      "still_live": true,
      "owner": "kanadhiayash",
      "approval": "NOT GRANTED. Same gate as SHR-029-C2; handled by the same runbook, but by its reflog-expire and gc --prune step rather than by filter-repo itself.",
      "evidence": {
        "refs": ["<none — unreachable>"],
        "paths": ["<unreachable blob ccd7ccb>", "<unreachable blob d0ede32>"],
        "objects": 2,
        "first_commit": "n/a — no commit references these blobs",
        "last_commit": "n/a — no commit references these blobs",
        "verify": "git fsck --unreachable --no-progress | awk '$2==\"blob\"{print $3}' | while read b; do git cat-file blob $b | grep -l 'notion[.]site' >/dev/null && echo $b; done"
      },
      "blast_radius": "Local to this clone. Removing them needs `git reflog expire --expire=now --all && git gc --prune=now`, which also discards every reflog entry — the undo history for the last 90 days of local work. That is the real cost, and it is why this is a separate candidate rather than a footnote on SHR-029-C2: the two need different commands and have different risks. These objects were almost certainly never pushed, so the remote is unaffected.",
      "rotation": "Covered by SHR-029-C2's page-level rotation, which supersedes object removal here as well."
    },
    {
      "id": "SHR-029-C4",
      "pattern_class": "home-rooted-absolute-path",
      "what": "Absolute paths rooted at the operator's macOS home directory (two real account-name segments, deliberately not spelled here) as they stood in the working tree. Zero remain: the SHR-022 tree guard re-verifies this on every run, and this manifest's own test re-checks the claim against the tree rather than trusting this sentence.",
      "classification": "current-tree cleanup",
      "still_live": false,
      "owner": "kanadhiayash",
      "evidence": {
        "refs": ["HEAD (security/shr-redaction-manifest)"],
        "paths": [
          "config/PROJECT.md",
          "references/shared-anti-hallucination.md"
        ],
        "objects": 0,
        "first_commit": "c8205f2 (2026-05-12)",
        "last_commit": "8cd8c47 (2026-07-10) — last commit whose tree carried one; removals landed across 23f3824, 15b83ec, 3050eed and earlier, NOT in PR 05 (see Corrections)",
        "verify": "git grep -n -E '/(Users|home)/[a-z]+/' HEAD -- ':!REDACT.md' ':!skills' ':!tests' ':!docs/security'  # exits 1"
      },
      "blast_radius": "None outstanding. Already done.",
      "rotation": "n/a — a filesystem path is not a credential and cannot be rotated. The disclosure is the operator's account name, which is also their public GitHub handle; see SHR-031-C12."
    },
    {
      "id": "SHR-029-C5",
      "pattern_class": "home-rooted-absolute-path",
      "what": "The same operator home paths in reachable history: 11 blobs across 8 file paths. Discloses the operator's local account name and directory layout. Materially the same class of disclosure as the commit author identity (SHR-031-C12), which is public and preserved deliberately — which is the argument for classifying this one as low-value to remove on its own.",
      "classification": "all-history removal",
      "still_live": true,
      "owner": "kanadhiayash",
      "approval": "NOT GRANTED. Bundle with SHR-029-C2 if a rewrite is approved at all; the marginal cost of adding these expressions to the same filter-repo run is zero, and the cost of a second rewrite later is another full force-push cycle.",
      "evidence": {
        "refs": ["origin/main", "refs/tags/v1.1.0", "refs/tags/v1.1.1", "+local branches"],
        "paths": [
          "config/PROJECT.md",
          "docs/06_Workflow_Examples.md",
          "memory/MEMORY.md",
          "references/shared-anti-hallucination.md",
          "tests/sandbox/canonical-handoff/adversarial.md",
          "tests/security-audit-v2.6-C.md",
          "wiki/index.md",
          "wiki/projects/shiroe-v2-rebuild.md"
        ],
        "objects": 11,
        "first_commit": "c8205f2 (2026-05-12) — earliest blob carrying a real home segment",
        "last_commit": "8cd8c47 (2026-07-10) — Dev (#69)",
        "verify": "bash scripts/scan-history-sensitive.sh | grep home-rooted-absolute-path"
      },
      "blast_radius": "Identical to SHR-029-C2 — the same rewrite, the same force push, the same re-clone — because it is the same rewrite. On its own it does not justify one.",
      "rotation": "n/a — not rotatable. The information is the operator's account name, already public via commit authorship."
    },
    {
      "id": "SHR-029-C6",
      "pattern_class": "operator-working-copy-path",
      "what": "Working-copy paths of the `~/Desktop` and `~/Documents` shape with a project directory beneath them. Zero occurrences in any of the 2944 blobs — the class is clean and has always been clean. It is listed because a scanner that reports nothing is only trustworthy if you can see it looked.",
      "classification": "current-tree cleanup",
      "still_live": false,
      "owner": "kanadhiayash",
      "evidence": {
        "refs": ["all 29"],
        "paths": [],
        "objects": 0,
        "first_commit": "n/a — no matching object in 2944 blobs",
        "last_commit": "n/a — no matching object in 2944 blobs",
        "verify": "bash scripts/scan-history-sensitive.sh | grep operator-working-copy-path  # blobs=0 paths=0"
      },
      "blast_radius": "None. Nothing to remove. The SHR-022 guard holds the line going forward.",
      "rotation": "n/a."
    },
    {
      "id": "SHR-029-C7",
      "pattern_class": "personal-cloud-sync-path",
      "what": "One unreachable blob (8779829) holding an earlier draft of tests/test_no_private_operational_references.py, from before that file learned to bracket its own literals. It spells the macOS iCloud container name as a pattern literal in a comment (written here as com[~]apple[~]CloudDocs, the same bracketing the current guard uses on itself). It is the name of a shape the guard hunts for, not a location anyone syncs anything to.",
      "classification": "preserved historical lineage",
      "still_live": true,
      "owner": "kanadhiayash",
      "evidence": {
        "refs": ["<none — unreachable>"],
        "paths": ["<unreachable blob 8779829>"],
        "objects": 1,
        "first_commit": "n/a — no commit references this blob",
        "last_commit": "n/a — no commit references this blob",
        "verify": "git cat-file blob 8779829c19b8a748e0a8074fd99b1530e1da44ea | grep -n CloudDocs"
      },
      "blast_radius": "n/a — kept deliberately. Removing it would mean expiring reflogs and pruning the object store to delete a comment that documents a detection pattern. The current tracked version of the same file brackets the literal precisely so it does not match itself; this draft is that lesson's fossil.",
      "rotation": "n/a — no operator location is disclosed. This is a pattern name."
    },
    {
      "id": "SHR-031-C8",
      "pattern_class": "aws-access-key-id",
      "what": "AWS access key IDs. Zero across all 2944 blobs at full shape (AKIA + 16 uppercase alphanumerics). PR 01's 2440 substring hits were the bare word AKIA in redaction documentation and CI regexes, deliberately-fake test fixtures assembled as `_AKIA = \"A\" + \"KIA\"`, and base64 image payload bytes inside assets/*.svg. The word stays; no key was ever committed.",
      "classification": "preserved historical lineage",
      "still_live": false,
      "owner": "kanadhiayash",
      "evidence": {
        "refs": ["all 29"],
        "paths": [],
        "objects": 0,
        "first_commit": "n/a — no matching object in 2944 blobs",
        "last_commit": "n/a — no matching object in 2944 blobs",
        "verify": "bash scripts/scan-history-sensitive.sh | grep aws-access-key-id  # blobs=0 paths=0"
      },
      "blast_radius": "None. Nothing to remove.",
      "rotation": "Not required — no key exists to rotate. This is a positive finding, re-derived by a stricter method than PR 01's, and it agrees with PR 01."
    },
    {
      "id": "SHR-031-C9",
      "pattern_class": "github-token",
      "what": "GitHub personal access tokens. Zero across all 2944 blobs at full shape (gh[pousr]_ + 36 characters). PR 01's 1379 substring hits were pattern documentation in CHANGELOG.md and the CI redaction regexes, plus fixtures too short to be a token.",
      "classification": "preserved historical lineage",
      "still_live": false,
      "owner": "kanadhiayash",
      "evidence": {
        "refs": ["all 29"],
        "paths": [],
        "objects": 0,
        "first_commit": "n/a — no matching object in 2944 blobs",
        "last_commit": "n/a — no matching object in 2944 blobs",
        "verify": "bash scripts/scan-history-sensitive.sh | grep github-token  # blobs=0 paths=0"
      },
      "blast_radius": "None. Nothing to remove.",
      "rotation": "Not required — no token exists to rotate."
    },
    {
      "id": "SHR-031-C10",
      "pattern_class": "provider-api-key",
      "what": "Provider API keys of the sk- / sk-ant- shape. 8 blobs across 3 paths, and none is a key. tests/test_vnext_pr2_storage.py carries the fixture `sk-live-1234567890abcdef` used to prove the redaction pipeline catches it; docs/canon/GITHUB_SURFACE_INVENTORY.md quotes that same fixture while triaging it; references/target-model-profiles/gpt-5-5-instant.md line 33 reads `never-ask-what-context-answers`, whose tail happens to match. PR 01's 4375 hits were ordinary words containing `sk-` — task-, risk-, desk-, disk-.",
      "classification": "preserved historical lineage",
      "still_live": true,
      "owner": "kanadhiayash",
      "evidence": {
        "refs": ["all 29"],
        "paths": [
          "tests/test_vnext_pr2_storage.py",
          "docs/canon/GITHUB_SURFACE_INVENTORY.md",
          "references/target-model-profiles/gpt-5-5-instant.md"
        ],
        "objects": 8,
        "first_commit": "present in the current tree; carried forward from the vNext PR 2 storage tests",
        "last_commit": "74da95a — still present at HEAD, deliberately",
        "verify": "bash scripts/scan-history-sensitive.sh | grep -A4 'provider-api-key'"
      },
      "blast_radius": "n/a — kept deliberately. Deleting the fixture would delete the test that proves provider keys get redacted, which is a net loss of security, not a gain. The English false positive is a phrase in a prose document.",
      "rotation": "Not required — no key exists to rotate."
    },
    {
      "id": "SHR-031-C11",
      "pattern_class": "pem-private-key",
      "what": "PEM private-key headers. 4 blobs across 2 paths. tests/test_privacy_redaction.py carries `-----BEGIN RSA PRIVATE KEY-----\\nMIIEpAIBAAKCAQEA\\n-----END RSA PRIVATE KEY-----` — a header, a 16-character stub, and a footer, with no key material between them — to test PEM redaction. docs/canon/GITHUB_SURFACE_INVENTORY.md quotes it while triaging it. PR 01's 186 hits were that one fixture, re-counted once per commit that touched the file.",
      "classification": "preserved historical lineage",
      "still_live": true,
      "owner": "kanadhiayash",
      "evidence": {
        "refs": ["all 29"],
        "paths": [
          "tests/test_privacy_redaction.py",
          "docs/canon/GITHUB_SURFACE_INVENTORY.md"
        ],
        "objects": 4,
        "first_commit": "carried from the privacy-redaction test suite's introduction",
        "last_commit": "74da95a — still present at HEAD, deliberately",
        "verify": "git grep -n 'BEGIN RSA PRIVATE KEY' HEAD -- tests/"
      },
      "blast_radius": "n/a — kept deliberately. The fixture is a PEM header with no key bytes; removing it removes the test that proves PEM blocks get redacted.",
      "rotation": "Not required — there is no key. The fixture's body is a 16-character base64 stub, not a decodable RSA key."
    },
    {
      "id": "SHR-031-C12",
      "pattern_class": "commit-author-identity",
      "what": "A personal email address in the author and committer fields of every commit. Three non-noreply identities appear: two spellings of the maintainer's name against one personal Gmail address, plus GitHub's web-flow signing identity. This is the maintainer's own published identity on a public repository, and it is what makes authorship attributable.",
      "classification": "preserved historical lineage",
      "still_live": true,
      "owner": "kanadhiayash",
      "evidence": {
        "refs": ["all 29"],
        "paths": ["<commit object metadata — not a blob>"],
        "objects": 243,
        "first_commit": "c8205f2 (2026-05-12) — the repository's first commit",
        "last_commit": "74da95a — every commit carries it",
        "verify": "git log --all --format='%an <%ae>' | sort -u"
      },
      "blast_radius": "Rewriting author identity changes every SHA — the same force-push and re-clone cost as SHR-029-C2 — and it would also break the link between these commits and the maintainer's GitHub account, since GitHub attributes commits by author email. It would make the history less accountable, not more private.",
      "rotation": "Available but not recommended here: GitHub offers a noreply alias, and 25% of this history already uses one. Switching future commits to it is a zero-cost forward change the owner may want independently. Rewriting past commits to it is not proposed."
    }
  ]
}
```

---

## What the owner is being asked to decide

1. **Check the Notion page's share setting.** If it is web-shared, un-publish or
   re-publish it. This is the highest-value action in this document, it costs
   nothing, and it reaches copies no rewrite can.
2. **Then** decide whether `SHR-029-C2`, `SHR-029-C3` and `SHR-029-C5` are still
   worth a history rewrite, knowing it changes 243 SHAs, invalidates every clone
   and fork, and does not reach GitHub's cached views without a separate support
   request. If yes, approve a specific version of this file in writing and hand
   `docs/security/HISTORY_REWRITE_RUNBOOK.md` to whoever executes it.
3. Note that the current-tree cleanup is on an unpushed branch. Until it is
   merged and pushed, `origin/main` still serves the URL from its tip.

Nothing above has been done. This PR wrote a document, a runbook, a scanner and
a test, and rewrote nothing.
