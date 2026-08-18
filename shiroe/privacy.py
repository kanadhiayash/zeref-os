"""
shiroe.privacy — Deterministic PII abstraction module (Sprint 2, hardened WS2).

Replaces prose-only privacy-abstraction skill with code-level enforcement.
Reads REDACT.md classes and applies a raw-first, decode-as-additive pipeline:

    1. raw surface          — credential patterns run on the UNTOUCHED input
                              before any normalization or decoding can mutate
                              a token body out from under the detectors.
    2. normalized surface   — NFKC + homoglyph fold, credentials re-scanned.
    3. whitespace surface   — anchored provider prefixes re-scanned with all
                              whitespace collapsed (catches tokens split by
                              spaces or newlines); matches map back to, and
                              redact, the original span.
    4. encoded surfaces     — base64/hex blobs are decoded into a validated
                              side container and PROBED for credentials; on a
                              hit the original encoded blob is redacted. The
                              decoded text is never substituted back into the
                              working string. Nested encodings are followed
                              to a bounded depth.
    5. class redaction      — remaining enabled REDACT.md classes (pii,
                              email, paths, ...) run on the normalized text.

Usage:
    from shiroe.privacy import scrub, audit

    clean, report = scrub("My name is John Doe, email: john@example.com")
    print(clean)   # "My name is [PII:pii], email: [PII:email]"
    print(report)  # ScrubReport(redacted=2, classes_hit=['pii', 'email'], ...)
"""

from __future__ import annotations

import base64
import binascii
import os
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Homoglyph table — common lookalike substitutions used to evade regex
# ---------------------------------------------------------------------------
_HOMOGLYPHS: dict[str, str] = {
    # lowercase Cyrillic
    "а": "a",   # Cyrillic а  U+0430
    "е": "e",   # Cyrillic е  U+0435
    "о": "o",   # Cyrillic о  U+043E
    "р": "p",   # Cyrillic р  U+0440
    "с": "c",   # Cyrillic с  U+0441
    "х": "x",   # Cyrillic х  U+0445
    "і": "i",   # Cyrillic і  U+0456
    "ӏ": "l",   # Cyrillic ӏ  U+04CF
    "у": "y",   # Cyrillic у  U+0443
    "ѕ": "s",   # Cyrillic ѕ  U+0455 (dze) — defends sk-/xoxb-style lowercase prefixes
    "ј": "j",   # Cyrillic ј  U+0458
    "һ": "h",   # Cyrillic һ  U+04BB — defends ghp_/github_pat_ prefixes
    # uppercase Cyrillic — needed to defend AKIA/AIza/PEM-style uppercase patterns
    "А": "A",   # Cyrillic А  U+0410
    "В": "B",   # Cyrillic В  U+0412
    "Е": "E",   # Cyrillic Е  U+0415
    "К": "K",   # Cyrillic К  U+041A
    "М": "M",   # Cyrillic М  U+041C
    "Н": "H",   # Cyrillic Н  U+041D (looks like H)
    "О": "O",   # Cyrillic О  U+041E
    "Р": "P",   # Cyrillic Р  U+0420
    "С": "C",   # Cyrillic С  U+0421
    "Т": "T",   # Cyrillic Т  U+0422
    "Х": "X",   # Cyrillic Х  U+0425
    "І": "I",   # Cyrillic І  U+0406
    "Ѕ": "S",   # Cyrillic Ѕ  U+0405
    "Ј": "J",   # Cyrillic Ј  U+0408
    "У": "Y",   # Cyrillic У  U+0423
    # Greek lookalikes
    "Α": "A",   # Greek Alpha   U+0391
    "Β": "B",   # Greek Beta    U+0392
    "Ε": "E",   # Greek Epsilon U+0395
    "Ζ": "Z",   # Greek Zeta    U+0396
    "Η": "H",   # Greek Eta     U+0397
    "Ι": "I",   # Greek Iota    U+0399
    "Κ": "K",   # Greek Kappa   U+039A
    "Μ": "M",   # Greek Mu      U+039C
    "Ν": "N",   # Greek Nu      U+039D
    "Ο": "O",   # Greek Omicron U+039F
    "Ρ": "P",   # Greek Rho     U+03A1
    "Τ": "T",   # Greek Tau     U+03A4
    "Υ": "Y",   # Greek Upsilon U+03A5
    "Χ": "X",   # Greek Chi     U+03A7
}


# ---------------------------------------------------------------------------
# Provider-shaped credential tokens — high-precision patterns that catch
# specific issuer prefixes regardless of whether a label precedes them.
# Order matters: these are evaluated before the generic credentials regex
# so a structured match wins.
# ---------------------------------------------------------------------------
_PROVIDER_PATTERNS: dict[str, re.Pattern] = {
    "credentials_openai_project": re.compile(
        r"sk-proj-[A-Za-z0-9_\-]{20,}",
    ),
    "credentials_openai_bare": re.compile(
        # bare sk-... but not the project-prefixed form (handled above)
        r"\bsk-(?!proj-)[A-Za-z0-9]{20,}\b",
    ),
    "credentials_github_pat": re.compile(
        r"github_pat_[A-Za-z0-9_]{20,}",
    ),
    "credentials_github_ghp": re.compile(
        r"\bghp_[A-Za-z0-9]{20,}\b",
    ),
    "credentials_slack_bot": re.compile(
        r"\bxoxb-[A-Za-z0-9\-]{10,}\b",
    ),
    "credentials_google_api": re.compile(
        r"\bAIza[A-Za-z0-9_\-]{30,}\b",
    ),
    "credentials_aws_access_key": re.compile(
        r"\bAKIA[A-Z0-9]{16}\b",
    ),
    "credentials_pem_block": re.compile(
        r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED |PGP )?PRIVATE KEY-----"
        r"[\s\S]{1,8192}?"
        r"-----END (?:RSA |EC |DSA |OPENSSH |ENCRYPTED |PGP )?PRIVATE KEY-----",
    ),
    "credentials_natural_language": re.compile(
        # "API key sk-...", "secret key abc123", "access token xoxb-..."
        r"""(?xi)
        \b(?:api\ key|secret\ key|access\ token)
        \s*[:=]?\s*
        ['"]?
        ([A-Za-z0-9_\-][A-Za-z0-9_\-./+=]{7,})
        ['"]?
        """,
    ),
}


