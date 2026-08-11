"""SHR-082..085: corrupt datasets and malformed provider responses fail with
exact error codes.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from shiroe.adapters.providers.base import JsonProviderAdapter


REPO_ROOT = Path(__file__).resolve().parent.parent


def _write(tmp_path: Path, payload: dict | str) -> Path:
    p = tmp_path / "provider.json"
    if isinstance(payload, dict):
        p.write_text(json.dumps(payload), encoding="utf-8")
    else:
        p.write_text(payload, encoding="utf-8")
    return p


def _v2_ok() -> dict:
    return {
        "schema": "shiroe.provider/v2",
        "provider": "test-provider",
        "classes": {
            "frontier": {
                "model_id": "claude-fable-5",
                "effort": "high",
                "lifecycle": "active",
                "verified_at": "2026-07-27",
                "verified_by": "human",
                "source_url": "https://example.test/spec",
            },
        },
    }


def test_provider_missing_schema_raises_value_error(tmp_path: Path) -> None:
    payload = _v2_ok()
    del payload["schema"]
    p = _write(tmp_path, payload)
    with pytest.raises(ValueError) as exc:
        JsonProviderAdapter(p)
    msg = str(exc.value)
    assert "expected schema" in msg
    assert str(p) in msg


def test_provider_wrong_schema_raises_value_error(tmp_path: Path) -> None:
    payload = _v2_ok()
    payload["schema"] = "shiroe.provider/v99"
    p = _write(tmp_path, payload)
    with pytest.raises(ValueError) as exc:
        JsonProviderAdapter(p)
    assert "shiroe.provider/v99" in str(exc.value)


def test_provider_unknown_lifecycle_raises_value_error(tmp_path: Path) -> None:
    payload = _v2_ok()
    payload["classes"]["frontier"]["lifecycle"] = "coasting"
    p = _write(tmp_path, payload)
    with pytest.raises(ValueError) as exc:
        JsonProviderAdapter(p)
    msg = str(exc.value)
    assert "unknown lifecycle" in msg
    assert "coasting" in msg


def test_provider_unknown_verified_by_raises_value_error(tmp_path: Path) -> None:
    payload = _v2_ok()
    payload["classes"]["frontier"]["verified_by"] = "gut_feeling"
    p = _write(tmp_path, payload)
    with pytest.raises(ValueError) as exc:
        JsonProviderAdapter(p)
    msg = str(exc.value)
    assert "unknown verified_by" in msg
    assert "gut_feeling" in msg


def test_provider_fallback_missing_model_id_raises_value_error(tmp_path: Path) -> None:
    payload = _v2_ok()
    payload["classes"]["frontier"]["fallback"] = {
        "lifecycle": "active",
        "verified_at": "2026-07-27",
        "verified_by": "human",
        "source_url": "https://example.test/spec",
    }
    p = _write(tmp_path, payload)
    with pytest.raises(ValueError) as exc:
        JsonProviderAdapter(p)
    msg = str(exc.value)
    assert "missing model_id" in msg
    assert "frontier" in msg


def test_provider_unknown_reasoning_class_raises_value_error(tmp_path: Path) -> None:
    payload = _v2_ok()
    payload["classes"] = {
        "megabrain": payload["classes"]["frontier"],
    }
    p = _write(tmp_path, payload)
    with pytest.raises(ValueError) as exc:
        JsonProviderAdapter(p)
    assert "megabrain" in str(exc.value)


def test_provider_truncated_json_raises_json_decode_error(tmp_path: Path) -> None:
    p = _write(tmp_path, '{"schema": "shiroe.provider/v2", "provider": "x", "classes":')
    with pytest.raises(json.JSONDecodeError):
        JsonProviderAdapter(p)


def test_provider_capability_unverified_when_v1(tmp_path: Path) -> None:
    payload = {
        "schema": "shiroe.provider/v1",
        "provider": "legacy",
        "classes": {"frontier": {"model_id": "m", "effort": "high"}},
    }
    p = _write(tmp_path, payload)
    adapter = JsonProviderAdapter(p)
    cap = adapter.capability("frontier")
    assert cap.fails_closed()


def test_shipped_provider_files_load_cleanly() -> None:
    for name in ("anthropic.json", "openai.json"):
        JsonProviderAdapter(REPO_ROOT / "shiroe/adapters/providers" / name)
