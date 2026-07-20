import pytest

from pathtrace.engine.loader import (
    PathtraceValidationError,
    discover_run_suites,
    load_run_suite,
    scenario_test_suite,
)


def test_load_run_suite_accepts_inline_assertions(tmp_path):
    path = tmp_path / "campaign.yaml"
    path.write_text(
        """version: 1
framework: codex
scenarios:
  - name: run tests
    prompt: Lance les tests
    assertions:
      - type: must_include
        event: tool_call:Bash
""",
        encoding="utf-8",
    )

    suite = load_run_suite(path)
    tests = scenario_test_suite(suite["scenarios"][0], path)

    assert tests["tests"][0]["name"] == "run tests"


def test_run_scenario_can_reference_existing_tests_file(tmp_path):
    assertions = tmp_path / "assertions.yaml"
    assertions.write_text(
        """version: 1
tests:
  - name: validation
    assertions:
      - type: status_equals
        value: success
""",
        encoding="utf-8",
    )
    campaign = tmp_path / "campaign.yaml"
    campaign.write_text(
        """version: 1
framework: codex
scenarios:
  - name: reused
    prompt: Fais le travail
    tests_file: assertions.yaml
""",
        encoding="utf-8",
    )

    suite = load_run_suite(campaign)
    tests = scenario_test_suite(suite["scenarios"][0], campaign)

    assert tests["tests"][0]["name"] == "validation"


def test_run_suite_requires_exactly_one_assertion_source(tmp_path):
    path = tmp_path / "invalid.yaml"
    path.write_text(
        """version: 1
scenarios:
  - name: invalid
    prompt: hello
""",
        encoding="utf-8",
    )

    with pytest.raises(PathtraceValidationError, match="exactly one assertion source"):
        load_run_suite(path)


def test_discover_run_suites_accepts_directory(tmp_path):
    one = tmp_path / "one.yaml"
    two = tmp_path / "nested" / "two.yml"
    two.parent.mkdir()
    one.write_text("version: 1\nscenarios: []\n", encoding="utf-8")
    two.write_text("version: 1\nscenarios: []\n", encoding="utf-8")

    assert discover_run_suites((str(tmp_path),)) == sorted([one.resolve(), two.resolve()])
