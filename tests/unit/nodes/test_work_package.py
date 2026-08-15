from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from shiroe.nodes.protocol import (
    WorkPackageError,
    make_work_package,
    validate_work_package,
)


NOW = datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)


def _package_dict() -> dict:
    return make_work_package(
        package_id="pkg_1",
        graph_id="graph1",
        work_node_id="work1",
        lease_id="lease_1",
        worker_node_id="node_worker",
        capability_id="cap.remote",
        capability_digest="sha256:cap",
        inputs={"x": 1},
        timeout_s=30,
        created_at=NOW,
        expires_at=NOW + timedelta(minutes=5),
    ).to_dict()


def test_validate_work_package_accepts_matching_digest_and_identity() -> None:
    package = validate_work_package(
        _package_dict(),
        worker_node_id="node_worker",
        capability_digest="sha256:cap",
        now=NOW,
    )

    assert package.worker_node_id == "node_worker"
    assert package.digest.startswith("sha256:")


def test_work_package_rejects_body_digest_tamper() -> None:
    data = _package_dict()
    data["inputs"] = {"x": 2}

    with pytest.raises(WorkPackageError, match="digest"):
        validate_work_package(
            data,
            worker_node_id="node_worker",
            capability_digest="sha256:cap",
            now=NOW,
        )


def test_work_package_rejects_wrong_worker_or_capability_digest() -> None:
    with pytest.raises(WorkPackageError, match="worker"):
        validate_work_package(
            _package_dict(),
            worker_node_id="node_other",
            capability_digest="sha256:cap",
            now=NOW,
        )

    with pytest.raises(WorkPackageError, match="capability digest"):
        validate_work_package(
            _package_dict(),
            worker_node_id="node_worker",
            capability_digest="sha256:other",
            now=NOW,
        )


def test_work_package_rejects_expired_package() -> None:
    with pytest.raises(WorkPackageError, match="expired"):
        validate_work_package(
            _package_dict(),
            worker_node_id="node_worker",
            capability_digest="sha256:cap",
            now=NOW + timedelta(minutes=10),
        )
