from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_core_scope_declares_operational_only_surface():
    text = (ROOT / "docs/architecture/CORE_SCOPE.md").read_text()
    assert "declared component must be executable" in text.lower()
    assert "first-party skills: 0" in text.lower()
    assert "work graph" in text.lower()


def test_agents_spec_no_longer_declares_contract_skills_or_team_packs():
    text = (ROOT / "AGENTS.md").read_text()
    for removed in (
        "budget-governor",
        "skill-router",
        "fleet-activator",
        "pattern-to-skill",
        "Team Packs",
    ):
        assert removed not in text
