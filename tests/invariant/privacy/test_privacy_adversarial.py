"""
Adversarial privacy-redaction suite (WS2 hardening).

Every fixture is assembled at runtime by concatenation (mirroring the `_fx`
convention in tests/test_privacy_redaction.py) so this file never contains a
literal that resembles a real credential.

Case provenance
---------------
Cases tagged BITES-PRE-FIX below were verified to bypass the pre-WS2 scrubber
(redacted=0 against the pipeline at origin/dev 535160b, where base64 decoding
mutated the working text BEFORE provider-token detection ran). The remaining
cases document behavior the old pipeline already handled and pin it against
regression.

BITES-PRE-FIX: numeric_body_26, numeric_body_28, hex_encoded,
whitespace_injected, newline_split, cyrillic_dze_prefix, nested_double_base64,
nested_triple_base64, hex_inside_base64.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from shiroe.privacy import scrub


# ---------------------------------------------------------------------------
# Concatenated fixture fragments — never a full credential-shaped literal.
# ---------------------------------------------------------------------------
_SK = "s" + "k"
_ALPHA_BODY = "AbCdEfGhIjKlMnOpQrStUv1234"


def _sk_proj(body: str) -> str:
    return _SK + "-proj-" + body


def _b64(payload: str) -> str:
    return base64.b64encode(payload.encode("utf-8")).decode("ascii")


def _b64_urlsafe(payload: str) -> str:
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")


# ---------------------------------------------------------------------------
# Adversarial positives — every one must be redacted, and the secret material
# (or its encoded carrier) must not survive into the output.
# ---------------------------------------------------------------------------
def _adversarial_cases() -> list[tuple[str, str, str]]:
    """Return (label, text, must_not_survive) triples."""
    numeric_26 = _sk_proj("4" * 6 + "12345678901234567890")           # BITES-PRE-FIX
    numeric_28 = _sk_proj("1234567890" * 2 + "12345678")               # BITES-PRE-FIX
    alpha_token = _sk_proj(_ALPHA_BODY)
    hex_blob = _sk_proj(_ALPHA_BODY[:24]).encode("utf-8").hex()        # BITES-PRE-FIX
    ws_token = _sk_proj("AbCdE FgHiJ KlMnO PqRsT Uv123 456")           # BITES-PRE-FIX
    nl_token = _sk_proj("AbCdEfGhIj\nKlMnOpQrStUv1234")                # BITES-PRE-FIX
    cyrillic = "ѕ" + "k-proj-" + _ALPHA_BODY                      # BITES-PRE-FIX (ѕ U+0455)
    fullwidth = "ｓｋ－proj-" + _ALPHA_BODY                # NFKC regression case
    b64_once = _b64(alpha_token)                                       # regression (old substitution caught it)
    b64_urlsafe = _b64_urlsafe(alpha_token + "?~")                     # regression
    b64_twice = _b64(_b64(alpha_token))                                # BITES-PRE-FIX
    b64_thrice = _b64(_b64(_b64(alpha_token)))                         # BITES-PRE-FIX
    hex_in_b64 = _b64(alpha_token.encode("utf-8").hex())               # BITES-PRE-FIX
    return [
        ("numeric_body_26",      f"config value {numeric_26} committed",      numeric_26),
        ("numeric_body_28",      f"config value {numeric_28} committed",      numeric_28),
        ("hex_encoded",          f"blob {hex_blob} in log",                   hex_blob),
        ("whitespace_injected",  f"note {ws_token} end",                      "AbCdE FgHiJ"),
        ("newline_split",        f"note {nl_token} end",                      "AbCdEfGhIj\nKlMnOpQrStUv"),
        ("cyrillic_dze_prefix",  f"suspicious {cyrillic} in paste",           _ALPHA_BODY),
        ("fullwidth_prefix",     f"suspicious {fullwidth} in paste",          _ALPHA_BODY),
        ("base64_standard",      f"encoded {b64_once} leaked",                b64_once),
        ("base64_urlsafe",       f"encoded {b64_urlsafe} leaked",             b64_urlsafe),
        ("nested_double_base64", f"encoded {b64_twice} leaked",               b64_twice),
        ("nested_triple_base64", f"encoded {b64_thrice} leaked",              b64_thrice),
        ("hex_inside_base64",    f"encoded {hex_in_b64} leaked",              hex_in_b64),
    ]


@pytest.mark.parametrize("label,text,must_not_survive", _adversarial_cases())
def test_adversarial_redaction(label: str, text: str, must_not_survive: str) -> None:
    out, report = scrub(text)
    assert report.redacted >= 1, f"[{label}] bypass: no redaction. out={out!r}"
    assert "credentials" in report.classes_hit, f"[{label}] wrong class: {report.classes_hit}"
    assert must_not_survive not in out, f"[{label}] secret material survived: {out!r}"


def test_decoded_text_never_substituted_into_output() -> None:
    """The encoded surface is additive: the blob is redacted, never decoded in place."""
    blob = _b64(_sk_proj(_ALPHA_BODY))
    out, report = scrub(f"payload {blob} end")
    assert report.redacted >= 1
    assert _SK + "-proj-" not in out, f"decoded credential substituted into output: {out!r}"
    assert "[REDACTED:credentials]" in out


def test_nesting_depth_is_bounded() -> None:
    """Encoded probing follows nesting to 3 levels and stops (DoS bound)."""
    token = _sk_proj(_ALPHA_BODY)
    quadruple = _b64(_b64(_b64(_b64(token))))
    out, report = scrub(f"blob {quadruple} end")
    # Four levels is beyond the bound; the important property is that scrub
    # terminates and does not crash. The blob itself carries no plaintext.
    assert token not in out


# ---------------------------------------------------------------------------
# Precision — identifier-shaped and benign-encoded text must NOT be redacted.
# These pin the WS2 tightening of the generic credentials pattern that makes
# the zero-tolerance CI gate viable.
# ---------------------------------------------------------------------------
PRECISION_NEGATIVES: list[tuple[str, str]] = [
    ("identifier_underscore",  "tokens_input_max: 4096 and tokens_output_max: 2048"),
    ("identifier_prose",       "token estimate for the compilation run"),
    ("identifier_auth_word",   "the session is authenticated and authorized"),
    ("identifier_assignment",  "api_key = env_hint  # resolved from environment"),
    ("benign_base64_text",     _b64("just some ordinary sentence here ok")),
    ("git_sha_hex",            "pinned to 9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0"),
    ("benign_hex_words",       "deadbeefdeadbeefdeadbeefdeadbeef checksum"),
]


@pytest.mark.parametrize("label,text", PRECISION_NEGATIVES)
def test_precision_no_false_positive(label: str, text: str) -> None:
    out, report = scrub(text)
    assert report.redacted == 0, (
        f"[{label}] false positive: {report.redacted} hit(s) in {text!r} -> {out!r}"
    )


def test_labelled_secret_with_digits_still_caught() -> None:
    out, report = scrub("api_key: aZ09_aZ09_aZ09_aZ09")
    assert report.redacted >= 1
    assert "aZ09" not in out


# ---------------------------------------------------------------------------
# Handoff privacy filtering — private/local-only/unknown atoms stay home.
# ---------------------------------------------------------------------------
def _handoff_root(tmp_path: Path) -> tuple[Path, dict[str, dict]]:
    from shiroe.memory import scaffold_project
    from shiroe.memory.models import MemoryWrite
    from shiroe.memory.service import MemoryService

    (tmp_path / "AGENTS.md").write_text("# AGENTS.md\n", encoding="utf-8")
    scaffold_project(tmp_path, name="adversarial", privacy="abstract", network_scope="device-only")
    service = MemoryService(tmp_path)
    atoms: dict[str, dict] = {}
    for privacy in ("public", "internal", "restricted", "unknown"):
        record = service.write(
            MemoryWrite(
                kind="fact",
                claim=f"the {privacy} pipeline stage is deterministic",
                title=f"{privacy} fixture record",
                summary=f"{privacy} fixture record",
                source_refs=("tests/test_privacy_adversarial.py",),
                evidence_grade="A",
                confidence="high",
                privacy_class=privacy,
            )
        )
        atoms[privacy] = {"id": record.id}
    return tmp_path, atoms


def _handoff_payload_json(result: dict) -> dict:
    return json.loads(Path(result["json"]).read_text(encoding="utf-8"))


def test_handoff_excludes_private_atoms_by_default(tmp_path: Path) -> None:
    from shiroe.handoff.compiler import compile_handoff

    root, atoms = _handoff_root(tmp_path)
    result = compile_handoff(root, target="codex")
    payload = _handoff_payload_json(result)
    exported_ids = {fact["id"] for fact in payload["known_facts"]}

    assert atoms["public"]["id"] in exported_ids
    assert atoms["internal"]["id"] not in exported_ids
    assert atoms["restricted"]["id"] not in exported_ids
    assert atoms["unknown"]["id"] not in exported_ids, "unknown must fail closed"

    markdown = Path(result["markdown"]).read_text(encoding="utf-8")
    assert atoms["internal"]["id"] not in markdown
    assert atoms["restricted"]["id"] not in markdown
    assert atoms["unknown"]["id"] not in markdown

    assert result["privacy"]["include_private"] is False
    assert result["privacy"]["excluded_atoms"] == {
        "internal": 2, "restricted": 1,
    }


def test_handoff_include_private_flag_exports_private_not_local_only(tmp_path: Path) -> None:
    from shiroe.handoff.compiler import compile_handoff

    root, atoms = _handoff_root(tmp_path)
    result = compile_handoff(root, target="codex", include_private=True)
    payload = _handoff_payload_json(result)
    exported_ids = {fact["id"] for fact in payload["known_facts"]}

    assert atoms["public"]["id"] in exported_ids
    assert atoms["internal"]["id"] in exported_ids
    assert atoms["unknown"]["id"] in exported_ids
    assert atoms["restricted"]["id"] not in exported_ids, (
        "restricted memory must never be exported, even with include_private=True"
    )
    assert result["privacy"]["include_private"] is True
    assert result["privacy"]["excluded_atoms"] == {"restricted": 1}


def test_handoff_include_private_emits_audit_event(tmp_path: Path) -> None:
    from shiroe.handoff.compiler import compile_handoff

    root, atoms = _handoff_root(tmp_path)
    audit_log = root / "memory" / "audit" / "redactions.jsonl"

    compile_handoff(root, target="human")
    baseline = [
        json.loads(line)
        for line in audit_log.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ] if audit_log.exists() else []
    assert not any(
        "include_private" in event.get("reason", "") for event in baseline
    ), "default handoff must not log a private-export override"

    compile_handoff(root, target="human", include_private=True)
    events = [
        json.loads(line)
        for line in audit_log.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    override_events = [
        event for event in events if "include_private=True" in event.get("reason", "")
    ]
    assert len(override_events) == 1
    event = override_events[0]
    assert event["event_type"] == "redaction"
    assert event["status"] == "override"
    assert event["payload"]["target"] == "human"
    assert event["payload"]["private_atoms_included"] == 2  # internal + unknown
    assert atoms["internal"]["id"] in event["payload"]["private_atom_ids"]
    assert atoms["restricted"]["id"] not in event["payload"]["private_atom_ids"]


def test_handoff_wrappers_thread_include_private(tmp_path: Path) -> None:
    import inspect

    from shiroe.handoff import claude, codex, cursor, github, human

    for module in (claude, codex, cursor, github, human):
        signature = inspect.signature(module.build)
        assert "include_private" in signature.parameters, module.__name__
        assert signature.parameters["include_private"].default is False, module.__name__
