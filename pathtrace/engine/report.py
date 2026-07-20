"""Rapport terminal et rapport JSON exploitable par la visualisation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


TestResult = dict[str, Any]


def build_report(
    trace: dict[str, Any],
    test_suite: dict[str, Any],
    results: list[TestResult],
) -> dict[str, Any]:
    passed = sum(result["passed"] is True for result in results)
    failed = len(results) - passed
    return {
        "version": 1,
        "trace": {
            "id": trace.get("id"),
            "session_id": trace.get("session_id"),
            "turn_id": trace.get("turn_id"),
            "framework": trace.get("framework"),
            "model": trace.get("model"),
            "prompt": trace.get("prompt"),
            "summary": trace.get("summary", {}),
        },
        "outcome": {"passed": failed == 0},
        "summary": {
            "status": "passed" if failed == 0 else "failed",
            "passed": passed,
            "failed": failed,
        },
        "tests": [
            {
                "name": test.get("name", "Unnamed test"),
                "passed": result["passed"],
                "assertions": result["assertions"],
            }
            for test, result in zip(test_suite["tests"], results)
        ],
    }


def write_json_report(report: dict[str, Any], path: str | Path) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return output


def format_report(
    trace: dict[str, Any],
    test_suite: dict[str, Any],
    results: list[TestResult],
) -> str:
    lines = [
        f"Trace: {trace.get('framework', 'unknown')} / {trace.get('session_id', 'unknown')} / {trace.get('turn_id', 'unknown')}"
    ]
    passed_count = 0

    for test, result in zip(test_suite["tests"], results):
        passed = result["passed"] is True
        passed_count += passed
        lines.append(f"[{_status_label(passed)}] {test.get('name', 'Unnamed test')}")
        for assertion in result["assertions"]:
            if assertion["passed"] is False:
                lines.append(f"  Reason: {assertion['reason']}")

    failed_count = len(results) - passed_count
    lines.append(f"Summary: {passed_count} passed, {failed_count} failed")
    return "\n".join(lines)


def _status_label(passed: bool) -> str:
    return "\033[32mPASS\033[0m" if passed else "\033[31mFAIL\033[0m"
