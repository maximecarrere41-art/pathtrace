import json
import subprocess

from pathtrace.runners.base import RunRequest
from pathtrace.runners.codex import CodexRunner


def test_codex_runner_launches_prompt_and_finds_new_trace(tmp_path, monkeypatch):
    def fake_run(command, cwd, **kwargs):
        trace_path = cwd / ".pathtrace" / "traces" / "codex" / "session" / "turn.json"
        trace_path.parent.mkdir(parents=True)
        trace_path.write_text(
            json.dumps(
                {
                    "version": 3,
                    "session_id": "session",
                    "turn_id": "turn",
                    "prompt": "lance les tests",
                    "framework": "codex",
                    "events": [],
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = CodexRunner().run(
        RunRequest(
            prompt="lance les tests",
            project_dir=tmp_path,
            executable="codex-custom",
            runner_args=("--model", "test-model"),
            trace_timeout_seconds=0.2,
        )
    )

    assert result.process_passed is True
    assert result.command[:3] == ("codex-custom", "exec", "--json")
    assert result.command[-1] == "lance les tests"
    assert result.trace_path is not None


def test_codex_runner_returns_no_trace_when_hooks_do_not_write(tmp_path, monkeypatch):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(command, 0, stdout="ok", stderr=""),
    )

    result = CodexRunner().run(
        RunRequest(
            prompt="hello",
            project_dir=tmp_path,
            trace_timeout_seconds=0.01,
        )
    )

    assert result.exit_code == 0
    assert result.trace_path is None
