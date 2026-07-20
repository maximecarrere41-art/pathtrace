"""Chargement et validation légère des traces et suites YAML."""

from __future__ import annotations

import glob
import json
from pathlib import Path
from typing import Any

import yaml

from pathtrace.model import normalize_trace


TESTS_REQUIRED_FIELDS = ("version", "tests")
RUN_SUITE_REQUIRED_FIELDS = ("version", "scenarios")


class PathtraceLoaderError(Exception):
    pass


class PathtraceFileNotFoundError(PathtraceLoaderError, FileNotFoundError):
    pass


class PathtraceInvalidContentError(PathtraceLoaderError, ValueError):
    pass


class PathtraceValidationError(PathtraceLoaderError, ValueError):
    pass


def load_trace(path: str | Path) -> dict[str, Any]:
    trace_path = _require_existing_file(path, "Trace file not found")
    data = _read_json(trace_path)
    _require_mapping(data, "Trace")
    trace = normalize_trace(data)
    _require_list(trace["events"], "Trace events")
    return trace


def load_tests(path: str | Path) -> dict[str, Any]:
    tests_path = _require_existing_file(path, "Tests file not found")
    data = _read_yaml(tests_path)
    validate_test_suite(data)
    return data


def validate_test_suite(data: Any) -> None:
    _require_mapping(data, "Tests file")
    _require_fields(data, TESTS_REQUIRED_FIELDS, "Tests file")
    _require_list(data["tests"], "Tests")
    _validate_tests_assertions(data["tests"])


def load_run_suite(path: str | Path) -> dict[str, Any]:
    suite_path = _require_existing_file(path, "Run suite file not found")
    data = _read_yaml(suite_path)
    _require_mapping(data, "Run suite")
    _require_fields(data, RUN_SUITE_REQUIRED_FIELDS, "Run suite")
    _require_list(data["scenarios"], "Run suite scenarios")
    _validate_run_defaults(data, "Run suite", allow_unknown=True)
    _validate_run_defaults(data.get("defaults"), "Run suite defaults")
    for index, scenario in enumerate(data["scenarios"]):
        _validate_run_scenario(scenario, f"Run suite scenarios[{index}]")
    return data


def discover_run_suites(inputs: tuple[str, ...] | list[str]) -> list[Path]:
    """Résout fichiers, dossiers et motifs glob vers des suites YAML uniques."""
    found: list[Path] = []
    for raw in inputs:
        path = Path(raw)
        if path.is_file():
            found.append(path)
            continue
        if path.is_dir():
            found.extend(path.rglob("*.yaml"))
            found.extend(path.rglob("*.yml"))
            continue
        found.extend(Path(match) for match in glob.glob(raw, recursive=True) if Path(match).is_file())

    yaml_files = [path for path in found if path.suffix.lower() in {".yaml", ".yml"}]
    unique = sorted({path.resolve() for path in yaml_files})
    if not unique:
        joined = ", ".join(inputs)
        raise PathtraceFileNotFoundError(f"No run suite found for: {joined}")
    return unique


def scenario_test_suite(scenario: dict[str, Any], suite_path: Path) -> dict[str, Any]:
    """Retourne la suite d'assertions inline ou référencée par le scénario."""
    if "assertions" in scenario:
        suite = {
            "version": 1,
            "tests": [
                {
                    "name": str(scenario["name"]),
                    "assertions": scenario["assertions"],
                }
            ],
        }
        validate_test_suite(suite)
        return suite

    tests_path = Path(str(scenario["tests_file"]))
    if not tests_path.is_absolute():
        tests_path = suite_path.parent / tests_path
    return load_tests(tests_path)


def find_latest_trace(root: str | Path = ".pathtrace/traces") -> Path:
    root_path = Path(root)
    candidates = [path for path in root_path.rglob("*.json") if path.is_file()]
    if not candidates:
        raise PathtraceFileNotFoundError(f"No trace found in: {root_path}")
    return max(candidates, key=lambda path: path.stat().st_mtime_ns)


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise PathtraceInvalidContentError(f"Invalid JSON trace: {path}") from error


def _read_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise PathtraceInvalidContentError(f"Invalid YAML file: {path}") from error


def _require_existing_file(path: str | Path, message: str) -> Path:
    file_path = Path(path)
    if not file_path.is_file():
        raise PathtraceFileNotFoundError(f"{message}: {file_path}")
    return file_path


