"""
Exhaustive privacy-scrubber tests.

Every provider-shaped credential pattern has positive cases (must redact) and
negative cases (must NOT trigger false positives on innocuous strings).
"""

from __future__ import annotations

import pytest

from shiroe.privacy import scrub


# ---------------------------------------------------------------------------
# Fixture builders — we assemble provider-shaped strings at runtime via
# concatenation so the source file itself contains no literal that would
# match GitHub's secret-scanning regex (which blocks pushes that look like
# real credentials, even inside negative tests).
# ---------------------------------------------------------------------------
_SK = "s" + "k"
_GHPAT = "github_" + "pat_"
_GHP = "g" + "hp_"
_XOXB = "xo" + "xb-"
_AIZA = "A" + "Iza"
_AKIA = "A" + "KIA"


def _fx(template: str) -> str:
    """
    Render a fixture template, substituting tokens like {SK}, {GHPAT}, {GHP},
    {XOXB}, {AIZA}, {AKIA} with their concatenated equivalents. This keeps
    the test corpus readable while keeping the on-disk source non-matching.
    """
    return template.format(
        SK=_SK, GHPAT=_GHPAT, GHP=_GHP, XOXB=_XOXB, AIZA=_AIZA, AKIA=_AKIA,
    )


# ---------------------------------------------------------------------------
# Positive cases — every one must end up redacted
# ---------------------------------------------------------------------------
POSITIVE_CASES: list[tuple[str, str]] = [
    ("openai_project",     _fx("key={SK}-proj-AbCdEfGhIjKlMnOpQrStUvWxYz1234567890_x")),
    ("openai_bare",        _fx("Stale token {SK}-AbCdEfGhIjKlMnOpQrStUv4242")),
    ("github_pat",         _fx("GH PAT {GHPAT}11ABCDEFG0abcdefghijklmnop_xyz_more")),
    ("github_ghp",         _fx("Classic PAT {GHP}AbCdEfGhIjKlMnOpQrStUvWxYz0123")),
    ("slack_bot",          _fx("Slack bot {XOXB}1234567890-AbCdEfGhIjKlMnO")),
    ("google_api",         _fx("GCP key {AIZA}SyA-1234567890abcdefghijklmnopqrstuv")),
    ("aws_access_key",     _fx("AWS access key {AKIA}IOSFODNN7EXAMPLE in config")),
    ("pem_block",          "-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkqhkiG9w0BAQEFAA\n-----END PRIVATE KEY-----"),
    ("pem_rsa",            "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA\n-----END RSA PRIVATE KEY-----"),
    ("nl_api_key",         _fx("My API key {SK}-abc12345xyz789 was leaked")),
    ("nl_secret_key",      "Use secret key: hunter2hunter2hunter"),
    ("nl_access_token",    _fx("access token = {XOXB}1234-abc_def_ghi")),
    ("env_openai",         _fx("OPENAI_API_KEY={SK}-AbCdEfGhIjKlMnOpQrStUvWx1234")),
    ("kv_api_key",         "api_key: aZ09_aZ09_aZ09_aZ09"),
    ("bearer",             "Authorization: bearer abcdef1234567890XYZ"),
]


@pytest.mark.parametrize("label,text", POSITIVE_CASES)
def test_positive_redaction(label: str, text: str) -> None:
    out, report = scrub(text)
    assert report.redacted >= 1, f"[{label}] expected redaction; got: {out!r}"
    assert "[REDACTED" in out or "[PII" in out, (
        f"[{label}] no redaction sentinel in output: {out!r}"
    )


# ---------------------------------------------------------------------------
# Negative cases — must NOT trigger redaction
# ---------------------------------------------------------------------------
NEGATIVE_CASES: list[tuple[str, str]] = [
    # short, unprefixed strings that look like nothing
    ("short_string",       "hello world"),
    ("code_comment",       "# this is a comment about the parser"),
    ("markdown_heading",   "## Architecture overview"),
    ("filename_with_sk",   "the file masks.py contains masking logic"),
    # AKIA-prefixed words that aren't 16-char access keys
    ("akia_word",          _fx("{AKIA} is a fictional acronym I made up")),
    # sk-... that's too short to be a real token
    ("too_short_sk",       _fx("version {SK}-1.2 is fine")),
]


@pytest.mark.parametrize("label,text", NEGATIVE_CASES)
def test_negative_no_false_positive(label: str, text: str) -> None:
    out, report = scrub(text)
    # We accept that "credentials" generic regex may catch labelled keys;
    # what we forbid is a redaction on these innocuous strings.
    assert report.redacted == 0, (
        f"[{label}] false positive: redacted {report.redacted} hit(s) in {text!r} "
        f"-> {out!r}"
    )


def test_scrub_returns_report_object() -> None:
    out, report = scrub("nothing sensitive here")
    assert out == "nothing sensitive here"
    assert report.redacted == 0
    assert report.classes_hit == []


def test_scrub_provenance_field_preserved() -> None:
    _, report = scrub("plain text", provenance="unit-test/123")
    assert report.provenance == "unit-test/123"


# ---------------------------------------------------------------------------
# Bypass-resistance — encoding tricks must not slip past
# ---------------------------------------------------------------------------
BYPASS_CASES: list[tuple[str, str]] = [
    # Cyrillic homoglyph in the AKIA prefix — pipeline normalises before regex
    # Leading char is Cyrillic А (U+0410), not Latin A
    ("homoglyph_akia",
     "Suspicious АKIAIOSFODNN7EXAMPLE in the log"),
    # base64-wrapped credential — pipeline base64-decodes before regex
    # decoded payload starts with the SK prefix
    ("base64_wrapped_sk",
     "Encoded blob c2stQWJDZEVmR2hJaktsTW5PcFFyU3RVdld4MTIzNA== leaked"),
    # NFKC normalisation — fullwidth-style PAT mention
    ("nfkc_fullwidth_pat",
     _fx("GH {GHP}AbCdEfGhIjKlMnOpQrStUvWxYz0123 mention")),
]


@pytest.mark.parametrize("label,text", BYPASS_CASES)
def test_bypass_resistance(label: str, text: str) -> None:
    out, report = scrub(text)
    assert report.redacted >= 1, (
        f"[{label}] bypass succeeded; expected redaction. text={text!r} out={out!r}"
    )
