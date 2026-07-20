from pathtrace.engine.assertions import evaluate_assertion


def test_must_include_returns_matching_indexes():
    result = evaluate_assertion(
        [_event("Read"), _event("Bash", command="python -m pytest")],
        {"type": "must_include", "event": "tool_call:Bash"},
    )

    assert result["passed"] is True
    assert result["matched_event_indexes"] == [1]


def test_where_supports_glob_for_commands():
    result = evaluate_assertion(
        [_event("Bash", command="python -m pytest tests/unit")],
        {
            "type": "must_include",
            "event": "tool_call:Bash",
            "where": {"command": "*pytest*"},
        },
    )

    assert result["passed"] is True


def test_must_not_include_marks_forbidden_event_as_failed():
    result = evaluate_assertion(
        [_event("Bash", command="rm -rf build")],
        {
            "type": "must_not_include",
            "event": "tool_call:Bash",
            "where": {"command": "*rm -rf*"},
        },
    )

    assert result["passed"] is False
    assert result["failed_event_indexes"] == [0]


def test_path_matches_returns_ordered_indexes():
    events = [
        {"type": "skill", "name": "conventions-code"},
        _event("Read"),
        _event("Bash", command="pytest"),
    ]
    result = evaluate_assertion(
        events,
        {
            "type": "path_matches",
            "sequence": [
                "skill:conventions-code",
                {"event": "tool_call:Bash", "where": {"command": "*pytest*"}},
            ],
        },
    )

    assert result["passed"] is True
    assert result["matched_event_indexes"] == [0, 2]


def test_no_direct_transition_marks_both_events():
    result = evaluate_assertion(
        [_event("Read"), _event("Bash")],
        {
            "type": "no_direct_transition",
            "from": "tool_call:Read",
            "to": "tool_call:Bash",
        },
    )

    assert result["passed"] is False
    assert result["failed_event_indexes"] == [0, 1]


def test_max_occurrences_marks_only_events_above_limit():
    result = evaluate_assertion(
        [_event("Read"), _event("Read"), _event("Read")],
        {"type": "max_occurrences", "event": "tool_call:Read", "max": 1},
    )

    assert result["passed"] is False
    assert result["failed_event_indexes"] == [1, 2]


def test_min_occurrences_fails_when_missing():
    result = evaluate_assertion(
        [_event("Read")],
        {"type": "min_occurrences", "event": "tool_call:Read", "min": 2},
    )

    assert result["passed"] is False


def test_status_equals_marks_only_wrong_statuses():
    result = evaluate_assertion(
        [_event("Read", status="success"), _event("Bash", status="failure")],
        {"type": "status_equals", "value": "success"},
    )

    assert result["failed_event_indexes"] == [1]


def test_question_mark_is_literal_not_wildcard():
    result = evaluate_assertion(
        [_event("githubx")],
        {"type": "must_include", "event": "tool_call:github?"},
    )

    assert result["passed"] is False


def test_custom_reason_is_used_on_failure():
    result = evaluate_assertion(
        [],
        {"type": "must_include", "event": "skill:pdfs", "reason": "skill requise"},
    )

    assert result["reason"] == "skill requise"


def _event(name, command=None, status=None):
    event = {"type": "tool_call", "name": name}
    if command:
        event["command"] = command
    if status:
        event["status"] = status
    return event
