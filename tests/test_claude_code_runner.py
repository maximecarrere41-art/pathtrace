import json
import subprocess

import pytest

from pathtrace.runners import available_runners, get_runner
from pathtrace.runners.base import AgentRunner, RunRequest, RunnerExecutionError
from pathtrace.runners.claude_code import ClaudeCodeRunner


def test_registry_exposes_claude_code_runner():
    assert available_runners() == ("claude-code", "codex")
    assert isinstance(get_runner("claude-code"), AgentRunner)


def test_claude_runner_launches_prompt_and_finds_matching_trace(tmp_path, monkeypatch):
    def fake_run(command, cwd, **kwargs):
        other = cwd / ".pathtrace" / "traces" / "claude-code" / "other" / "turn.json"
        other.parent.mkdir(parents=True)
        other.write_text(
            json.dumps({"session_id": "other", "prompt": "same prompt"}),
            encoding="utf-8",
        )
        trace_path = cwd / ".pathtrace" / "traces" / "claude-code" / "session" / "turn.json"
        trace_path.parent.mkdir(parents=True)
        trace_path.write_text(
            json.dumps(
                {
                    "version": 3,
                    "session_id": "session",
                    "turn_id": "turn",
                    "prompt": "same prompt",
                    "framework": "claude-code",
                    "events": [],
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps({"result": "ok", "session_id": "session"}),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = ClaudeCodeRunner().run(
        RunRequest(
            prompt="same prompt",
            project_dir=tmp_path,
            executable="claude-custom",
            runner_args=("--model", "sonnet"),
            trace_timeout_seconds=0.2,
        )
    )

    assert result.process_passed is True
    assert result.command == (
        "claude-custom",
        "-p",
        "--model",
        "sonnet",
        "--output-format",
        "json",
        "same prompt",
    )
    assert result.trace_path is not None
    assert result.trace_path.parent.name == "session"


def test_claude_runner_uses_environment_executable(tmp_path, monkeypatch):
    monkeypatch.setenv("PATHTRACE_CLAUDE_CODE_EXECUTABLE", "claude-env")
    request = RunRequest(prompt="hello", project_dir=tmp_path)

    command = ClaudeCodeRunner().build_command(request)

    assert command[0] == "claude-env"


def test_claude_runner_rejects_bare_mode(tmp_path):
    request = RunRequest(prompt="hello", project_dir=tmp_path, runner_args=("--bare",))

    with pytest.raises(RunnerExecutionError, match="désactive les hooks"):
        ClaudeCodeRunner().build_command(request)


def test_claude_runner_returns_no_trace_when_hooks_do_not_write(tmp_path, monkeypatch):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps({"session_id": "session"}),
            stderr="",
        ),
    )

    result = ClaudeCodeRunner().run(
        RunRequest(
            prompt="hello",
            project_dir=tmp_path,
            trace_timeout_seconds=0.01,
        )
    )

    assert result.exit_code == 0
    assert result.trace_path is None
