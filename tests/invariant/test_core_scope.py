from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_core_scope_declares_operational_only_surface():
    text = (ROOT / "docs/architecture/CORE_SCOPE.md").read_text()
    assert "declared component must be executable" in text.lower()
    assert "first-party skills: 0" in text.lower()
    assert "work graph" in text.lower()


def test_agents_spec_declares_executable_only_runtime():
    text = (ROOT / "AGENTS.md").read_text()
    assert "Every declared component must be executable" in text
    assert "Work Graph" in text
    assert "approval_advisor" in text
