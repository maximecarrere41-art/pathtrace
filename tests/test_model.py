from pathtrace.model import build_trace, normalize_trace


def test_build_trace_exposes_simple_summary():
    trace = build_trace(
        framework="codex",
        session_id="s",
        turn_id="t",
        prompt="p",
        model="m",
        events=[
            {"type": "skill", "name": "pdfs", "tool": "Read"},
            {"type": "tool_call", "name": "Bash", "command": "pytest"},
            {"type": "tool_call", "name": "Bash", "command": "pytest"},
        ],
    )

    assert trace["summary"] == {
        "skills": ["pdfs"],
        "commands": ["pytest"],
        "tools": ["Read", "Bash"],
    }
    assert [event["index"] for event in trace["events"]] == [0, 1, 2]


def test_normalize_trace_reads_legacy_v2_tools_list():
    trace = normalize_trace(
        {
            "prompt": "legacy",
            "model": "m",
            "framework": "codex",
            "session_id": "s",
            "tools": [{"type": "tool_call", "name": "Read"}],
        }
    )

    assert trace["version"] == 3
    assert trace["events"][0]["name"] == "Read"
    assert trace["summary"]["tools"] == ["Read"]
