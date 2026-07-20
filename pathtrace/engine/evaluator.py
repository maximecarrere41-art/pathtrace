"""Évaluation d'une suite de tests contre une trace canonique."""

from __future__ import annotations

from typing import Any

from pathtrace.engine.assertions import evaluate_assertion
from pathtrace.engine.report import TestResult


def evaluate_test_suite(trace: dict[str, Any], test_suite: dict[str, Any]) -> list[TestResult]:
    return [_evaluate_test(trace["events"], test) for test in test_suite["tests"]]


def _evaluate_test(events: list[dict[str, Any]], test: dict[str, Any]) -> TestResult:
    assertions = [evaluate_assertion(events, assertion) for assertion in test["assertions"]]
    return {"passed": all(result["passed"] is True for result in assertions), "assertions": assertions}