# ---------------------------------------------------------------------------
# Built-in regex patterns per REDACT.md class
# ---------------------------------------------------------------------------
_BUILTIN_PATTERNS: dict[str, re.Pattern] = {
    # Generic labelled-credential pattern. Precision requirements (WS2):
    #   * keyword starts at a word boundary,
    #   * an explicit separator (whitespace / colon / equals / quote) must
    #     follow the keyword — underscore/hyphen joins are identifiers
    #     ("tokens_input_max"), not leaks,
    #   * the value must contain at least one digit — real high-entropy
    #     secrets essentially always do, prose words ("token estimate")
    #     essentially never do.
    # These make a zero-tolerance credentials gate viable without carpeting
    # runtime modules in allowlist markers. Provider-shaped tokens are
    # handled by the always-on _PROVIDER_PATTERNS regardless of this one.
    "credentials": re.compile(
        r"""(?xi)
        \b(?:api[_\-]?key|token|secret|password|passwd|bearer|auth)
        [\s:='"]{1,4}
        (?=[A-Za-z0-9+/=\-_]*\d)
        [A-Za-z0-9+/=\-_]{8,}
        """,
    ),
    "pii": re.compile(
        r"""(?x)
        (?:
            # v2.5 L1: negative lookahead blocks action verbs as first name token
            \b(?!(?:Hire|Call|Email|Tell|Send|Meet|Ask|See|Visit|With|Hired|Called|
                     Emailed|Told|Sent|Met|Asked|Saw|Visited|Will|Can|May|Should|
                     Would|Shall|Did|Was|Were|Has|Have|Had|Benchmark|Failure|
                     Analysis)\b)
            [A-Z][a-z]{1,20}\ [A-Z][a-z]{1,20}\b      # Firstname Lastname
            | \b\d{3}-\d{2}-\d{4}\b                    # SSN
            | \b\d{3}[.\-\ ]\d{3}[.\-\ ]\d{4}\b        # Phone
        )
        """,
    ),
    "email": re.compile(
        r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
    ),
    "internal_paths": re.compile(
        r"""(?x)
        (?:
            /(?:Users|home|var|etc|opt|srv)/[^\s"'<>]+
            | [A-Za-z]:\\[^\s"'<>]+
        )
        """,
    ),
    "client_data": re.compile(
        r"""(?xi)
        \b(?:client|customer|account|contract)[_\- ]?
        (?:id|name|number|ref)[_\- :='"]{0,4}[A-Za-z0-9\-]{3,}
        """,
    ),
    "financial": re.compile(
        r"""(?x)
        (?:
            \b\d{4}[\ \-]?\d{4}[\ \-]?\d{4}[\ \-]?\d{4}\b
            | \$[ ]*\d[\d,]*(?:\.\d{2})?
            | \b(?:IBAN|BIC|SWIFT)[:\s]+[A-Z0-9]{8,34}
        )
        """,
    ),
    "proprietary_code": re.compile(
        r"""(?xi)
        \b(?:
            [A-Z]{2,6}-\d{3,8}
            | v\d+\.\d+\.\d+[-\w]+
        )\b
        """,
    ),
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
@dataclass
class RedactClass:
    name: str
    enabled: bool
    replacement: str = "[REDACTED]"
    pattern: Optional[str] = None


@dataclass
class ScrubReport:
    redacted: int = 0
    classes_hit: list[str] = field(default_factory=list)
    provenance: str = ""
    audit_trail: list[dict] = field(default_factory=list)

    def summary(self) -> str:
        if self.redacted == 0:
            return "No PII detected."
        lines = [f"Redacted {self.redacted} token(s) across {len(self.classes_hit)} class(es):"]
        for entry in self.audit_trail:
            lines.append(f"  [{entry['class']}] {entry['count']} hit(s) → {entry['replacement']}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# REDACT.md parser
# ---------------------------------------------------------------------------
def _load_redact_md(path: Path) -> list[RedactClass]:
    """Parse REDACT.md frontmatter into RedactClass list."""
    if not path.exists():
        return [
            RedactClass(name=n, enabled=True, replacement=f"[PII:{n}]")
            for n in _BUILTIN_PATTERNS
        ]

    text = path.read_text()
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            classes = _parse_redact_frontmatter(parts[1])
            if classes:
                return classes

    return [
        RedactClass(name=n, enabled=True, replacement=f"[PII:{n}]")
        for n in _BUILTIN_PATTERNS
    ]


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"true", "yes", "on", "1"}


def _parse_scalar(value: str) -> str:
    value = value.strip()
    if "#" in value:
        value = value.split("#", 1)[0].strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _parse_redact_frontmatter(block: str) -> list[RedactClass]:
    classes: dict[str, dict[str, str]] = {}
    in_classes = False
    current: str | None = None

    for raw in block.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))

        if indent == 0:
            in_classes = stripped == "classes:"
            current = None
            continue
        if not in_classes:
            continue
        if indent == 2 and stripped.endswith(":") and not stripped.startswith("- "):
            current = stripped[:-1].strip()
            classes.setdefault(current, {})
            continue
        if current is None or indent != 4 or ":" not in stripped:
            continue
        key, _, value = stripped.partition(":")
        value = _parse_scalar(value)
        if key.strip() in {"enabled", "replacement", "pattern"}:
            classes[current][key.strip()] = value

    return [
        RedactClass(
            name=name,
            enabled=_parse_bool(cfg.get("enabled", "false")),
            replacement=cfg.get("replacement", f"[PII:{name}]"),
            pattern=cfg.get("pattern"),
        )
        for name, cfg in classes.items()
    ]


