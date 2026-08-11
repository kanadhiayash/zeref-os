from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_contract_directories_are_absent():
    for rel in ("skills", "agents", "commands", "team-packs"):
        assert not (ROOT / rel).exists(), rel


def test_contract_registries_are_absent():
    assert not (ROOT / "shiroe-registry.json").exists()
    assert not (ROOT / "registry/shiroe-registry.schema.json").exists()


def test_no_contract_or_experimental_component_status_is_active():
    for path in (ROOT / "registry").glob("*.json"):
        text = path.read_text().lower()
        assert '"status": "contract"' not in text
        assert '"status": "experimental"' not in text
