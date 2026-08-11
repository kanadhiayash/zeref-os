"""SHR-086..089: every published external-run result names its
dataset lock, command, model, commit, metric type, cost, and raw
artifact pointer.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmarks.external.harness import build_provenance


REPO_ROOT = Path(__file__).resolve().parent.parent

REQUIRED_FIELDS: tuple[str, ...] = (
    "git_sha",
    "command",
    "raw_artifact",
    "metric_type",
    "dataset",
    "model_id",
    "cost",
)


class _FakeLoader:
    NAME = "fake"
    OFFICIAL_URL = "https://example.test/fake"
    PINNED_VERSION = "1.0"
    PINNED_SHA256 = "0" * 64
    DATA_FILENAME = "fake.jsonl"
    METRIC = "exact_match"
    LICENSE = "MIT"
    LICENSE_NOTE = "synthetic"


def _payload(**overrides) -> dict:
    p = build_provenance(
        _FakeLoader,
        Path("/tmp/does-not-exist"),
        model_id="claude-fable-5",
        prompts_hash="ph",
        usage_total={"usd_total": 0.42, "tokens_in": 100, "tokens_out": 50},
        mode="proxy",
        command=["python", "-m", "benchmarks.external.harness", "--benchmark", "fake"],
        raw_artifact="benchmarks/external/results/fake.jsonl",
    )
    p.update(overrides)
    return p


def validate_publishable(provenance: dict) -> None:
    for field in REQUIRED_FIELDS:
        if field not in provenance:
            raise ValueError(f"external-run provenance missing required field: {field}")
        if provenance[field] in (None, "", [], {}):
            raise ValueError(f"external-run provenance field {field!r} is empty")
    dataset = provenance["dataset"]
    for sub in ("sha256_pinned", "sha256_actual"):
        if sub not in dataset:
            raise ValueError(f"external-run provenance dataset lock missing {sub}")


def test_full_payload_validates() -> None:
    p = _payload()
    p["dataset"]["sha256_actual"] = "1" * 64
    validate_publishable(p)


def test_metric_type_is_populated_from_loader() -> None:
    p = _payload()
    assert p["metric_type"] == "exact_match"


def test_command_defaults_to_sys_argv_when_not_supplied() -> None:
    p = build_provenance(
        _FakeLoader,
        Path("/tmp/does-not-exist"),
        model_id="m",
        prompts_hash="ph",
        usage_total={},
        mode="proxy",
    )
    assert isinstance(p["command"], list)
    assert p["command"], "command must not be empty"


def test_raw_artifact_pointer_carries_through() -> None:
    p = _payload()
    assert p["raw_artifact"] == "benchmarks/external/results/fake.jsonl"


@pytest.mark.parametrize("field", REQUIRED_FIELDS)
def test_missing_top_level_field_fails_deterministically(field: str) -> None:
    p = _payload()
    p["dataset"]["sha256_actual"] = "1" * 64
    del p[field]
    with pytest.raises(ValueError) as exc:
        validate_publishable(p)
    assert field in str(exc.value)


@pytest.mark.parametrize("field", REQUIRED_FIELDS)
def test_empty_top_level_field_fails_deterministically(field: str) -> None:
    p = _payload()
    p["dataset"]["sha256_actual"] = "1" * 64
    empties = {
        "git_sha": "",
        "command": [],
        "raw_artifact": "",
        "metric_type": "",
        "dataset": {},
        "model_id": "",
        "cost": {},
    }
    p[field] = empties[field]
    with pytest.raises(ValueError) as exc:
        validate_publishable(p)
    assert field in str(exc.value) or "empty" in str(exc.value)


@pytest.mark.parametrize("sub", ("sha256_pinned", "sha256_actual"))
def test_missing_dataset_lock_field_fails(sub: str) -> None:
    p = _payload()
    p["dataset"]["sha256_actual"] = "1" * 64
    del p["dataset"][sub]
    with pytest.raises(ValueError) as exc:
        validate_publishable(p)
    assert sub in str(exc.value)


def test_published_result_survives_json_round_trip(tmp_path: Path) -> None:
    from benchmarks.external.harness import write_results

    payload = {
        "backend": "shiroe",
        "task_count": 0,
        "official_metric_scores": None,
        "retrieval_hit_proxy_mean": None,
        "tasks": [],
        "provenance": _payload(),
    }
    payload["provenance"]["dataset"]["sha256_actual"] = "1" * 64
    out = write_results(tmp_path / "out.json", payload)
    data = json.loads(out.read_text(encoding="utf-8"))
    validate_publishable(data["provenance"])