# ---------------------------------------------------------------------------
# Core pipeline stages
# ---------------------------------------------------------------------------
# Invisible / directional chars an attacker can splice into a token body to
# break regex boundaries — zero-width joiners, LRM/RLM, bidi overrides, BOM.
# These have no legitimate reason to appear inside API keys or PEM blocks; we
# strip them before NFKC in the normalized surface (WS4/SHR-069).
_INVISIBLE_CHARS_RE = re.compile(
    "["
    "​‌‍‎‏"   # ZWSP, ZWNJ, ZWJ, LRM, RLM
    "‪-‮"                     # LRE, RLE, PDF, LRO, RLO
    "⁠-⁤"                     # word joiner + invisible operators
    "⁦-⁩"                     # LRI, RLI, FSI, PDI
    "﻿"                            # zero-width no-break space / BOM
    "]"
)


def _unicode_normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", _INVISIBLE_CHARS_RE.sub("", text))


def _homoglyph_normalize(text: str) -> str:
    return "".join(_HOMOGLYPHS.get(ch, ch) for ch in text)


# Encoded-surface scanning (WS2). Candidate blobs are decoded into a validated
# side container and probed for credentials; the ORIGINAL encoded blob is what
# gets redacted on a hit. Decoded text is never substituted into the working
# string — the historical substitution step let an attacker (or an unlucky
# numeric token body) mutate a credential before the detectors ran.
_ENCODED_RUN_RE = re.compile(r"[A-Za-z0-9+/_\-]{16,}={0,2}")
_HEX_RUN_RE = re.compile(r"(?<![0-9a-fA-F])(?:[0-9a-fA-F]{2}){12,}(?![0-9a-fA-F])")
# base32: RFC 4648 alphabet [A-Z2-7]. Requires an uppercase-only run so we
# don't collide with normal English text or hex.
_BASE32_RUN_RE = re.compile(r"(?<![A-Z2-7])[A-Z2-7]{16,}={0,6}(?![A-Z2-7])")
_ENCODED_MAX_DEPTH = 3
_URLSAFE_TO_STANDARD = str.maketrans("-_", "+/")


def _validate_decoded_container(raw: bytes) -> Optional[str]:
    """Accept decoded bytes only when they form plausible embedded text.

    Requires strict UTF-8 and printable characters (tab/newline tolerated) so
    that random binary — hashes, compressed data, honest base64 payloads —
    never enters the credential probe.
    """
    try:
        decoded = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return None
    if len(decoded) < 8:
        return None
    if not all(ch.isprintable() or ch in "\t\n\r" for ch in decoded):
        return None
    return decoded


def _decode_base64_container(blob: str) -> Optional[str]:
    """Decode a base64-looking run (standard or urlsafe alphabet) or return None."""
    body = blob.rstrip("=")
    padded = body + "=" * (-len(body) % 4)
    candidates = [padded]
    translated = padded.translate(_URLSAFE_TO_STANDARD)
    if translated != padded:
        candidates.append(translated)
    for candidate in candidates:
        try:
            raw = base64.b64decode(candidate, validate=True)
        except (binascii.Error, ValueError):
            continue
        return _validate_decoded_container(raw)
    return None


def _decode_hex_container(blob: str) -> Optional[str]:
    """Decode a hex-looking run or return None."""
    try:
        raw = bytes.fromhex(blob)
    except ValueError:
        return None
    return _validate_decoded_container(raw)


def _decode_base32_container(blob: str) -> Optional[str]:
    """Decode a base32-looking run or return None."""
    body = blob.rstrip("=")
    padded = body + "=" * (-len(body) % 8)
    try:
        raw = base64.b32decode(padded, casefold=False)
    except (binascii.Error, ValueError):
        return None
    return _validate_decoded_container(raw)


# Credential probe patterns — provider-shaped tokens plus the generic
# labelled-credential pattern. The always-on set the encoded-surface probe
# uses for the credentials class.
_CREDENTIAL_PROBE_PATTERNS: tuple[re.Pattern, ...] = (
    *_PROVIDER_PATTERNS.values(),
    _BUILTIN_PATTERNS["credentials"],
)


def _probe_encoded(decoded: str, remaining_decodes: int,
                   patterns: "tuple[re.Pattern, ...] | list[re.Pattern]") -> bool:
    """Return True when decoded text matches any of `patterns` on any surface.

    Checks the raw decoded text and its normalized fold against `patterns`,
    then recurses into any encoded runs nested inside the decoded text.
    `remaining_decodes` bounds how many further decode levels may be spent on
    nested encodings. `patterns` selects the sensitivity class(es) probed —
    credentials, email, pii, or internal_paths — so a single mechanism serves
    every class rather than being hardwired to credentials.
    """
    surfaces = [decoded]
    normalized = _homoglyph_normalize(_unicode_normalize(decoded))
    if normalized != decoded:
        surfaces.append(normalized)
    for surface in surfaces:
        for pattern in patterns:
            if pattern.search(surface):
                return True
    if remaining_decodes > 0:
        for run_re, decoder in ((_ENCODED_RUN_RE, _decode_base64_container),
                                (_HEX_RUN_RE, _decode_hex_container),
                                (_BASE32_RUN_RE, _decode_base32_container)):
            for match in run_re.finditer(decoded):
                inner = decoder(match.group(0))
                if inner is not None and _probe_encoded(inner, remaining_decodes - 1, patterns):
                    return True
    return False


