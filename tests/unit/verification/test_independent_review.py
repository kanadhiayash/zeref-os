from __future__ import annotations

import json
from pathlib import Path

import pytest

from shiroe.adapters.capabilities import AdapterResult, EnforcementLevel, HealthReport, register_adapter
from shiroe.capabilities.inspection import inspect_source
from shiroe.capabilities.store import CapabilityStore


class ReviewReasoner:
    name = "test-reviewer"
    enforcement_level = EnforcementLevel.embedded
    supported_types = ("api_service",)

    def health(self) -> HealthReport:
        return HealthReport(
            adapter=self.name,
            detected_version="test",
            enforcement_level=self.enforcement_level,
            healthy=True,
            supported_types=self.supported_types,
        )

    def invoke(self, *, capability_id: str, action: str, inputs: dict, permissions=None, timeout_s=None) -> AdapterResult:
        return AdapterResult(ok=True, output=json.dumps({"verdict": "pass", "findings": []}))


def register_executable_reasoner(root: Path, capability_id: str) -> None:
    source = root / f"{capability_id.replace('.', '_')}.txt"
    source.write_text("local review reasoner fixture\n", encoding="utf-8")
    register_adapter("test-reviewer", ReviewReasoner())
    CapabilityStore(root).upsert_capability(
        capability_id=capability_id,
        name=capability_id,
        type_="api_service",
        lifecycle="active",
        digest=inspect_source(source).digest,
        manifest={
            "schema": "shiroe.capability/v1",
            "id": capability_id,
            "name": capability_id,
            "type": "api_service",
            "version": "1.0.0",
            "source": {"kind": "file", "location": str(source)},
            "entrypoint": {"adapter": "test-reviewer", "url": "local://reviewer"},
            "requires": {},
        },
        source_kind="file",
        source_location=str(source),
    )


def test_independent_review_rejects_executor_capability(tmp_path):
    from shiroe.verification.review import run_independent_review

    capability_id = "test.reasoner"
    register_executable_reasoner(tmp_path, capability_id)
    with pytest.raises(ValueError, match="independent"):
        run_independent_review(
            tmp_path,
            node_id="n1",
            executor_capability_id=capability_id,
            reviewer_capability_id=capability_id,
        )


def test_independent_review_returns_verification_check(tmp_path):
    from shiroe.verification.review import run_independent_review

    register_executable_reasoner(tmp_path, "test.executor")
    register_executable_reasoner(tmp_path, "test.reviewer")

    check = run_independent_review(
        tmp_path,
        node_id="n1",
        executor_capability_id="test.executor",
        reviewer_capability_id="test.reviewer",
    )

    assert check.name == "independent_review"
    assert check.status.value == "pass"
