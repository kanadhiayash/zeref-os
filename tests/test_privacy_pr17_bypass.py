"""
PR17 · Secret-scanning bypass fixtures — SHR-068, SHR-069, SHR-070, SHR-071,
SHR-073.

Each of the five hardening classes gets ONE runnable check that fails if the
bypass path is left open. Fixtures are generated at runtime and every
credential-shaped string is assembled from split fragments — this file never
carries a full credential-shaped literal on disk.

Scanner surface under test: `shiroe.privacy.audit(strict=True)` — the
canonical entry point invoked by `shiroe audit-privacy --strict --fail-classes
credentials` and by the release gate.
"""

from __future__ import annotations

import base64
import io
import subprocess
import tarfile
import zipfile
from pathlib import Path

import pytest

from shiroe.privacy import (
    _ARCHIVE_MAX_DEPTH,
    audit,
    scrub,
)


# ---------------------------------------------------------------------------
# Concatenated fragments — never a full credential-shaped literal on disk.
# ---------------------------------------------------------------------------
_AKIA = "AKIA" + "IOSFODNN7EXAMPLE"  # AWS docs public example key
_SK = "s" + "k"


def _sk_proj(body: str) -> str:
    return _SK + "-proj-" + body


def _redact_md(dst: Path) -> Path:
    """Minimal REDACT.md that keeps credentials + email classes enabled."""
    dst.write_text(
        "---\n"
        "classes:\n"
        "  credentials:\n"
        "    enabled: true\n"
        "  email:\n"
        "    enabled: true\n"
        "    replacement: '[PII:email]'\n"
        "---\n"
        "# REDACT.md test fixture\n",
        encoding="utf-8",
    )
    return dst


def _init_repo(root: Path) -> None:
    """git-init the tree and commit REDACT.md + a benign carrier file."""
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "init"],
        cwd=root, check=True,
        env={"GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
             "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
             "PATH": "/usr/bin:/bin"},
    )


# ---------------------------------------------------------------------------
# SHR-068 · Credential — a real-looking API key must trigger a blocking hit.
# ---------------------------------------------------------------------------
def test_shr_068_credential_fixture_is_blocking(tmp_path: Path) -> None:
    redact = _redact_md(tmp_path / "REDACT.md")
    (tmp_path / "leak.md").write_text(
        f"deploy note: AWS_ACCESS_KEY_ID={_AKIA}\n", encoding="utf-8",
    )
    _init_repo(tmp_path)

    result = audit(directory=tmp_path, redact_md_path=redact, strict=True)

    assert result["hits_by_class"].get("credentials", 0) >= 1, result
    assert result["credential_files"], (
        "credential_files must be populated for zero-tolerance gate"
    )
    offender = next(iter(result["credential_files"]))
    assert offender.endswith("leak.md"), offender


# ---------------------------------------------------------------------------
# SHR-069 · Unicode — homoglyph, zero-width, and bidi override bypasses.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "label,payload",
    [
        # Cyrillic 'А' (U+0410) impersonating ASCII 'A' at the AKIA prefix.
        ("homoglyph_cyrillic", "АKIA" + "IOSFODNN7EXAMPLE"),
        # Zero-width space inserted mid-token to break \b boundaries.
        ("zero_width_split", "AKIA​IOSFODNN7EXAMPLE"),
        # Right-to-left override wrapped around the body.
        ("bidi_override", "‮AKIAIOSFODNN7EXAMPLE‬"),
    ],
)
def test_shr_069_unicode_bypass_is_blocked(label: str, payload: str) -> None:
    out, report = scrub(f"key: {payload}")
    assert "credentials" in report.classes_hit, f"[{label}] {report.classes_hit}"
    assert _AKIA not in out, f"[{label}] plain body survived: {out!r}"