def _scan_encoded_surfaces(text: str,
                           patterns: "tuple[re.Pattern, ...] | list[re.Pattern]",
                           max_depth: int = _ENCODED_MAX_DEPTH) -> list[tuple[int, int]]:
    """Find encoded blobs whose decoded content matches `patterns`.

    Returns (start, end) spans in `text` covering the encoded blobs to redact.
    Purely additive: nothing in `text` is modified here.
    """
    spans: list[tuple[int, int]] = []
    for regex, decoder in ((_ENCODED_RUN_RE, _decode_base64_container),
                           (_HEX_RUN_RE, _decode_hex_container),
                           (_BASE32_RUN_RE, _decode_base32_container)):
        for match in regex.finditer(text):
            decoded = decoder(match.group(0))
            # One decode level is spent reaching `decoded`; the probe may
            # spend the rest on nested encodings (3 levels total).
            if decoded is not None and _probe_encoded(decoded, max_depth - 1, patterns):
                spans.append((match.start(), match.end()))
    return _merge_spans(spans)


# Whitespace-collapsed surface (WS2). Only anchored, high-precision provider
# prefixes participate — the generic credentials pattern relies on separators
# and label words, and collapsing whitespace under it would invite false
# positives. PEM blocks and natural-language forms are likewise excluded
# because their patterns are whitespace-aware by construction.
_WS_SCAN_PROVIDERS: tuple[str, ...] = (
    "credentials_openai_project",
    "credentials_openai_bare",
    "credentials_github_pat",
    "credentials_github_ghp",
    "credentials_slack_bot",
    "credentials_google_api",
    "credentials_aws_access_key",
)


# Sensitivity classes that get the credential-grade evasion surfaces
# (whitespace-collapsed scan + encoded-blob probe) in addition to the raw and
# normalized surfaces every class already receives. Program requirement is
# privacy=100%: a whitespace-split or base64-encoded email/SSN/path must be
# caught at the same strictness as a credential, not passed through.
_EVASION_SCAN_CLASSES: tuple[str, ...] = ("email", "pii", "internal_paths")


def _collapsed_pattern_spans(
    text: str,
    patterns: "tuple[re.Pattern, ...] | list[re.Pattern]",
    collapse,
) -> list[tuple[int, int]]:
    """Run `patterns` over a whitespace-collapsed view of `text`.

    `collapse(text, i)` decides whether the whitespace char at index `i` is
    dropped before matching. Matches map back to spans in the ORIGINAL text
    (including interior whitespace) and are returned only when that original
    span actually contains whitespace — contiguous matches are already handled
    by the raw/normalized surfaces.
    """
    collapsed_chars: list[str] = []
    index_map: list[int] = []
    for position, ch in enumerate(text):
        if ch.isspace() and collapse(text, position):
            continue
        collapsed_chars.append(ch)
        index_map.append(position)
    collapsed = "".join(collapsed_chars)
    spans: list[tuple[int, int]] = []
    for pattern in patterns:
        for match in pattern.finditer(collapsed):
            start, end = match.span()
            if end <= start:
                continue
            orig_start = index_map[start]
            orig_end = index_map[end - 1] + 1
            if any(text[j].isspace() for j in range(orig_start, orig_end)):
                spans.append((orig_start, orig_end))
    return _merge_spans(spans)


def _scan_whitespace_collapsed(text: str) -> list[tuple[int, int]]:
    """Provider tokens that survive only because whitespace splits them.

    Collapses ALL whitespace: provider patterns are anchored on fixed prefixes
    (`sk-proj-`, `AKIA`+16, ...), so a full collapse cannot let a match bleed
    into neighbouring prose.
    """
    patterns = [_PROVIDER_PATTERNS[name] for name in _WS_SCAN_PROVIDERS]
    return _collapsed_pattern_spans(text, patterns, lambda _text, _i: True)


def _borders_punctuation(text: str, index: int) -> bool:
    """True when the nearest non-space neighbour on either side is non-alphanumeric.

    Collapses only the whitespace an attacker splices around a token's
    structural characters (`@`, `.`, `-`) to break email/SSN/path matching,
    while leaving the spaces that separate ordinary words intact. So
    "john.doe @ example . com" rejoins into an email, but "contact me at ...
    please" is left alone — an unanchored email/path/SSN pattern under a full
    collapse would otherwise swallow the surrounding words.
    """
    left = index - 1
    while left >= 0 and text[left].isspace():
        left -= 1
    right = index + 1
    while right < len(text) and text[right].isspace():
        right += 1
    left_punct = left >= 0 and not text[left].isalnum()
    right_punct = right < len(text) and not text[right].isalnum()
    return left_punct or right_punct


def _scan_whitespace_split_classes(
    text: str, patterns: "tuple[re.Pattern, ...] | list[re.Pattern]",
) -> list[tuple[int, int]]:
    """Email/pii/path tokens split by whitespace around their structural chars."""
    return _collapsed_pattern_spans(text, patterns, _borders_punctuation)


