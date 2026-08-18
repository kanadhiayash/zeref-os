"""
Wave 10 (3/3): email / PII / internal-path adversarial-bypass matrix.

Mirrors `tests/invariant/privacy/test_privacy_adversarial.py`'s credentials
matrix, but for the `email`, `pii`, and `internal_paths` REDACT.md classes.
Every fixture goes through the same entry point the credentials matrix uses:
`shiroe.privacy.scrub`.

What is and isn't "the same strictness as credentials" here is load-bearing,
so it is worth being explicit about the pipeline shape (see `scrub()`'s
docstring in `shiroe/privacy.py`):

  * Surfaces 1-2 (raw, then NFKC + homoglyph normalized) run for every class,
    including email/pii/internal_paths, because normalization happens once on
    `working` before Surface 5 runs the remaining classes. Unicode homoglyph
    substitution and fullwidth-character evasion are therefore caught for
    these classes too, and the first section below pins that.

  * Surfaces 3-4 (whitespace-collapsed scan, decoded-container probing) now
    cover email/pii/internal_paths at the same strictness as credentials.
    `_scan_encoded_surfaces` is class-parameterized (probing decoded blobs
    with each class's own pattern) and the per-class loop runs a
    whitespace-split scan (`_scan_whitespace_split_classes`) plus the encoded
    probe for each of `_EVASION_SCAN_CLASSES`. So a whitespace-split
    email/SSN/path, or a base64-encoded one, is caught rather than passed
    through -- pinned in the third section below. To avoid an unanchored
    pattern swallowing neighbouring prose under a full collapse, the class
    scan only collapses whitespace bordering a token's structural characters
    (`@`, `.`, `-`); ordinary word-separating spaces are left intact.
"""

from __future__ import annotations

import base64

import pytest

from shiroe.privacy import scrub


# ---------------------------------------------------------------------------
# Caught: evasions that survive raw + NFKC/homoglyph normalization, which
# email/pii/internal_paths DO receive (same as credentials Surfaces 1-2).
# ---------------------------------------------------------------------------
def _caught_cases() -> list[tuple[str, str, str, str]]:
    """Return (label, text, expected_class, must_not_survive) triples."""
    cyrillic_domain = "john.doe@ex\u0430mple.\u0441om"  # Cyrillic а (U+0430), с (U+0441)
    fullwidth_addr = "john\uFF0Edoe\uFF20example\uFF0Ecom"  # fullwidth . @ . -- NFKC folds these
    concatenated = "reach:john.doe@example.com|urgent"
    windows_path = r"C:\Users\jdoe\Documents\secret.txt"
    unix_path_deep = "/var/log/app/secret-2024.log"
    # Placeholder home segment ("runner") per REDACT.md/SHR-022: still matches the
    # internal_paths detector (/home/<seg>/...) but is not a real account name, so the
    # tracked-tree private-reference scanner accepts it.
    home_path = "/home/runner/.ssh/id_rsa"
    plain_name = "John Smith"
    cyrillic_name = "J\u043ehn Smith"  # Cyrillic о (U+043E)
    ssn = "123-45-6789"
    phone_dashes = "415-555-1234"
    phone_dots = "415.555.1234"
    return [
        ("email_plain", f"contact me at john.doe@example.com please", "email", "john.doe@example.com"),
        ("email_cyrillic_domain", f"contact me at {cyrillic_domain} please", "email", cyrillic_domain),
        ("email_fullwidth", f"contact me at {fullwidth_addr} please", "email", "example.com"),
        ("email_concatenated_no_boundary", concatenated, "email", "john.doe@example.com"),
        ("path_windows", f"see {windows_path} for details", "internal_paths", windows_path),
        ("path_unix_deep", f"log at {unix_path_deep} for details", "internal_paths", unix_path_deep),
        ("path_home_dotfile", f"backup lives at {home_path} copy", "internal_paths", home_path),
        ("pii_name_plain", f"please contact {plain_name} about the merger", "pii", plain_name),
        ("pii_name_cyrillic_homoglyph", f"please contact {cyrillic_name} about the merger", "pii", "Smith"),
        ("pii_ssn_plain", f"SSN on file: {ssn}", "pii", ssn),
        ("pii_phone_dashes", f"call {phone_dashes} today", "pii", phone_dashes),
        ("pii_phone_dots", f"call {phone_dots} today", "pii", phone_dots),
    ]


@pytest.mark.parametrize("label,text,expected_class,must_not_survive", _caught_cases())
def test_adversarial_redaction_email_pii_path(
    label: str, text: str, expected_class: str, must_not_survive: str
) -> None:
    out, report = scrub(text)
    assert report.redacted >= 1, f"[{label}] bypass: no redaction. out={out!r}"
    assert expected_class in report.classes_hit, f"[{label}] wrong class: {report.classes_hit}"
    assert must_not_survive not in out, f"[{label}] sensitive material survived: {out!r}"


# ---------------------------------------------------------------------------
# Precision negatives -- benign text must not trip email/pii/internal_paths.
# ---------------------------------------------------------------------------
PRECISION_NEGATIVES: list[tuple[str, str]] = [
    ("not_an_email_at_symbol", "meet @channel in the standup thread"),
    ("not_a_path_forward_slash_ratio", "the cost/benefit ratio improved this quarter"),
    ("not_a_name_sentence_case", "Benchmark Failure Analysis report attached"),
]


@pytest.mark.parametrize("label,text", PRECISION_NEGATIVES)
def test_precision_no_false_positive(label: str, text: str) -> None:
    out, report = scrub(text)
    assert report.redacted == 0, (
        f"[{label}] false positive: {report.redacted} hit(s) in {text!r} -> {out!r}"
    )


# ---------------------------------------------------------------------------
# Caught: whitespace-injection and base64 encoding no longer bypass
# email/pii/internal_paths redaction. The whitespace-collapsed surface and the
# encoded-blob probe (`_scan_whitespace_split_classes` / `_scan_encoded_
# surfaces` in `shiroe/privacy.py`) now cover these classes at the same
# strictness as credentials, per the program's privacy=100% requirement.
# ---------------------------------------------------------------------------
def _evasion_cases() -> list[tuple[str, str, str, str]]:
    """Return (label, text, expected_class, must_not_survive) triples."""
    b64_email = base64.b64encode(b"john.doe@example.com").decode("ascii")
    return [
        ("email_whitespace_split",
         "contact me at john.doe @ example . com please", "email", "john.doe"),
        ("email_base64_encoded",
         f"payload {b64_email} end", "email", b64_email),
        ("path_whitespace_split",
         "see /Users / jdoe / Documents / secret.txt for details",
         "internal_paths", "secret.txt"),
        ("ssn_whitespace_split",
         "SSN on file: 123 - 45 - 6789", "pii", "123 - 45 - 6789"),
    ]


@pytest.mark.parametrize("label,text,expected_class,must_not_survive", _evasion_cases())
def test_whitespace_and_base64_evasion_caught_email_pii_path(
    label: str, text: str, expected_class: str, must_not_survive: str
) -> None:
    out, report = scrub(text)
    assert report.redacted >= 1, f"[{label}] bypass: no redaction. out={out!r}"
    assert expected_class in report.classes_hit, f"[{label}] wrong class: {report.classes_hit}"
    assert must_not_survive not in out, f"[{label}] sensitive material survived: {out!r}"