# ---------------------------------------------------------------------------
# SHR-070 · Encoding — base64 / base32 / hex carriers must be blocked.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "label,encoder",
    [
        ("base64",
         lambda s: base64.b64encode(s.encode()).decode("ascii")),
        ("base64_urlsafe",
         lambda s: base64.urlsafe_b64encode(s.encode()).decode("ascii")),
        ("base32",
         lambda s: base64.b32encode(s.encode()).decode("ascii")),
        ("hex",
         lambda s: s.encode().hex()),
    ],
)
def test_shr_070_encoded_bypass_is_blocked(label: str, encoder) -> None:
    body = _sk_proj("AbCdEfGhIjKlMnOpQrStUv1234")
    blob = encoder(body)
    out, report = scrub(f"embedded {blob} end")
    assert "credentials" in report.classes_hit, f"[{label}] {report.classes_hit}"
    # Blob itself is what got redacted; decoded plaintext must never appear.
    assert body not in out, f"[{label}] decoded body survived: {out!r}"


# ---------------------------------------------------------------------------
# SHR-071 · Nested archive — secret buried inside zip-in-zip is caught up to
# the declared depth ceiling; deeper nesting emits a visible warning.
# ---------------------------------------------------------------------------
def _make_zip_bytes(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return buf.getvalue()


def _make_targz_bytes(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for name, data in members.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def test_shr_071_secret_at_max_depth_is_blocking(tmp_path: Path) -> None:
    """A secret at depth == _ARCHIVE_MAX_DEPTH (3) must be found."""
    assert _ARCHIVE_MAX_DEPTH == 3, "ceiling changed — update fixture"
    secret_text = f"aws creds: AWS_ACCESS_KEY_ID={_AKIA}\n".encode()
    # depth 3: outer.zip -> inner1.zip -> inner2.zip -> leak.md
    inner2 = _make_zip_bytes({"leak.md": secret_text})
    inner1 = _make_zip_bytes({"inner2.zip": inner2})
    outer = _make_zip_bytes({"inner1.zip": inner1})
    redact = _redact_md(tmp_path / "REDACT.md")
    (tmp_path / "bundle.zip").write_bytes(outer)
    _init_repo(tmp_path)

    result = audit(directory=tmp_path, redact_md_path=redact, strict=True)
    assert result["hits_by_class"].get("credentials", 0) >= 1, result
    offender = next(iter(result["credential_files"]))
    assert offender.endswith("bundle.zip"), offender
    assert not result["archive_depth_exceeded"], (
        "depth 3 must be reachable, not report exceeded"
    )


def test_shr_071_beyond_ceiling_emits_warning_not_silent_pass(
    tmp_path: Path,
) -> None:
    """Depth 4 must NOT silently pass; scanner reports the depth-exceeded warning."""
    secret_text = f"aws creds: AWS_ACCESS_KEY_ID={_AKIA}\n".encode()
    # depth 4: outer -> d1 -> d2 -> d3 -> leak.md
    d3 = _make_zip_bytes({"leak.md": secret_text})
    d2 = _make_zip_bytes({"d3.zip": d3})
    d1 = _make_zip_bytes({"d2.zip": d2})
    outer = _make_zip_bytes({"d1.zip": d1})
    redact = _redact_md(tmp_path / "REDACT.md")
    (tmp_path / "bundle.zip").write_bytes(outer)
    _init_repo(tmp_path)

    result = audit(directory=tmp_path, redact_md_path=redact, strict=True)
    # The buried leak is beyond the ceiling. The warning field must fire AND
    # a synthetic credentials-class hit must be stamped so the
    # `--fail-classes credentials` gate and the release-check both refuse —
    # silently accepting depth > 3 would be the bypass this test exists for.
    assert result["archive_depth_exceeded"], (
        "depth-4 archive must surface archive_depth_exceeded warning"
    )
    assert any(p.endswith("bundle.zip") for p in result["archive_depth_exceeded"])
    assert result["hits_by_class"].get("credentials", 0) >= 1, (
        f"depth-exceeded must stamp a credentials hit for the release gate: {result}"
    )
    assert any(p.endswith("bundle.zip") for p in result["credential_files"])


def test_shr_071_malformed_archive_is_blocking(tmp_path: Path) -> None:
    """A wrapper that pretends to be a zip but isn't parseable must fail closed."""
    redact = _redact_md(tmp_path / "REDACT.md")
    (tmp_path / "bogus.zip").write_bytes(b"PK\x03\x04not-a-real-zip-body\x00\x00truncated")
    _init_repo(tmp_path)
    result = audit(directory=tmp_path, redact_md_path=redact, strict=True)
    assert result["archive_malformed"], (
        f"malformed archive must be surfaced, not swallowed: {result}"
    )
    assert result["hits_by_class"].get("credentials", 0) >= 1, (
        "malformed archive must stamp a credentials hit for the release gate"
    )


def test_shr_071_zip_bomb_member_flood_is_blocking(tmp_path: Path) -> None:
    """Many small members that overflow the total-bytes/member-count cap must
    fail closed (marked malformed) — a 4097-member zip cannot silently pass."""
    from shiroe.privacy import _ARCHIVE_MAX_MEMBERS
    members = {f"file_{i}.md": b"a" for i in range(_ARCHIVE_MAX_MEMBERS + 1)}
    redact = _redact_md(tmp_path / "REDACT.md")
    (tmp_path / "flood.zip").write_bytes(_make_zip_bytes(members))
    _init_repo(tmp_path)
    result = audit(directory=tmp_path, redact_md_path=redact, strict=True)
    assert result["archive_malformed"], (
        f"member-count flood must be surfaced as malformed: {result}"
    )
    assert result["hits_by_class"].get("credentials", 0) >= 1


def test_shr_071_targz_carrier_is_also_covered(tmp_path: Path) -> None:
    """`.tar.gz` gets the same treatment as `.zip` — no format-based bypass."""
    secret_text = f"key = {_sk_proj('AbCdEfGhIjKlMnOpQrStUvWx1234')}\n".encode()
    inner = _make_targz_bytes({"leak.md": secret_text})
    outer = _make_targz_bytes({"inner.tar.gz": inner})
    redact = _redact_md(tmp_path / "REDACT.md")
    (tmp_path / "bundle.tar.gz").write_bytes(outer)
    _init_repo(tmp_path)

    result = audit(directory=tmp_path, redact_md_path=redact, strict=True)
    assert result["hits_by_class"].get("credentials", 0) >= 1, result
    offender = next(iter(result["credential_files"]))
    assert offender.endswith("bundle.tar.gz"), offender


# ---------------------------------------------------------------------------
# SHR-073 · Changed allowlist — modifying REDACT.md in the same run FAILS.
# ---------------------------------------------------------------------------
def test_shr_073_dirty_allowlist_fails_the_scan(tmp_path: Path) -> None:
    redact = _redact_md(tmp_path / "REDACT.md")
    (tmp_path / "clean.md").write_text("just a note\n", encoding="utf-8")
    _init_repo(tmp_path)

    # Baseline: clean tree, allowlist unmodified -> zero credentials hits.
    baseline = audit(directory=tmp_path, redact_md_path=redact, strict=True)
    assert baseline["hits_by_class"].get("credentials", 0) == 0, baseline
    assert baseline["allowlist_changed"] is False

    # Modify REDACT.md in place — mimicking a widening of the classifier
    # in the same commit as the audit run. This must trip the gate even
    # though the tree still contains no secret material.
    redact.write_text(
        redact.read_text(encoding="utf-8") + "\n# widened by attacker\n",
        encoding="utf-8",
    )
    dirty = audit(directory=tmp_path, redact_md_path=redact, strict=True)
    assert dirty["allowlist_changed"] is True, dirty
    assert dirty["hits_by_class"].get("credentials", 0) >= 1, dirty
    assert str(redact) in dirty["credential_files"], dirty["credential_files"]