def _require_mapping(data: Any, label: str) -> None:
    if not isinstance(data, dict):
        raise PathtraceValidationError(f"{label} must be a YAML/JSON object")


def _require_fields(data: dict, fields: tuple[str, ...], label: str) -> None:
    missing = [field for field in fields if field not in data]
    if missing:
        raise PathtraceValidationError(f"{label} is missing: {', '.join(missing)}")


def _require_list(value: Any, label: str) -> None:
    if not isinstance(value, list):
        raise PathtraceValidationError(f"{label} must be a list")


def _validate_tests_assertions(tests: list[Any]) -> None:
    for test_index, test in enumerate(tests):
        label = f"Tests[{test_index}]"
        _require_mapping(test, label)
        assertions = test.get("assertions", [])
        _require_list(assertions, f"{label} assertions")
        for assertion_index, assertion in enumerate(assertions):
            _validate_assertion(assertion, f"{label} assertions[{assertion_index}]")


def _validate_assertion(assertion: Any, label: str) -> None:
    _require_mapping(assertion, label)
    assertion_type = assertion.get("type")
    if assertion_type == "min_occurrences":
        _require_fields(assertion, ("min",), label)
        _forbid_fields(assertion, ("max",), label)
    if assertion_type == "max_occurrences":
        _require_fields(assertion, ("max",), label)
        _forbid_fields(assertion, ("min",), label)
    _validate_where(assertion.get("where"), f"{label} where")
    _validate_where(assertion.get("from_where"), f"{label} from_where")
    _validate_where(assertion.get("to_where"), f"{label} to_where")
    if assertion_type == "path_matches":
        _validate_sequence(assertion, label)


def _validate_sequence(assertion: dict, label: str) -> None:
    sequence = assertion.get("sequence", assertion.get("path"))
    _require_list(sequence, f"{label} sequence")
    for index, item in enumerate(sequence):
        if isinstance(item, str):
            continue
        _require_mapping(item, f"{label} sequence[{index}]")
        _require_fields(item, ("event",), f"{label} sequence[{index}]")
        _validate_where(item.get("where"), f"{label} sequence[{index}] where")


def _validate_where(where: Any, label: str) -> None:
    if where is None:
        return
    _require_mapping(where, label)
    if not all(isinstance(key, str) for key in where):
        raise PathtraceValidationError(f"{label} keys must be strings")


def _validate_run_scenario(scenario: Any, label: str) -> None:
    _require_mapping(scenario, label)
    _require_fields(scenario, ("name", "prompt"), label)
    if not isinstance(scenario["name"], str) or not scenario["name"].strip():
        raise PathtraceValidationError(f"{label} name must be a non-empty string")
    if not isinstance(scenario["prompt"], str) or not scenario["prompt"].strip():
        raise PathtraceValidationError(f"{label} prompt must be a non-empty string")

    sources = [field for field in ("assertions", "tests_file") if field in scenario]
    if len(sources) != 1:
        raise PathtraceValidationError(
            f"{label} must contain exactly one assertion source: assertions or tests_file"
        )
    if "assertions" in scenario:
        _require_list(scenario["assertions"], f"{label} assertions")
        _validate_tests_assertions([{"assertions": scenario["assertions"]}])
    if "tests_file" in scenario and not isinstance(scenario["tests_file"], str):
        raise PathtraceValidationError(f"{label} tests_file must be a string")

    _validate_run_defaults(scenario, label, allow_unknown=True)


def _validate_run_defaults(value: Any, label: str, allow_unknown: bool = False) -> None:
    if value is None:
        return
    _require_mapping(value, label)
    for field in ("project_dir", "framework", "executable"):
        if field in value and not isinstance(value[field], str):
            raise PathtraceValidationError(f"{label} {field} must be a string")
    for field in ("timeout", "trace_timeout"):
        if field in value and not _positive_number(value[field]):
            raise PathtraceValidationError(f"{label} {field} must be a positive number")
    if "runner_args" in value:
        _require_list(value["runner_args"], f"{label} runner_args")
        if not all(isinstance(item, str) for item in value["runner_args"]):
            raise PathtraceValidationError(f"{label} runner_args entries must be strings")


def _positive_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def _forbid_fields(data: dict, fields: tuple[str, ...], label: str) -> None:
    present = [field for field in fields if field in data]
    if present:
        raise PathtraceValidationError(f"{label} contains: {', '.join(present)}")
