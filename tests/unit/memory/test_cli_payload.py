from __future__ import annotations

from shiroe.cli.common import memory_write_from_payload


def test_cli_does_not_invent_evidence_grade() -> None:
    write = memory_write_from_payload(
        {
            "type": "decision",
            "title": "No evidence",
            "claim": "Caller must provide evidence.",
            "source_refs": ["user-input"],
        }
    )

    assert write.evidence_grade == ""