def _merge_spans(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Merge overlapping/adjacent (start, end) spans; result sorted ascending."""
    if not spans:
        return []
    ordered = sorted(spans)
    merged = [ordered[0]]
    for start, end in ordered[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def _redact_spans(text: str, spans: list[tuple[int, int]], replacement: str) -> str:
    """Replace each span (assumed merged + sorted) with `replacement`."""
    for start, end in reversed(spans):
        text = text[:start] + replacement + text[end:]
    return text


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def _record_credential_hits(report: ScrubReport, class_name: str, count: int,
                            replacement: str) -> None:
    report.redacted += count
    if "credentials" not in report.classes_hit:
        report.classes_hit.append("credentials")
    report.audit_trail.append({
        "class": class_name,
        "count": count,
        "replacement": replacement,
    })


def _scan_credentials_surface(working: str, report: ScrubReport,
                              generic_pattern: Optional[re.Pattern],
                              generic_replacement: str) -> str:
    """Run provider patterns + the generic credentials pattern on one surface."""
    for name, pattern in _PROVIDER_PATTERNS.items():
        matches = list(pattern.finditer(working))
        if matches:
            _record_credential_hits(report, name, len(matches), "[REDACTED:credentials]")
            working = pattern.sub("[REDACTED:credentials]", working)
    if generic_pattern is not None:
        matches = list(generic_pattern.finditer(working))
        if matches:
            _record_credential_hits(report, "credentials", len(matches), generic_replacement)
            working = generic_pattern.sub(generic_replacement, working)
    return working


def scrub(
    text: str,
    redact_md_path: Path = Path("REDACT.md"),
    provenance: str = "",
) -> tuple[str, ScrubReport]:
    """
    Scrub PII from text using the deterministic pipeline.

    Detection order is raw-first, decode-as-additive (see module docstring):
    credentials are scanned on the untouched input, again after NFKC +
    homoglyph normalization, again on a whitespace-collapsed view (anchored
    provider prefixes only), and finally encoded blobs (base64/hex, nested up
    to 3 levels) are decoded into a side container and probed — a hit redacts
    the original encoded blob, never substituting decoded text into the
    output. Remaining REDACT.md classes run on the normalized text.

    credentials class is ALWAYS applied regardless of REDACT.md enabled flag.

    Returns (cleaned_text, ScrubReport).
    """
    classes = _load_redact_md(redact_md_path)
    report = ScrubReport(provenance=provenance)

    # Resolve the generic credentials pattern/replacement (always-on; may be
    # customized by REDACT.md).
    credentials_cls = next((cls for cls in classes if cls.name == "credentials"), None)
    if credentials_cls is not None and credentials_cls.pattern:
        generic_pattern: Optional[re.Pattern] = re.compile(
            credentials_cls.pattern, re.IGNORECASE | re.VERBOSE
        )
    else:
        generic_pattern = _BUILTIN_PATTERNS.get("credentials")
    generic_replacement = (
        credentials_cls.replacement if credentials_cls is not None
        else "[REDACTED:credentials]"
    )

    # Surface 1 — RAW input. Runs before any normalization or decoding so a
    # token body that also parses as base64/hex cannot be mutated out from
    # under the detectors.
    working = _scan_credentials_surface(text, report, generic_pattern, generic_replacement)

    # Surface 2 — normalized (NFKC + homoglyph fold), credentials re-scanned.
    working = _unicode_normalize(working)
    working = _homoglyph_normalize(working)
    working = _scan_credentials_surface(working, report, generic_pattern, generic_replacement)

    # Surface 3 — whitespace-collapsed view, anchored provider prefixes only.
    ws_spans = _scan_whitespace_collapsed(working)
    if ws_spans:
        _record_credential_hits(
            report, "credentials_whitespace_split", len(ws_spans), "[REDACTED:credentials]"
        )
        working = _redact_spans(working, ws_spans, "[REDACTED:credentials]")

    # Surface 4 — encoded blobs (additive probe; original blob is redacted).
    encoded_spans = _scan_encoded_surfaces(working, _CREDENTIAL_PROBE_PATTERNS)
    if encoded_spans:
        _record_credential_hits(
            report, "credentials_encoded", len(encoded_spans), "[REDACTED:credentials]"
        )
        working = _redact_spans(working, encoded_spans, "[REDACTED:credentials]")

    # Surface 5 — remaining enabled classes (credentials already applied above).
    for cls in classes:
        if cls.name == "credentials":
            continue
        if not cls.enabled:
            continue
        pattern = (
            re.compile(cls.pattern, re.IGNORECASE | re.VERBOSE)
            if cls.pattern
            else _BUILTIN_PATTERNS.get(cls.name)
        )
        if pattern is None:
            continue
        matches = list(pattern.finditer(working))
        if matches:
            report.redacted += len(matches)
            if cls.name not in report.classes_hit:
                report.classes_hit.append(cls.name)
            report.audit_trail.append({
                "class": cls.name,
                "count": len(matches),
                "replacement": cls.replacement,
            })
            working = pattern.sub(cls.replacement, working)

        # Evasion surfaces for high-sensitivity classes — same strictness as
        # credentials. Runs AFTER the contiguous scan above (on the already-
        # redacted `working`) so ordinary matches are handled there and only
        # genuinely whitespace-split or base64-encoded evasions are caught here.
        if cls.name in _EVASION_SCAN_CLASSES:
            evasion_spans = _merge_spans(
                _scan_whitespace_split_classes(working, [pattern])
                + _scan_encoded_surfaces(working, [pattern])
            )
            if evasion_spans:
                report.redacted += len(evasion_spans)
                if cls.name not in report.classes_hit:
                    report.classes_hit.append(cls.name)
                report.audit_trail.append({
                    "class": cls.name,
                    "count": len(evasion_spans),
                    "replacement": cls.replacement,
                })
                working = _redact_spans(working, evasion_spans, cls.replacement)

    return working, report


# Allowlist markers — recognized inside file content:
#   * File-level:  `privacy-audit: allow-file "<reason>"`
#                  anywhere in the first 40 lines; skips the whole file.
#   * Line-level:  `noqa: privacy-audit`  or  `privacy-audit: allow`
#                  on the same line; scrubbers ignore that single line.
# Every marker must be human-authored with a rationale in adjacent prose or
# comment. Do NOT sprinkle these — each allow is a policy assertion.
_ALLOW_FILE_RE = re.compile(r"privacy-audit:\s*allow-file", re.IGNORECASE)
_ALLOW_LINE_RE = re.compile(
    r"(?:noqa:\s*privacy-audit|privacy-audit:\s*(?:allow|ignore))",
    re.IGNORECASE,
)


def _file_allowlisted(text: str) -> bool:
    head = "\n".join(text.splitlines()[:40])
    return bool(_ALLOW_FILE_RE.search(head))


def _filter_noqa_lines(text: str) -> str:
    return "\n".join(line for line in text.splitlines()
                     if not _ALLOW_LINE_RE.search(line))


# Nested-archive scanning (SHR-071). Depth-3 ceiling: outer file at depth 0,
# each contained archive adds a level. Beyond that we refuse to descend and
# emit a visible warning — silently accepting depth-4 would let an attacker
# hide a secret in one extra `tar czf`.
_ARCHIVE_MAX_DEPTH = 3
_ARCHIVE_MAX_MEMBER_BYTES = 2 * 1024 * 1024   # ponytail: hard 2MiB ceiling per member; a real secret fits
_ARCHIVE_MAX_TOTAL_BYTES = 32 * 1024 * 1024   # zip-bomb cap across all members + subtrees
_ARCHIVE_MAX_MEMBERS = 4096                   # per-archive-subtree member count cap
_TEXTUAL_EXTS = {".md", ".py", ".json", ".yml", ".yaml", ".toml", ".jsonl",
                 ".txt", ".cfg", ".ini", ".env"}


def _archive_kind(path_or_name: str) -> Optional[str]:
    name = str(path_or_name).lower()
    if name.endswith(".zip"):
        return "zip"
    if name.endswith((".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2")):
        return "tar"
    return None


def _scan_archive_bytes(
    raw: bytes,
    kind: str,
    redact_md_path: Path,
    depth: int,
    budget: dict | None = None,
) -> tuple[int, list[str], bool, bool]:
    """Recursively scrub textual members of a zip/tar archive.

    Returns (credential_hits, credential_classes, depth_exceeded, malformed).
    Members that are themselves archives descend up to `_ARCHIVE_MAX_DEPTH` —
    at the ceiling, `depth_exceeded` flips True and the caller surfaces a
    warning rather than silently swallowing the buried content. Malformed
    parse errors (BadZipFile, TarError) flip `malformed` True so a caller
    can block on a wrapper that pretends to be an archive but isn't parseable
    — otherwise a truncated .zip with a plausible secret in an unreachable
    member would produce zero findings and zero warnings.

    `budget` is a shared dict {'bytes': int, 'members': int} that caps the
    total uncompressed bytes and member count across the entire nested-scan
    subtree; when either ceiling is exceeded, the current subtree stops
    descending and `malformed` is flipped so the caller surfaces it.
    """
    import io
    if budget is None:
        budget = {"bytes": 0, "members": 0}
    hits = 0
    classes_hit: list[str] = []
    depth_exceeded = False
    malformed = False

    def _observe(sub_text: str) -> None:
        nonlocal hits
        _, sub_report = scrub(sub_text, redact_md_path)
        for entry in sub_report.audit_trail:
            if str(entry["class"]).startswith("credentials"):
                hits += entry["count"]
                classes_hit.append(str(entry["class"]))

    def _budget_ok(data_len: int) -> bool:
        # zip-bomb + member-flood cap enforced across the whole subtree.
        budget["members"] += 1
        budget["bytes"] += data_len
        return (budget["members"] <= _ARCHIVE_MAX_MEMBERS
                and budget["bytes"] <= _ARCHIVE_MAX_TOTAL_BYTES)

    def _handle_member(member_name: str, data: bytes) -> None:
        nonlocal depth_exceeded, malformed, hits
        if len(data) > _ARCHIVE_MAX_MEMBER_BYTES:
            return
        if not _budget_ok(len(data)):
            malformed = True  # surfaces as blocking finding — same treatment as parse errors
            return
        inner_kind = _archive_kind(member_name)
        if inner_kind is not None:
            if depth + 1 >= _ARCHIVE_MAX_DEPTH:
                depth_exceeded = True
                return
            sub_hits, sub_classes, sub_exceeded, sub_malformed = _scan_archive_bytes(
                data, inner_kind, redact_md_path, depth + 1, budget,
            )
            hits += sub_hits
            classes_hit.extend(sub_classes)
            depth_exceeded = depth_exceeded or sub_exceeded
            malformed = malformed or sub_malformed
            return
        # Non-archive member — treat as text if extension suggests text or if
        # bytes decode cleanly. Anything else (binaries, images) is skipped.
        suffix = Path(member_name).suffix.lower()
        if suffix and suffix not in _TEXTUAL_EXTS:
            return
        try:
            text = data.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            return
        _observe(text)

    if kind == "zip":
        import zipfile
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    if info.file_size > _ARCHIVE_MAX_MEMBER_BYTES:
                        continue
                    try:
                        data = zf.read(info.filename)
                    except (zipfile.BadZipFile, RuntimeError, OSError):
                        malformed = True
                        continue
                    _handle_member(info.filename, data)
        except (zipfile.BadZipFile, OSError, EOFError):
            malformed = True
    elif kind == "tar":
        import tarfile
        try:
            with tarfile.open(fileobj=io.BytesIO(raw), mode="r:*") as tf:
                for member in tf.getmembers():
                    if not member.isfile():
                        continue
                    if member.size > _ARCHIVE_MAX_MEMBER_BYTES:
                        continue
                    fh = tf.extractfile(member)
                    if fh is None:
                        continue
                    data = fh.read()
                    _handle_member(member.name, data)
        except (tarfile.TarError, OSError, EOFError):
            malformed = True

    return hits, classes_hit, depth_exceeded, malformed


def _redact_md_dirty(directory: Path, redact_md_path: Path) -> bool:
    """Return True when REDACT.md has uncommitted changes vs HEAD.

    SHR-073: an allowlist change cannot silently unblock a secret in the same
    run. If the file the scanner reads for its rules is dirty, that's a hard
    stop. When the tree isn't the top of its own git checkout, we return
    False — no reliable HEAD, no signal, and CI runs on clean checkouts.
    """
    import subprocess
    try:
        rel = redact_md_path.resolve().relative_to(directory.resolve())
    except ValueError:
        return False
    # Only trigger when `directory` IS the top of a git checkout. This avoids
    # firing on scaffolded tmp dirs or on repos whose parent chain happens to
    # contain a .git (which would surface "error: Could not access HEAD"
    # with rc=1 and be misread as dirty).
    try:
        top = subprocess.run(
            ["git", "-C", str(directory), "rev-parse", "--show-toplevel"],
            capture_output=True, timeout=15, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    if top.returncode != 0:
        return False
    top_path = top.stdout.decode("utf-8", "ignore").strip()
    if not top_path or Path(top_path).resolve() != directory.resolve():
        return False
    try:
        proc = subprocess.run(
            ["git", "-C", str(directory), "diff", "--quiet", "HEAD", "--", str(rel)],
            capture_output=True, timeout=15, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 1


def _tracked_files(directory: Path) -> set[Path] | None:
    """Resolved paths of git-tracked files under `directory`.

    Returns None when `directory` is not a git checkout (or git is
    unavailable), which callers treat as "scan everything".
    """
    import subprocess
    try:
        proc = subprocess.run(
            ["git", "-C", str(directory), "ls-files", "-z"],
            capture_output=True, timeout=30, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    names = [n for n in proc.stdout.decode("utf-8", "ignore").split("\0") if n]
    if not names:
        return None
    return {(directory / n).resolve() for n in names}


def audit(
    directory: Path = Path("."),
    redact_md_path: Path = Path("REDACT.md"),
    strict: bool = False,
) -> dict:
    """
    Read-only audit: scan tracked-file extensions under directory for PII hits.
    Default skips `tests/fixtures/` (documented-historical).
    When strict=True, scanned extensions expand to include .py/.json/.yml/.yaml/.toml/.jsonl.
    Files carrying `privacy-audit: allow-file "<reason>"` in their first 40 lines
    are skipped entirely; lines carrying `noqa: privacy-audit` are excluded from
    the scan input. Returns {scanned, total_hits, by_file, by_class, allowlisted}.
    """
    # Trees that intentionally cite PII-shaped tokens as content, examples,
    # or historical spec text are skipped in strict mode. The scan focuses
    # on trees where a real leak would be an accidental egress:
    #   scanned in strict:  root *.md, config/, shiroe/, .github/
    #   skipped in strict:  docs/, references/, tests/, CHANGELOG.md
    #                       (release history), and self-referential modules
    #                       whose docstrings document detection patterns.
    # Skip rules match whole path COMPONENTS (or an exact repo-relative path),
    # never a substring of the joined path. A substring test silently exempts
    # any file whose name merely contains a skip token — "notdocs.md" matching
    # "docs", "distribution.md" matching "dist" — which is a fail-open hole in
    # a scan whose entire job is to catch accidental egress.
    _SKIP_DIRS = {
        "docs", "references",
        "tests", ".git", "__pycache__", "node_modules", "assets",
        # Third-party and generated trees. These are not authored surfaces:
        # dependency source legitimately contains credential-shaped example
        # strings, and scanning them made the release gate fail purely because
        # a local virtualenv existed. Agent worktrees hold full repo copies,
        # so scanning them double-counts every finding.
        ".venv", "venv", "site-packages", ".tox", ".nox",
        "build", "dist", ".claude",
        ".pytest_cache", ".mypy_cache", ".ruff_cache",
    }
    # Exact repo-relative paths (POSIX separators).
    _SKIP_PATHS = {
        "CHANGELOG.md",
        # detection modules whose own docstrings show pattern examples
        "shiroe/privacy.py", "shiroe/security/policy.py",
    }

    def _skipped(rel_path: Path) -> bool:
        if rel_path.as_posix() in _SKIP_PATHS:
            return True
        parts = rel_path.parts
        if any(part in _SKIP_DIRS for part in parts):
            return True
        # Packaging metadata directories are named "<project>.egg-info".
        return any(part.endswith(".egg-info") for part in parts)
    exts = {".md"} if not strict else {".md", ".py", ".json", ".yml", ".yaml", ".toml", ".jsonl"}
    # Archive containers (SHR-071): scanned in strict mode so an attacker
    # can't smuggle a secret past the regex-driven surfaces by shipping it
    # inside a zip/tar.
    archive_exts = {".zip", ".tar", ".gz", ".tgz", ".bz2", ".tbz2"} if strict else set()
    results: dict = {
        "scanned": 0, "total_hits": 0, "by_file": {}, "by_class": {},
        "strict": strict, "allowlisted": [],
        # Severity-class accounting (WS2): total HIT counts per class (unlike
        # by_class, which counts affected files), with provider-shaped
        # subclasses folded into "credentials". credential_files maps each
        # file containing credentials-class hits to its hit count — release
        # gates treat any entry here as a hard failure.
        "hits_by_class": {}, "credential_files": {},
        # SHR-071 / SHR-073 signals — surfaced by CLI + release gate.
        # depth_exceeded and malformed both stamp a synthetic
        # credentials-class hit against the offending archive path so the
        # zero-tolerance gate refuses the release; the lists are kept for
        # human-readable output.
        "archive_depth_exceeded": [],
        "archive_malformed": [],
        "allowlist_changed": False,
    }

    directory = Path(directory)
    # SHR-073: if the allowlist file itself is dirty vs HEAD, an allowlist
    # widening could silently unblock a secret in the same commit. Mark the
    # scan as failing and stamp a synthetic credentials-class hit against
    # REDACT.md so the zero-tolerance gate trips.
    if strict and _redact_md_dirty(directory, redact_md_path):
        results["allowlist_changed"] = True
        marker = str(redact_md_path)
        results["credential_files"][marker] = results["credential_files"].get(marker, 0) + 1
        results["hits_by_class"]["credentials"] = results["hits_by_class"].get("credentials", 0) + 1
        results["total_hits"] += 1
    tracked = _tracked_files(directory)
    for path in sorted(directory.rglob("*")):
        if not path.is_file():
            continue
        # Archive branch (SHR-071): recurse into nested containers up to
        # _ARCHIVE_MAX_DEPTH; a member that's still an archive at that depth
        # is surfaced as a warning, never silently skipped.
        archive_kind = _archive_kind(path.name) if path.suffix.lower() in archive_exts else None
        if archive_kind is not None:
            rel = path.relative_to(directory) if path.is_absolute() else path
            if _skipped(Path(rel)):
                continue
            if tracked is not None and path.resolve() not in tracked:
                continue
            try:
                raw = path.read_bytes()
            except OSError:
                continue
            hits, classes_hit, depth_exceeded, malformed = _scan_archive_bytes(
                raw, archive_kind, redact_md_path, depth=0,
            )
            results["scanned"] += 1
            # depth-exceeded and malformed both stamp a synthetic credentials
            # hit against the offending path so `--fail-classes credentials`
            # and the release gate refuse — either would be a bypass otherwise.
            if depth_exceeded:
                results["archive_depth_exceeded"].append(str(path))
                results["credential_files"][str(path)] = (
                    results["credential_files"].get(str(path), 0) + 1
                )
                results["hits_by_class"]["credentials"] = (
                    results["hits_by_class"].get("credentials", 0) + 1
                )
                results["total_hits"] += 1
            if malformed:
                results["archive_malformed"].append(str(path))
                results["credential_files"][str(path)] = (
                    results["credential_files"].get(str(path), 0) + 1
                )
                results["hits_by_class"]["credentials"] = (
                    results["hits_by_class"].get("credentials", 0) + 1
                )
                results["total_hits"] += 1
            if hits:
                results["total_hits"] += hits
                results["by_file"][str(path)] = results["by_file"].get(str(path), 0) + hits
                results["hits_by_class"]["credentials"] = (
                    results["hits_by_class"].get("credentials", 0) + hits
                )
                results["credential_files"][str(path)] = (
                    results["credential_files"].get(str(path), 0) + hits
                )
                if "credentials" not in results["by_class"]:
                    results["by_class"]["credentials"] = 0
                results["by_class"]["credentials"] += 1
            continue
        if path.suffix not in exts:
            continue
        # Inside a git checkout, assess only tracked content. A release gate
        # answers "is what we publish clean?" — untracked local files (audit
        # inputs, scratch notes, downloaded fixtures) are never published, so
        # flagging them blocks releases over material that cannot leak. When
        # the directory is not a git repo (scaffolded temp dirs, fresh inits)
        # `tracked` is None and every file is scanned, as before.
        if tracked is not None and path.resolve() not in tracked:
            continue
        rel = path.relative_to(directory) if path.is_absolute() else path
        if _skipped(Path(rel)):
            continue
        if _is_macos_dataless_placeholder(path):
            continue
        try:
            text = path.read_text(errors="ignore")
        except (OSError, UnicodeDecodeError):
            continue
        if _file_allowlisted(text):
            results["allowlisted"].append(str(path))
            continue
        text = _filter_noqa_lines(text)
        _, report = scrub(text, redact_md_path)
        results["scanned"] += 1
        if report.redacted:
            results["total_hits"] += report.redacted
            results["by_file"][str(path)] = report.redacted
            for cls in report.classes_hit:
                results["by_class"][cls] = results["by_class"].get(cls, 0) + 1
            for entry in report.audit_trail:
                severity_class = (
                    "credentials"
                    if str(entry["class"]).startswith("credentials")
                    else str(entry["class"])
                )
                results["hits_by_class"][severity_class] = (
                    results["hits_by_class"].get(severity_class, 0) + entry["count"]
                )
                if severity_class == "credentials":
                    results["credential_files"][str(path)] = (
                        results["credential_files"].get(str(path), 0) + entry["count"]
                    )

    return results


def _is_macos_dataless_placeholder(path: Path) -> bool:
    """Avoid blocking on cloud-backed files that have metadata but no local bytes."""
    try:
        flags = os.stat(path).st_flags
    except (AttributeError, OSError):
        return False
    # macOS exposes dataless cloud placeholders with an undocumented high bit.
    # Reading those can block while the OS attempts to materialize the file.
    return bool(flags & 0x40000000)
