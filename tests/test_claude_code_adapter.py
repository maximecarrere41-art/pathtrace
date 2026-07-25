import json

import pytest

from pathtrace.adapters.claude_code import (
    ClaudeCodeAdapter,
    PathtraceClaudeHookConfigError,
)


adapter = ClaudeCodeAdapter()


def test_install_preserves_existing_hooks_and_adds_managed_events(tmp_path, monkeypatch):
    claude_home = tmp_path / ".claude"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(claude_home))
    settings_path = claude_home / "settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(
        json.dumps(
            {
                "permissions": {"defaultMode": "plan"},
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Bash",
                            "hooks": [{"type": "command", "command": "existing hook"}],
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    path = adapter.install(tmp_path)

    config = json.loads(settings_path.read_text(encoding="utf-8"))
    assert path == settings_path
    assert config["permissions"] == {"defaultMode": "plan"}
    assert set(config["hooks"]) >= {
        "SessionStart",
        "SessionEnd",
        "UserPromptSubmit",
        "PreToolUse",
        "PostToolUse",
        "PostToolUseFailure",
        "Stop",
        "StopFailure",
    }
    commands = _commands(config, "PreToolUse")
    assert "existing hook" in commands
    assert "pathtrace hook receive claude-code pre-tool-use" in commands


def test_install_is_idempotent(tmp_path, monkeypatch):
    claude_home = tmp_path / ".claude"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(claude_home))

    adapter.install(tmp_path)
    adapter.install(tmp_path)

    config = json.loads((claude_home / "settings.json").read_text(encoding="utf-8"))
    assert _commands(config, "UserPromptSubmit").count(
        "pathtrace hook receive claude-code user-prompt-submit"
    ) == 1


def test_install_rejects_invalid_hooks_shape(tmp_path, monkeypatch):
    claude_home = tmp_path / ".claude"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(claude_home))
    claude_home.mkdir()
    (claude_home / "settings.json").write_text('{"hooks": []}', encoding="utf-8")

    with pytest.raises(PathtraceClaudeHookConfigError, match="hooks"):
        adapter.install(tmp_path)


def test_prompt_and_pre_post_hooks_create_one_command_event(tmp_path):
    adapter.handle(
        "session-start",
        {"session_id": "s1", "model": "claude-sonnet-test"},
        tmp_path,
    )
    adapter.handle(
        "user-prompt-submit",
        {"session_id": "s1", "turn_id": "t1", "prompt": "run tests"},
        tmp_path,
    )
    adapter.handle(
        "pre-tool-use",
        {
            "session_id": "s1",
            "tool_use_id": "call-1",
            "tool_name": "Bash",
            "tool_input": {"command": "python -m pytest"},
        },
        tmp_path,
    )
    adapter.handle(
        "post-tool-use",
        {
            "session_id": "s1",
            "tool_use_id": "call-1",
            "tool_name": "Bash",
            "tool_input": {"command": "python -m pytest"},
            "tool_response": {"success": True, "output": "12 passed"},
            "duration_ms": 42,
        },
        tmp_path,
    )

    output = adapter.handle("stop", {"session_id": "s1"}, tmp_path)
    trace = json.loads(output.read_text(encoding="utf-8"))

    assert trace["version"] == 3
    assert trace["framework"] == "claude-code"
    assert trace["prompt"] == "run tests"
    assert trace["model"] == "claude-sonnet-test"
    assert trace["turn_id"] == "t1"
    assert trace["summary"]["commands"] == ["python -m pytest"]
    assert trace["summary"]["tools"] == ["Bash"]
    assert len(trace["events"]) == 1
    assert trace["events"][0]["status"] == "success"
    assert trace["events"][0]["output_summary"] == "12 passed"
    assert trace["events"][0]["raw"]["duration_ms"] == 42
    assert not (
        tmp_path / ".pathtrace" / ".state" / "claude-code" / "s1" / "current.json"
    ).exists()


def test_failed_tool_is_correlated_and_marks_trace_as_failure(tmp_path):
    adapter.handle(
        "user-prompt-submit",
        {"session_id": "s1", "turn_id": "failed", "prompt": "run tests"},
        tmp_path,
    )
    adapter.handle(
        "pre-tool-use",
        {
            "session_id": "s1",
            "tool_use_id": "call-1",
            "tool_name": "Bash",
            "tool_input": {"command": "pytest"},
        },
        tmp_path,
    )
    adapter.handle(
        "post-tool-use-failure",
        {
            "session_id": "s1",
            "tool_use_id": "call-1",
            "tool_name": "Bash",
            "tool_input": {"command": "pytest"},
            "error": "exit code 1",
        },
        tmp_path,
    )

    output = adapter.handle("stop", {"session_id": "s1"}, tmp_path)
    trace = json.loads(output.read_text(encoding="utf-8"))

    assert trace["status"] == "failure"
    assert len(trace["events"]) == 1
    assert trace["events"][0]["status"] == "failure"
    assert trace["events"][0]["output_summary"] == "exit code 1"


def test_skill_is_extracted_from_claude_skill_path(tmp_path):
    adapter.handle(
        "user-prompt-submit",
        {"session_id": "s1", "turn_id": "skill", "prompt": "review"},
        tmp_path,
    )
    adapter.handle(
        "post-tool-use",
        {
            "session_id": "s1",
            "tool_name": "Read",
            "tool_input": {"file_path": ".claude/skills/code-review/SKILL.md"},
            "tool_response": {"success": True},
        },
        tmp_path,
    )

    output = adapter.handle("stop", {"session_id": "s1"}, tmp_path)
    trace = json.loads(output.read_text(encoding="utf-8"))

    assert trace["summary"]["skills"] == ["code-review"]
    assert trace["events"][0]["type"] == "skill"
    assert trace["events"][0]["name"] == "code-review"
    assert trace["events"][0]["tool"] == "Read"


def test_session_end_removes_persistent_session_state(tmp_path):
    adapter.handle(
        "session-start",
        {"session_id": "s1", "model": "claude-sonnet-test"},
        tmp_path,
    )

    adapter.handle("session-end", {"session_id": "s1"}, tmp_path)

    assert not (
        tmp_path / ".pathtrace" / ".state" / "claude-code" / "s1" / "session.json"
    ).exists()


def test_stop_failure_finalizes_trace_as_failure(tmp_path):
    adapter.handle(
        "user-prompt-submit",
        {"session_id": "s1", "turn_id": "api-error", "prompt": "hello"},
        tmp_path,
    )

    output = adapter.handle("stop-failure", {"session_id": "s1"}, tmp_path)
    trace = json.loads(output.read_text(encoding="utf-8"))

    assert trace["status"] == "failure"
    assert trace["events"] == []


def _commands(config, event_name):
    return [
        hook["command"]
        for entry in config["hooks"][event_name]
        for hook in entry["hooks"]
    ]
