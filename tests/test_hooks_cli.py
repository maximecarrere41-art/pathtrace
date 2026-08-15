import json
import os
import shutil
import subprocess
from pathlib import Path

from click.testing import CliRunner

from pathtrace.cli import cli


def test_stop_hook_creates_trace_and_returns_json(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    result = runner.invoke(
        cli,
        ["hook", "receive", "codex", "stop"],
        input='{"session_id":"s1","turn_id":"t1"}',
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {}

    traces = list(
        (tmp_path / ".pathtrace" / "traces").rglob("*.json")
    )
    assert traces

def test_stop_hook_outputs_valid_json(monkeypatch):
    runner = CliRunner()

    class FakeAdapter:
        def handle(self, event_slug, payload, cwd):
            return "trace.json"

    monkeypatch.setattr(
        "pathtrace.cli.get_adapter",
        lambda _: FakeAdapter(),
    )

    result = runner.invoke(
        cli,
        ["hook", "receive", "codex", "stop"],
        input='{"session_id":"s1","turn_id":"t1"}',
    )

    assert result.exit_code == 0
    assert json.loads(result.output) == {}


def test_codex_hook_subprocesses_preserve_utf8_transcript_text(tmp_path):
    session_id = "windows-session"
    turn_id = "windows-turn"
    call_id = "exec-with-utf8-output"
    prompt = "dépôt, été, création, sécurité"
    output = "Résumé créé — texte littéral déjà valide : dÃ©jà"
    transcript_path = tmp_path / "rollout.jsonl"
    transcript_path.write_text(
        "\n".join(
            json.dumps(record, ensure_ascii=False)
            for record in (
                {
                    "type": "event_msg",
                    "payload": {
                        "type": "item_completed",
                        "turn_id": turn_id,
                        "item": {
                            "type": "UserMessage",
                            "content": [{"type": "text", "text": prompt}],
                        },
                    },
                },
                {
                    "type": "event_msg",
                    "payload": {
                        "type": "item_completed",
                        "turn_id": turn_id,
                        "item": {
                            "type": "CommandExecution",
                            "id": call_id,
                            "aggregated_output": output,
                        },
                    },
                },
            )
        )
        + "\n",
        encoding="utf-8",
    )
    common = {
        "session_id": session_id,
        "turn_id": turn_id,
        "transcript_path": str(transcript_path),
    }

    _run_codex_hook(
        tmp_path,
        "user-prompt-submit",
        {**common, "prompt": _as_windows_mojibake(prompt)},
    )
    _run_codex_hook(
        tmp_path,
        "post-tool-use",
        {
            **common,
            "tool_use_id": call_id,
            "tool_name": "Bash",
            "tool_input": {"command": "tool producing UTF-8"},
            "tool_response": _as_windows_mojibake(output),
        },
    )
    _run_codex_hook(tmp_path, "stop", common)

    trace_path = (
        tmp_path
        / ".pathtrace"
        / "traces"
        / "codex"
        / session_id
        / f"{turn_id}.json"
    )
    trace = json.loads(trace_path.read_text(encoding="utf-8"))

    assert trace["prompt"] == prompt
    assert trace["events"][0]["output_summary"] == output


def _run_codex_hook(tmp_path: Path, event_slug: str, payload: dict) -> None:
    pathtrace_executable = shutil.which("pathtrace")
    assert pathtrace_executable is not None
    hook_command = [
        pathtrace_executable,
        "hook",
        "receive",
        "codex",
        event_slug,
    ]
    if os.name == "nt":
        command = [
            os.environ.get("COMSPEC", "cmd.exe"),
            "/D",
            "/C",
            subprocess.list2cmdline(hook_command),
        ]
    else:
        command = hook_command
    environment = os.environ.copy()
    repository_root = str(Path(__file__).parents[1])
    environment["PYTHONPATH"] = os.pathsep.join(
        value
        for value in (repository_root, environment.get("PYTHONPATH"))
        if value
    )

    result = subprocess.run(
        command,
        input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")


def _as_windows_mojibake(value: str) -> str:
    return value.encode("utf-8").decode("cp1252")
