from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_legacy_execution_models_are_absent():
    for rel in (
        "missions",
        "shiroe/missions",
        "shiroe/teams",
        "shiroe/loops",
        "shiroe/execution_policies",
        "shiroe/graph",
    ):
        assert not (ROOT / rel).exists(), rel
    # `shiroe/runtime` is a live, plan-approved module (Task B1 runtime
    # disclosure report); it is not a legacy execution model.


def test_work_execution_model_exists():
    assert (ROOT / "shiroe/work").is_dir()
    assert (ROOT / "shiroe/execution").is_dir()
