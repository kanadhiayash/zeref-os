from __future__ import annotations

import builtins
from pathlib import Path

import pytest

from shiroe.privacy import scrub


SENSITIVE_TEXT = "John Doe <john.doe@example.com> /Users/yash/private"


def _redact_md(path: Path, *, email_enabled: bool = True) -> Path:
    path.write_text(
        "---\n"
        "classes:\n"
        "  credentials:\n"
        "    enabled: true\n"
        "  pii:\n"
        "    enabled: true\n"
        "    replacement: '[PERSON]'\n"
        "  email:\n"
        f"    enabled: {'true' if email_enabled else 'false'}\n"
        "    replacement: '[EMAIL]'\n"
        "  internal_paths:\n"
        "    enabled: true\n"
        "    replacement: '[PATH]'\n"
        "---\n"
        "# REDACT.md test fixture\n",
        encoding="utf-8",
    )
    return path


def _without_yaml(monkeypatch: pytest.MonkeyPatch) -> None:
    real_import = builtins.__import__

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "yaml":
            raise ImportError("yaml intentionally unavailable for parity test")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)


def test_redaction_result_is_identical_without_optional_yaml(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redact = _redact_md(tmp_path / "REDACT.md")

    with_yaml, with_report = scrub(SENSITIVE_TEXT, redact)
    _without_yaml(monkeypatch)
    without_yaml, without_report = scrub(SENSITIVE_TEXT, redact)

    assert without_yaml == with_yaml
    assert without_report.classes_hit == with_report.classes_hit
    assert "John Doe" not in without_yaml
    assert "john.doe@example.com" not in without_yaml
    assert "/Users/yash/private" not in without_yaml


def test_enabled_false_and_custom_replacement_are_stdlib_deterministic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redact = _redact_md(tmp_path / "REDACT.md", email_enabled=False)

    with_yaml, with_report = scrub(SENSITIVE_TEXT, redact)
    _without_yaml(monkeypatch)
    without_yaml, without_report = scrub(SENSITIVE_TEXT, redact)

    assert without_yaml == with_yaml
    assert without_report.classes_hit == with_report.classes_hit
    assert "[PERSON]" in without_yaml
    assert "[PATH]" in without_yaml
    assert "[EMAIL]" not in without_yaml
    assert "john.doe@example.com" in without_yaml
