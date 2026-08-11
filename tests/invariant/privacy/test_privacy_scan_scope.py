"""Scan-scope regression tests for `shiroe.privacy.audit`.

The release gate treats any credentials-class hit as a hard failure, so the
set of files the scan walks is security-relevant in both directions:

* Too wide, and the gate fails on material that is never published — a local
  virtualenv's dependency source, an agent worktree holding a second copy of
  the repo, or an untracked audit note that quotes a credential shape on
  purpose. That blocks releases without protecting anything.
* Too narrow, and a real secret committed to a tracked file slips through.

These tests pin both edges.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from shiroe.privacy import _tracked_files, audit


# Assembled at runtime so the literal never exists in the source file and
# cannot trip secret scanning on push. Mirrors the `_fx` helper convention
# used in tests/test_privacy_redaction.py.
def _fx() -> str:
    return "sk-" + "proj-" + ("A" * 24)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   capture_output=True)


def _init_repo(path: Path) -> None:
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Test")


def test_tracked_files_returns_none_outside_git(tmp_path: Path) -> None:
    """Non-git directories fall back to scanning everything."""
    (tmp_path / "note.md").write_text("plain text")
    assert _tracked_files(tmp_path) is None


def test_untracked_file_is_not_scanned(tmp_path: Path) -> None:
    """An untracked file cannot be published, so it must not fail the gate."""
    _init_repo(tmp_path)
    (tmp_path / "tracked.md").write_text("nothing sensitive here")
    _git(tmp_path, "add", "tracked.md")
    _git(tmp_path, "commit", "-qm", "seed")

    # Untracked, and deliberately credential-shaped — e.g. a local audit note.
    (tmp_path / "untracked.md").write_text(f"example token: {_fx()}\n")

    result = audit(tmp_path, strict=True)
    assert result["credential_files"] == {}, (
        "untracked files must not contribute credentials-class hits"
    )


def test_tracked_file_is_still_scanned(tmp_path: Path) -> None:
    """The narrowing must not blind the gate to committed secrets."""
    _init_repo(tmp_path)
    (tmp_path / "leaked.md").write_text(f"token: {_fx()}\n")
    _git(tmp_path, "add", "leaked.md")
    _git(tmp_path, "commit", "-qm", "seed")

    result = audit(tmp_path, strict=True)
    assert result["credential_files"], (
        "a tracked file carrying a credential shape must still be flagged"
    )


def test_dependency_and_worktree_trees_are_skipped(tmp_path: Path) -> None:
    """Third-party and generated trees are excluded even when tracked.

    A committed vendored dependency or an agent worktree copy would otherwise
    fail the gate on someone else's example strings.
    """
    _init_repo(tmp_path)
    for rel in (".venv/lib/site-packages/dep.py",
                ".claude/worktrees/copy/thing.py"):
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f'EXAMPLE = "{_fx()}"\n')
    _git(tmp_path, "add", "-A", "-f")
    _git(tmp_path, "commit", "-qm", "seed")

    result = audit(tmp_path, strict=True)
    assert result["credential_files"] == {}


def test_skip_rules_match_path_components_not_substrings(tmp_path: Path) -> None:
    """A filename that merely CONTAINS a skip token is still scanned.

    The skip list names directories (`docs/`, `tests/`, `dist/`) and a few
    exact paths. Matching those as substrings of the joined relative path
    silently exempted any file whose own name embedded a skip token, so a
    tracked file called `notdocs.md` or `distribution.md` could carry a
    credential past the release gate purely because of what it was named.
    """
    decoys = ["notdocs.md", "distribution.md", "team-notes.md", "buildlog.md"]
    for name in decoys:
        (tmp_path / name).write_text(f"token {_fx()}\n")

    results = audit(directory=tmp_path, redact_md_path=Path("REDACT.md"), strict=True)

    scanned_names = {Path(p).name for p in results["by_file"]}
    assert scanned_names == set(decoys), (
        f"files exempted by substring match: {set(decoys) - scanned_names}"
    )
    assert results["hits_by_class"].get("credentials", 0) >= len(decoys)
    assert len(results["credential_files"]) == len(decoys)


def test_real_skip_directories_are_still_skipped(tmp_path: Path) -> None:
    """Component matching must not weaken the intended directory skips."""
    for rel in ("docs/note.md", "tests/fx.md", "dist/pkg.md", "proj.egg-info/meta.md"):
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"token {_fx()}\n")
    # Exact-path skips.
    (tmp_path / "CHANGELOG.md").write_text(f"token {_fx()}\n")

    results = audit(directory=tmp_path, redact_md_path=Path("REDACT.md"), strict=True)

    assert results["by_file"] == {}
    assert results["credential_files"] == {}
