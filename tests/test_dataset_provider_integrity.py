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


def _bench_ok() -> dict:
    return {
        "label": "internal quality axes",
        "evidence_namespace": "conformance",
        "evidence_tier": "fixture_tested",
        "passed": True,
        "pass_bar": {"axis_min": 9.0},
        "axes": [
            {"axis": "portability", "score": 10.0, "sub": {}},
        ],
    }


def _load_bench(p: Path) -> dict:
    text = p.read_text(encoding="utf-8")
    data = json.loads(text)
    for key, kind in (
        ("label", str),
        ("evidence_namespace", str),
        ("evidence_tier", str),
        ("axes", list),
    ):
        if key not in data:
            raise KeyError(f"benchmark result missing required key: {key}")
        if not isinstance(data[key], kind):
            raise TypeError(
                f"benchmark result key {key!r} has type {type(data[key]).__name__}, "
                f"expected {kind.__name__}"
            )
    return data


def test_real_benchmark_results_are_wellformed() -> None:
    data = _load_bench(REPO_ROOT / "benchmarks" / "results.json")
    assert data["axes"], "at least one axis expected"


def test_truncated_benchmark_json_fails_deterministically(tmp_path: Path) -> None:
    p = tmp_path / "results.json"
    p.write_text('{"label": "x", "axes"', encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        _load_bench(p)


def test_benchmark_missing_axes_raises_key_error(tmp_path: Path) -> None:
    payload = _bench_ok()
    del payload["axes"]
    p = tmp_path / "results.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(KeyError) as exc:
        _load_bench(p)
    assert "axes" in str(exc.value)


def test_benchmark_wrong_type_axes_raises_type_error(tmp_path: Path) -> None:
    payload = _bench_ok()
    payload["axes"] = "portability, retrieval"
    p = tmp_path / "results.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(TypeError) as exc:
        _load_bench(p)
    msg = str(exc.value)
    assert "axes" in msg
    assert "str" in msg or "expected list" in msg


def test_benchmark_missing_evidence_tier_raises_key_error(tmp_path: Path) -> None:
    payload = _bench_ok()
    del payload["evidence_tier"]
    p = tmp_path / "results.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(KeyError) as exc:
        _load_bench(p)
    assert "evidence_tier" in str(exc.value)


def test_shipped_provider_files_load_cleanly() -> None:
    for name in ("anthropic.json", "openai.json"):
        JsonProviderAdapter(REPO_ROOT / "shiroe/adapters/providers" / name)
