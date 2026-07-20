"""Assertions déclaratives appliquées à la liste d'événements canonique."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any


AssertionResult = dict[str, Any]
AssertionHandler = Callable[[list[dict[str, Any]], dict[str, Any]], AssertionResult]


def evaluate_assertion(events: list[dict[str, Any]], assertion: dict[str, Any]) -> AssertionResult:
    handler = ASSERTION_HANDLERS.get(assertion.get("type"))
    if handler is None:
        return _result(False, assertion, f"Unsupported assertion type: {assertion.get('type')}")
    return handler(events, assertion)


def must_include(events: list[dict], assertion: dict) -> AssertionResult:
    matcher = _assertion_matcher(assertion)
    if matcher is None:
        return _result(False, assertion, "must_include requires a string event pattern")
    indexes = _matching_indexes(events, matcher)
    if indexes:
        return _result(True, assertion, f"Event matching {matcher['event']} was found", indexes)
    return _failed_for_assertion(assertion, f"No event matches {matcher['event']}")


def must_not_include(events: list[dict], assertion: dict) -> AssertionResult:
    matcher = _assertion_matcher(assertion)
    if matcher is None:
        return _result(False, assertion, "must_not_include requires a string event pattern")
    indexes = _matching_indexes(events, matcher)
    if not indexes:
        return _result(True, assertion, f"No event matches {matcher['event']}")
    return _failed_for_assertion(
        assertion,
        f"An event matches {matcher['event']}",
        matched=indexes,
        failed=indexes,
    )


def path_matches(events: list[dict], assertion: dict) -> AssertionResult:
    matchers = _sequence_matchers(assertion)
    if matchers is None:
        return _result(False, assertion, "path_matches requires a non-empty sequence")
    indexes = _sequence_indexes(events, matchers)
    if indexes is not None:
        return _result(True, assertion, "Path contains the expected sequence", indexes)
    return _failed_for_assertion(assertion, "Path does not contain the expected sequence")


def no_direct_transition(events: list[dict], assertion: dict) -> AssertionResult:
    left = _transition_matcher(assertion, "from", "from_where")
    right = _transition_matcher(assertion, "to", "to_where")
    if left is None or right is None:
        return _result(False, assertion, "no_direct_transition requires string from and to patterns")
    indexes = _direct_transition_indexes(events, left, right)
    if indexes is None:
        return _result(True, assertion, "Forbidden direct transition was not found")
    return _failed_for_assertion(
        assertion,
        "Forbidden direct transition was found",
        matched=indexes,
        failed=indexes,
    )


def max_occurrences(events: list[dict], assertion: dict) -> AssertionResult:
    matcher = _assertion_matcher(assertion)
    maximum = assertion.get("max")
    if matcher is None or not _is_count(maximum):
        return _result(False, assertion, "max_occurrences requires event and non-negative max")
    indexes = _matching_indexes(events, matcher)
    if len(indexes) <= maximum:
        return _result(True, assertion, f"{len(indexes)} event(s), within maximum {maximum}", indexes)
    return _failed_for_assertion(
        assertion,
        f"{len(indexes)} event(s), exceeding maximum {maximum}",
        matched=indexes,
        failed=indexes[maximum:],
    )


def min_occurrences(events: list[dict], assertion: dict) -> AssertionResult:
    matcher = _assertion_matcher(assertion)
    minimum = assertion.get("min")
    if matcher is None or not _is_count(minimum):
        return _result(False, assertion, "min_occurrences requires event and non-negative min")
    indexes = _matching_indexes(events, matcher)
    if len(indexes) >= minimum:
        return _result(True, assertion, f"{len(indexes)} event(s), meeting minimum {minimum}", indexes)
    return _failed_for_assertion(
        assertion,
        f"{len(indexes)} event(s), below minimum {minimum}",
        matched=indexes,
    )


def status_equals(events: list[dict], assertion: dict) -> AssertionResult:
    expected = assertion.get("value")
    if not isinstance(expected, str):
        return _result(False, assertion, "status_equals requires a string value")
    checked = [index for index, event in enumerate(events) if "status" in event]
    failed = [index for index in checked if events[index].get("status") != expected]
    if not failed:
        return _result(True, assertion, f"All event statuses equal {expected}", checked)
    return _failed_for_assertion(
        assertion,
        f"At least one status differs from {expected}",
        matched=checked,
        failed=failed,
    )


def _assertion_matcher(assertion: dict) -> dict | None:
    event = assertion.get("event")
    if not isinstance(event, str):
        return None
    return {"event": event, "where": assertion.get("where", {})}


def _sequence_matchers(assertion: dict) -> list[dict] | None:
    sequence = assertion.get("sequence", assertion.get("path"))
    if not isinstance(sequence, list) or not sequence:
        return None
    matchers = [_normalize_matcher(item) for item in sequence]
    return matchers if all(matchers) else None


def _normalize_matcher(value: object) -> dict | None:
    if isinstance(value, str):
        return {"event": value, "where": {}}
    if not isinstance(value, dict) or not isinstance(value.get("event"), str):
        return None
    return {"event": value["event"], "where": value.get("where", {})}


def _transition_matcher(assertion: dict, event_key: str, where_key: str) -> dict | None:
    event = assertion.get(event_key)
    if not isinstance(event, str):
        return None
    return {"event": event, "where": assertion.get(where_key, {})}


def _sequence_indexes(events: list[dict], matchers: list[dict]) -> list[int] | None:
    found: list[int] = []
    start = 0
    for matcher in matchers:
        index = _find_next(events, matcher, start)
        if index < 0:
            return None
        found.append(index)
        start = index + 1
    return found


def _find_next(events: list[dict], matcher: dict, start: int) -> int:
    for index in range(start, len(events)):
        if _event_matches(events[index], matcher):
            return index
    return -1


def _direct_transition_indexes(events: list[dict], left: dict, right: dict) -> list[int] | None:
    for index, (current, next_event) in enumerate(zip(events, events[1:])):
        if _event_matches(current, left) and _event_matches(next_event, right):
            return [index, index + 1]
    return None


def _matching_indexes(events: list[dict], matcher: dict) -> list[int]:
    return [index for index, event in enumerate(events) if _event_matches(event, matcher)]


def _event_matches(event: dict, matcher: dict) -> bool:
    event_type = event.get("type")
    event_name = event.get("name")
    if not isinstance(event_type, str) or not isinstance(event_name, str):
        return False
    return _matches_glob(f"{event_type}:{event_name}", matcher["event"]) and _matches_where(
        event, matcher["where"]
    )


def _matches_where(event: dict, where: object) -> bool:
    if not isinstance(where, dict):
        return False
    return all(_value_matches(_nested_value(event, path), expected) for path, expected in where.items())


def _value_matches(actual: object, expected: object) -> bool:
    if isinstance(expected, str) and "*" in expected:
        return _matches_glob(str(actual or ""), expected)
    return actual == expected


def _nested_value(data: dict, path: str) -> object:
    value: object = data
    for part in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _matches_glob(value: str, pattern: str) -> bool:
    expression = ".*".join(re.escape(part) for part in pattern.split("*"))
    return re.fullmatch(expression, value) is not None


def _is_count(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _result(
    passed: bool,
    assertion: dict[str, Any],
    reason: str,
    matched: list[int] | None = None,
    failed: list[int] | None = None,
) -> AssertionResult:
    return {
        "passed": passed,
        "type": assertion.get("type", "unknown"),
        "expected": _expected(assertion),
        "reason": reason,
        "matched_event_indexes": matched or [],
        "failed_event_indexes": failed or [],
    }


def _failed_for_assertion(
    assertion: dict[str, Any],
    fallback: str,
    matched: list[int] | None = None,
    failed: list[int] | None = None,
) -> AssertionResult:
    custom_reason = assertion.get("reason")
    reason = custom_reason if isinstance(custom_reason, str) else fallback
    return _result(False, assertion, reason, matched, failed)


def _expected(assertion: dict[str, Any]) -> dict[str, Any]:
    ignored = {"reason"}
    return {key: value for key, value in assertion.items() if key not in ignored}


ASSERTION_HANDLERS: dict[str, AssertionHandler] = {
    "must_include": must_include,
    "must_not_include": must_not_include,
    "path_matches": path_matches,
    "no_direct_transition": no_direct_transition,
    "max_occurrences": max_occurrences,
    "min_occurrences": min_occurrences,
    "status_equals": status_equals,
}
