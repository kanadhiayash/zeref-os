from shiroe.cli.main import registered_command_names


EXPECTED = {
    "init",
    "status",
    "plan",
    "run",
    "approve",
    "memory",
    "verify",
    "handoff",
    "doctor",
    "policy",
    "capability",
    "state",
    "version",
}


def test_cli_exposes_exact_top_level_surface():
    assert set(registered_command_names()) == EXPECTED
