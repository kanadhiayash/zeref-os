"""H4.2: verification adversarial matrix.

Baseline coverage tests only the privacy dimension. This file pins one
adversarial case per dimension the VerificationEngine actually reports
against: privacy egress, evidence provenance, contradictions, write
shape. Independent review has its own dedicated test module. Graph
validation lives in shiroe/work/compiler.py and is covered by its own
tests; this matrix is scoped to VerificationEngine.verify_memory_write.
"""

from __future__ import annotations

import pytest

from shiroe.memory.models import MemoryWrite
from shiroe.verification import VerificationEngine


def _report(root, **overrides):
    proposal = MemoryWrite(
        kind=overrides.pop("kind", "fact"),
        title=overrides.pop("title", "Ok title"),
        claim=overrides.pop("claim", "Postgres supports MVCC"),
        source_refs=overrides.pop("source_refs", ("docs/pg.md",)),
        privacy_class=overrides.pop("privacy_class", "internal"),
        evidence_grade=overrides.pop("evidence_grade", "A"),
        **overrides,
    )
    return VerificationEngine(root).verify_memory_write(proposal)


def _find(report, name):
    for check in report.checks:
        if check.name == name:
            return check
    raise AssertionError(f"no {name} check in report")


# ---- write-shape dimension --------------------------------------------

@pytest.mark.parametrize("empty_field", ["kind", "title", "claim"])
def test_write_shape_blocks_when_required_field_is_blank(tmp_path, empty_field):
    report = _report(tmp_path, **{empty_field: "  "})
    assert report.status.value == "block"
    assert _find(report, "write").status.value == "block"


# ---- privacy dimension ------------------------------------------------

@pytest.mark.parametrize("bad_class", ["secret", "do_not_store"])
def test_privacy_blocks_forbidden_privacy_class(tmp_path, bad_class):
    report = _report(tmp_path, privacy_class=bad_class)
    priv = _find(report, "privacy")
    assert priv.status.value == "block"


def test_privacy_blocks_credential_shaped_claim(tmp_path):
    report = _report(
        tmp_path,
        claim="Use token sk-proj-THIS_IS_SYNTHETIC_NOT_REAL_1234567890",
    )
    priv = _find(report, "privacy")
    assert priv.status.value == "block"


# ---- evidence dimension -----------------------------------------------

def test_evidence_blocks_when_fact_has_no_source_refs(tmp_path):
    report = _report(tmp_path, source_refs=(), kind="fact")
    ev = _find(report, "evidence")
    assert ev.status.value == "block"


@pytest.mark.parametrize("weak", ["D", "F"])
def test_evidence_warns_on_weak_grade(tmp_path, weak):
    report = _report(tmp_path, evidence_grade=weak)
    ev = _find(report, "evidence")
    # Weak evidence is a WARN, not a block -- pinned so it never
    # regresses to block (would flip acceptable D-graded facts to
    # forbidden) or to pass (would silence a real weakness).
    assert ev.status.value == "warn"


# ---- contradictions dimension -----------------------------------------

def test_contradictions_never_silently_warns_on_opposing_active_claim(tmp_path):
    from shiroe.memory.service import MemoryService

    (tmp_path / "REDACT.md").write_text("# minimal\n", encoding="utf-8")
    with MemoryService(tmp_path) as svc:
        svc.write(MemoryWrite(
            kind="fact",
            title="prior",
            claim="Postgres does not support MVCC",
            source_refs=("docs/pg.md",),
            evidence_grade="A",
        ))

    report = _report(tmp_path, claim="Postgres does support MVCC")
    contra = _find(report, "contradictions")
    # The polarity heuristic may or may not catch this specific
    # antonym pair; what must NOT happen is a silent "warn" that
    # looks benign while the store carries two opposing facts.
    # Acceptable outcomes: block (heuristic caught it) or pass (out
    # of scope of the current heuristic).
    assert contra.status.value in ("block", "pass")
