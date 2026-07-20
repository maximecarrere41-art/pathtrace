import json

from click.testing import CliRunner

from pathtrace.cli import cli


def test_install_writes_codex_hooks(tmp_path, monkeypatch):
    codex_home = tmp_path / ".codex"
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(cli, ["install", "--framework", "codex"])

    assert result.exit_code == 0
    config = json.loads(
        (codex_home / "hooks.json").read_text(encoding="utf-8")
    )


def test_hook_receive_finalizes_trace(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    runner.invoke(
        cli,
        ["hook", "receive", "codex", "user-prompt-submit"],
        input=json.dumps({"session_id": "s", "turn_id": "t", "prompt": "hello"}),
    )
    result = runner.invoke(
        cli,
        ["hook", "receive", "codex", "stop"],
        input=json.dumps({"session_id": "s", "turn_id": "t"}),
    )

    assert result.exit_code == 0
    assert (tmp_path / ".pathtrace" / "traces" / "codex" / "s" / "t.json").is_file()


def test_test_command_writes_report_and_graph(tmp_path):
    trace = tmp_path / "trace.json"
    tests = tmp_path / "tests.yaml"
    trace.write_text(json.dumps(_trace()), encoding="utf-8")
    tests.write_text(_tests("*pytest*"), encoding="utf-8")

    result = CliRunner().invoke(
        cli,
        [
            "test",
            "--trace",
            str(trace),
            "--tests",
            str(tests),
            "--report",
            "--graph",
            "--output-dir",
            str(tmp_path / "out"),
        ],
    )

    assert result.exit_code == 0
    assert "Summary: 1 passed, 0 failed" in result.output
    assert list((tmp_path / "out" / "reports").glob("*.json"))
    assert list((tmp_path / "out" / "graphs").glob("*.html"))


def test_test_command_returns_one_on_failure_and_still_writes_graph(tmp_path):
    trace = tmp_path / "trace.json"
    tests = tmp_path / "tests.yaml"
    trace.write_text(json.dumps(_trace()), encoding="utf-8")
    tests.write_text(_tests("*dotnet test*"), encoding="utf-8")

    result = CliRunner().invoke(
        cli,
        [
            "test",
            "--trace",
            str(trace),
            "--tests",
            str(tests),
            "--graph",
            "--output-dir",
            str(tmp_path / "out"),
        ],
    )

    assert result.exit_code == 1
    assert list((tmp_path / "out" / "graphs").glob("*.html"))


def test_test_command_requires_exactly_one_trace_source(tmp_path):
    tests = tmp_path / "tests.yaml"
    tests.write_text(_tests("*pytest*"), encoding="utf-8")

    result = CliRunner().invoke(cli, ["test", "--tests", str(tests)])

    assert result.exit_code != 0
    assert "exactement une source" in result.output


def _trace():
    return {
        "version": 3,
        "id": "test:s:t",
        "session_id": "s",
        "turn_id": "t",
        "prompt": "run tests",
        "model": "m",
        "framework": "test",
        "status": "success",
        "summary": {"skills": [], "commands": ["pytest"], "tools": ["Bash"]},
        "events": [
            {
                "index": 0,
                "type": "tool_call",
                "name": "Bash",
                "command": "pytest",
                "status": "success",
            }
        ],
    }


def _tests(command):
    return f"""version: 1
tests:
  - name: CLI scenario
    assertions:
      - type: must_include
        event: tool_call:Bash
        where:
          command: '{command}'
"""


def test_run_command_executes_automated_suite(tmp_path, monkeypatch):
    from pathtrace.runners.base import RunResult

    class FakeRunner:
        def run(self, request):
            trace_path = (
                request.project_dir
                / ".pathtrace"
                / "traces"
                / "codex"
                / "s"
                / "t.json"
            )
            trace_path.parent.mkdir(parents=True, exist_ok=True)
            trace_path.write_text(json.dumps(_trace()), encoding="utf-8")
            return RunResult(
                command=("fake",),
                exit_code=0,
                stdout="",
                stderr="",
                duration_seconds=0.1,
                trace_path=trace_path,
            )

    campaign = tmp_path / "campaign.yaml"
    campaign.write_text(
        f"""version: 1
framework: codex
defaults:
  project_dir: '{tmp_path.as_posix()}'
scenarios:
  - name: automated
    prompt: run tests
    assertions:
      - type: must_include
        event: tool_call:Bash
        where:
          command: '*pytest*'
""",
        encoding="utf-8",
    )
    monkeypatch.setattr("pathtrace.campaign.get_runner", lambda name: FakeRunner())

    result = CliRunner().invoke(
        cli,
        ["run", "--tests", str(campaign), "--report", "--graph", "--output-dir", str(tmp_path / "out")],
    )

    assert result.exit_code == 0
    assert "Campaign summary: 1 passed, 0 failed" in result.output
