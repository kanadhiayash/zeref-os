"""
SHR-022 — no private operational references in the tracked tree.

A *private operational reference* is a string that names the maintainer's own
infrastructure rather than the product's: a private workspace URL, an absolute
path rooted in somebody's home directory, or a personal cloud-sync location.
None of them are secrets in the credential sense, so no secret scanner catches
them; they leak where the operator works, not what they know.

The matchers below are deliberately **shape-based**. A roster of today's known
hits would go green the moment it was written and stay green through the next
leak, which is the failure mode this guard exists to prevent. Each pattern
describes a *form*, so a file this repo has never seen is covered too.

Shape-based also means the guard has to survive the surfaces that legitimately
*document* these forms. `REDACT.md`, `skills/privacy-abstraction/SKILL.md`,
`tests/test_privacy_guard.py` and `tests/test_benchmark_suite.py` all spell
`/Users/` on purpose — they specify or test the redaction pipeline. They are
not exempted by name (an exemption roster is the same trap as a hit roster).
Instead the matcher encodes what actually distinguishes them:

* they use placeholder home segments (`<name>`, `x`, `example`), never a real
  account name — so the home-path matcher rejects placeholder-shaped segments;
* they name the `/Users/` prefix as a pattern, without a rooted path under it —
  so a bare `/Users/` with nothing addressable after it is not a finding.

Likewise a mention of a standard directory (`~/Documents`) or of a tool config
root (`~/.claude/skills`, `~/.shiroe/policies`) is not a leak: those name the
platform, not a person. What leaks is a *rooted* path — a personal directory
plus at least one segment of the operator's own content beneath it.

Nothing here is exempted, including this file. Every pattern is written so its
own source text cannot match it — bracketed literals such as `[.]notion[.]site`
and `com[~]apple[~]CloudDocs` describe the shape without spelling it — and the
synthetic-leak fixtures are assembled from fragments at runtime. If a comment
in this file ever spells a leak out, this guard fails on itself, which is the
correct outcome.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

# --------------------------------------------------------------------------- #
# Shapes
# --------------------------------------------------------------------------- #

# A Notion *workspace* subdomain. The bare product domain (`notion.so`,
# `www.notion.com`) is a public brand reference and appears legitimately in
# connector docs; a `<workspace>.notion.site` host is one specific private
# workspace's published surface.
PRIVATE_NOTION_HOST = re.compile(r"\b[A-Za-z0-9][A-Za-z0-9-]*[.]notion[.]site\b")

# An absolute home root naming an account: `/Users/<seg>/` or `/home/<seg>/`.
# The trailing slash matters — it is what separates "a path belonging to
# someone" from "the /Users/ prefix, named as a pattern".
HOME_ROOT = re.compile(r"/(?:Users|home)/(?P<seg>[^/\s\"'`,;:)\]}]+)/")

# Home-relative roots that are not spelled with an account name.
_HOME_PREFIX = r"(?:~|\$\{?HOME\}?|%(?:USERPROFILE|HOMEPATH)%|/(?:Users|home)/[^/\s]+)"

# Personal content directories. Deliberately excludes dot-directories: tool
# config roots (`~/.claude/`, `~/.shiroe/`, `~/.codex/`) are product surfaces
# this repo documents on purpose, not operator location leaks.
_PERSONAL_DIR = (
    r"(?:Desktop|Documents|Downloads|Movies|Music|Pictures|Public"
    r"|Dropbox|OneDrive|Sites|Applications)"
)

# A rooted operator path: personal directory *plus* content beneath it. A bare
# `~/Documents` names a platform directory and is allowed; the same root with a
# project name under it says where one person keeps one thing, and is not.
OPERATOR_PATH = re.compile(_HOME_PREFIX + r"/" + _PERSONAL_DIR + r"/[^\s/\"'`)\]}]+")

# Personal cloud-sync locations. The bracketed literals below keep this source
# from matching itself while still matching the real thing.
CLOUD_SYNC_PATH = re.compile(
    r"com[~]apple[~]CloudDocs"
    r"|Library/Mobile[ ]Documents"
    r"|iCloud[ ]Drive",
    re.IGNORECASE,
)

PATTERNS: dict[str, re.Pattern[str]] = {
    "private-notion-workspace": PRIVATE_NOTION_HOST,
    "home-rooted-absolute-path": HOME_ROOT,
    "operator-working-copy-path": OPERATOR_PATH,
    "personal-cloud-sync-path": CLOUD_SYNC_PATH,
}

# A home segment that stands for "whoever runs this", not for a person. Shapes,
# not names: bracketed/templated tokens, single-character stand-ins, and the
# handful of English words that mean "the user" in documentation.
PLACEHOLDER_SEGMENT = re.compile(
    r"""^(?:
          [<{\[(].*                     # <name>, {user}, [you], (username)
        | \$\{?\w+\}?                   # $USER, ${HOME}
        | %\w+%                         # %USERNAME%
        | \w                            # single-character stand-in: x, y, a
        | example|user|username|name|you|me|someone|somebody
        | youruser|yourname|placeholder|redacted|home|runner|root|ubuntu
      )$""",
    re.VERBOSE | re.IGNORECASE,
)

BINARY_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip", ".gz",
    ".tar", ".woff", ".woff2", ".ttf", ".otf", ".sqlite", ".db", ".mp4",
}


# --------------------------------------------------------------------------- #
# Scanner
# --------------------------------------------------------------------------- #

def _is_finding(rule: str, match: re.Match[str]) -> bool:
    """Second-stage filter for the shapes that need one."""
    if rule == "home-rooted-absolute-path":
        return not PLACEHOLDER_SEGMENT.match(match.group("seg"))
    return True


def scan_text(text: str) -> list[tuple[int, str, str]]:
    """Return (line number, rule, matched text) for every finding in `text`."""
    findings: list[tuple[int, str, str]] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        for rule, pattern in PATTERNS.items():
            for match in pattern.finditer(line):
                if _is_finding(rule, match):
                    findings.append((lineno, rule, match.group(0)))
    return findings


def _tracked_files(repo_root: Path) -> list[str]:
    r = subprocess.run(
        ["git", "ls-files"],
        capture_output=True, text=True, cwd=str(repo_root), check=True,
    )
    return [line for line in r.stdout.splitlines() if line]


def scan_tree(repo_root: Path) -> list[str]:
    """Scan every tracked text file. Returns `path:line: rule: match` strings."""
    hits: list[str] = []
    for rel in _tracked_files(repo_root):
        path = repo_root / rel
        if path.suffix.lower() in BINARY_SUFFIXES or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, rule, matched in scan_text(text):
            hits.append(f"{rel}:{lineno}: {rule}: {matched}")
    return hits


# --------------------------------------------------------------------------- #
# The guard
# --------------------------------------------------------------------------- #

def test_tracked_tree_has_no_private_operational_references(repo_root: Path) -> None:
    hits = scan_tree(repo_root)
    assert not hits, (
        "private operational reference(s) in the tracked tree:\n  "
        + "\n  ".join(hits)
        + "\n\nRemove the reference or, if the file must show the *form* of one, "
          "write it with a placeholder segment the way REDACT.md does."
    )


# --------------------------------------------------------------------------- #
# Proof the matcher actually catches things — synthetic leaks, assembled from
# fragments so this file carries none of them literally.
# --------------------------------------------------------------------------- #

SYNTHETIC_LEAKS = [
    # Fabricated host. Reassembling the real one would reintroduce the very
    # string this guard removes, as a fixture.
    ("private-notion-workspace", "Command center: https://" + "amber-lamp-104" + ".notion" + ".site/Some-Page-0123abcd"),
    ("home-rooted-absolute-path", "cd " + "/Users/" + "jdoe" + "/code/shiroe"),
    ("home-rooted-absolute-path", 'root = "' + "/home/" + "jdoe" + '/src/shiroe"'),
    ("operator-working-copy-path", 'REPO="$HOME' + "/Desktop/" + 'SHIROE/shiroe"'),
    ("operator-working-copy-path", "worktree at ~" + "/Documents/" + "shiroe-pr-05"),
    ("personal-cloud-sync-path", "synced via ~/Library/Mobile" + " " + "Documents/shiroe"),
    ("personal-cloud-sync-path", "stored in com" + "~apple~" + "CloudDocs/shiroe"),
]


@pytest.mark.parametrize("rule,leak", SYNTHETIC_LEAKS)
def test_matcher_catches_synthetic_leak(rule: str, leak: str) -> None:
    findings = scan_text(leak)
    assert findings, f"matcher missed a {rule} leak: {leak!r}"
    assert rule in {r for _, r, _ in findings}, (
        f"{leak!r} matched {sorted({r for _, r, _ in findings})}, expected {rule}"
    )


def test_injected_leak_fails_the_tree_scan(repo_root: Path, tmp_path: Path) -> None:
    """The tree scan is wired to the matcher — an injected file is caught."""
    victim = repo_root / "docs" / "GLOSSARY.md"
    original = victim.read_text(encoding="utf-8")
    leak = "\n\nOperator note: repo lives at $HOME" + "/Desktop/" + "SHIROE/shiroe\n"
    try:
        victim.write_text(original + leak, encoding="utf-8")
        hits = scan_tree(repo_root)
        assert any(h.startswith("docs/GLOSSARY.md:") for h in hits), (
            "tree scan did not see an injected leak in a tracked file"
        )
    finally:
        victim.write_text(original, encoding="utf-8")

    assert not any(h.startswith("docs/GLOSSARY.md:") for h in scan_tree(repo_root))


# --------------------------------------------------------------------------- #
# Proof the matcher does *not* fire on the surfaces that specify these forms.
# --------------------------------------------------------------------------- #

SPEC_SURFACES = [
    "REDACT.md",
    "tests/test_privacy_guard.py",
]


@pytest.mark.parametrize("rel", SPEC_SURFACES)
def test_redaction_spec_surfaces_are_not_false_positives(repo_root: Path, rel: str) -> None:
    path = repo_root / rel
    assert path.exists(), f"{rel} is missing — this test pins a real surface"
    findings = scan_text(path.read_text(encoding="utf-8"))
    assert not findings, (
        f"{rel} documents these patterns and must not be flagged; got {findings}"
    )
