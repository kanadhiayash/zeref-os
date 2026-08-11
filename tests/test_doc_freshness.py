"""
Documentation freshness guard.

Two checks, both driven off the repo's actual state so they stay correct
across version bumps and future operator-record splits:

1. Live public surfaces (README badge, docs/wiki/Installation.md) name the
   version that `shiroe/VERSION` declares, and don't advertise some *other*
   `vX.Y.Z`-shaped version as the product's current release.
2. No operator-record files are tracked back under docs/. Operator records
   are maintained outside this repository (see docs/audits/README.md), so
   this guard matches them by *shape* rather than by an enumerated roster:
   anything under a release-evidence directory, anything under docs/audits/
   besides the pointer stub, and any date-stamped artifact filename (the
   operator-record naming grammar carries an ISO date; published doc
   surfaces do not).
   Only git-tracked files count: shiroe/release/checks.py legitimately
   writes local evidence blobs under docs/audits/release-evidence/ at
   runtime, and .gitignore keeps them out of the public tree.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

VERSION_RE = re.compile(r"\bv(\d+\.\d+\.\d+(?:-[0-9A-Za-z.]+)?)\b")

# Files that live in docs/wiki/Installation.md-style "live" public surfaces
# and are expected to mention the current version.
LIVE_VERSION_SURFACES = ("README.md", "docs/wiki/Installation.md")

# Structural signatures of an operator record. Deliberately shape-based, not
# a roster of artifact names: the guard must keep working for records this
# repo has never seen, and naming them here would republish what the split
# was meant to remove.
#
# 1. Evidence dumps live in a release-evidence directory at any depth.
# 2. docs/audits/ is a pointer stub only — see AUDITS_STUB.
# 3. Operator records are date-stamped per the artifact naming grammar
#    (`..._<state>_<owner>_<yyyy-mm-dd>_v<major.minor>`); published doc
#    surfaces are versionless and carry no date in the filename.
EVIDENCE_DIR_SEGMENT = "release-evidence"
AUDITS_DIR = "docs/audits/"
AUDITS_STUB = "docs/audits/README.md"
DATE_STAMPED_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _current_version(repo_root: Path) -> str:
    version_file = repo_root / "shiroe" / "VERSION"
    assert version_file.exists(), "shiroe/VERSION is missing"
    return version_file.read_text(encoding="utf-8").strip()


def _tracked_docs_files(repo_root: Path) -> list[str]:
    r = subprocess.run(
        ["git", "ls-files", "--", "docs/"],
        capture_output=True, text=True, cwd=str(repo_root), check=True,
    )
    return [line for line in r.stdout.splitlines() if line]


def test_live_surfaces_mention_current_version_and_no_other(repo_root: Path) -> None:
    current = _current_version(repo_root)

    for rel in LIVE_VERSION_SURFACES:
        path = repo_root / rel
        assert path.exists(), f"expected live doc surface missing: {rel}"
        text = path.read_text(encoding="utf-8", errors="ignore")

        found = {m.group(1) for m in VERSION_RE.finditer(text)}
        assert current in found, (
            f"{rel} does not mention the current version v{current} "
            f"(shiroe/VERSION). Found version strings: {sorted(found) or 'none'}"
        )

        stale = found - {current}
        assert not stale, (
            f"{rel} advertises other version string(s) as current: "
            f"{sorted(stale)}. Only v{current} (from shiroe/VERSION) should "
            "appear as a current-release claim; historical version mentions "
            "belong in CHANGELOG.md, not live surfaces."
        )


def test_no_operator_records_tracked_under_docs(repo_root: Path) -> None:
    tracked = _tracked_docs_files(repo_root)
    assert tracked, "docs/ has no tracked files — unexpected"

    hits: list[str] = []
    for rel in tracked:
        if rel.startswith("docs/superpowers/"):
            continue
        parts = Path(rel).parts
        if EVIDENCE_DIR_SEGMENT in parts:
            hits.append(rel)
        elif rel.startswith(AUDITS_DIR) and rel != AUDITS_STUB:
            hits.append(rel)
        elif DATE_STAMPED_RE.search(Path(rel).name):
            hits.append(rel)

    assert not hits, (
        "operator-record-shaped file(s) tracked under docs/: "
        f"{sorted(hits)}. Operator records are maintained outside this "
        "repository and must not re-enter the public tree."
    )


def test_audits_dir_tracks_only_the_stub_pointer(repo_root: Path) -> None:
    tracked = [
        rel for rel in _tracked_docs_files(repo_root)
        if rel.startswith("docs/audits/")
    ]
    assert tracked == [AUDITS_STUB], (
        "docs/audits/ should track only the pointer stub README.md; "
        f"tracked: {tracked}"
    )

    stub = (repo_root / "docs" / "audits" / "README.md").read_text(encoding="utf-8")
    assert "maintained outside this repository" in stub
