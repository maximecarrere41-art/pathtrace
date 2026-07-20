import json

import pytest

from pathtrace.engine.loader import (
    PathtraceFileNotFoundError,
    PathtraceInvalidContentError,
    PathtraceValidationError,
    find_latest_trace,
    load_tests,
    load_trace,
)


def test_load_trace_normalizes_v3_example():
    trace = load_trace("examples/trace-example.json")

    assert trace["version"] == 3
    assert trace["summary"]["skills"] == ["conventions-code"]
    assert len(trace["events"]) == 2


def test_load_trace_normalizes_legacy_fixture():
    trace = load_trace("tests/fixtures/valid-trace.json")

    assert trace["version"] == 3
    assert trace["events"]


def test_find_latest_trace_searches_recursively(tmp_path):
    first = tmp_path / "codex" / "s" / "one.json"
    second = tmp_path / "codex" / "s" / "two.json"
    first.parent.mkdir(parents=True)
    first.write_text("{}", encoding="utf-8")
    second.write_text("{}", encoding="utf-8")
    first.touch()
    second.touch()
    first_time = first.stat().st_mtime_ns
    second_time = first_time + 10_000_000
    import os
    os.utime(second, ns=(second_time, second_time))

    assert find_latest_trace(tmp_path) == second


def test_load_tests_accepts_structured_sequence_and_where_glob(tmp_path):
    path = tmp_path / "tests.yaml"
    path.write_text(
        """version: 1
tests:
  - name: orchestration
    assertions:
      - type: path_matches
        sequence:
          - event: tool_call:Bash
            where:
              command: '*pytest*'
""",
        encoding="utf-8",
    )

    suite = load_tests(path)
    assert suite["tests"][0]["assertions"][0]["sequence"][0]["where"]["command"] == "*pytest*"


def test_load_trace_raises_for_missing_file():
    with pytest.raises(PathtraceFileNotFoundError, match="Trace file not found"):
        load_trace("missing.json")


def test_load_trace_raises_for_invalid_json(tmp_path):
    path = tmp_path / "trace.json"
    path.write_text("{", encoding="utf-8")
    with pytest.raises(PathtraceInvalidContentError, match="Invalid JSON trace"):
        load_trace(path)


def test_load_tests_rejects_wrong_count_fields(tmp_path):
    path = tmp_path / "tests.yaml"
    path.write_text(
        """version: 1
tests:
  - name: count
    assertions:
      - type: min_occurrences
        event: tool_call:*
        min: 1
        max: 2
""",
        encoding="utf-8",
    )
    with pytest.raises(PathtraceValidationError, match="contains: max"):
        load_tests(path)
