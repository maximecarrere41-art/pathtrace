import json

from pathtrace.campaign import execute_run_suite
from pathtrace.runners.base import RunResult


class FakeRunner:
    def __init__(self, create_trace=True, exit_code=0):
        self.create_trace = create_trace
        self.exit_code = exit_code

    def run(self, request):
        trace_path = None
        if self.create_trace:
            trace_path = (
                request.project_dir
                / ".pathtrace"
                / "traces"
                / "codex"
                / "session"
                / "turn.json"
            )
            trace_path.parent.mkdir(parents=True, exist_ok=True)
            trace_path.write_text(
                json.dumps(
                    {
                        "version": 3,
                        "session_id": "session",
                        "turn_id": "turn",
                        "prompt": request.prompt,
                        "framework": "codex",
                        "model": "test",
                        "events": [
                            {
                                "type": "tool_call",
                                "name": "Bash",
                                "command": "python -m pytest",
                                "status": "success",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
        return RunResult(
            command=("fake", request.prompt),
            exit_code=self.exit_code,
            stdout="done",
            stderr="",
            duration_seconds=0.1,
            trace_path=trace_path,
        )


def _suite(path):
    path.write_text(
        """version: 1
framework: codex
defaults:
  project_dir: .
scenarios:
  - name: validation automatique
    prompt: Corrige puis lance les tests
    assertions:
      - type: must_include
        event: tool_call:Bash
        where:
          command: '*pytest*'
""",
        encoding="utf-8",
    )


def test_execute_run_suite_writes_reports_and_graphs(tmp_path, monkeypatch):
    suite = tmp_path / "campaign.yaml"
    _suite(suite)
    monkeypatch.setattr("pathtrace.campaign.get_runner", lambda name: FakeRunner())

    result = execute_run_suite(
        suite,
        output_dir=tmp_path / "out",
        write_report=True,
        write_graph=True,
    )

    assert result["summary"]["failed"] == 0
    scenario = result["scenarios"][0]
    assert scenario["passed"] is True
    assert (tmp_path / "out" / "campaigns" / "campaign.json").is_file()
    assert list((tmp_path / "out" / "graphs").glob("*.html"))


def test_execute_run_suite_fails_cleanly_when_trace_is_missing(tmp_path, monkeypatch):
    suite = tmp_path / "campaign.yaml"
    _suite(suite)
    monkeypatch.setattr("pathtrace.campaign.get_runner", lambda name: FakeRunner(create_trace=False))

    result = execute_run_suite(
        suite,
        output_dir=tmp_path / "out",
        write_graph=True,
    )

    assert result["summary"]["failed"] == 1
    assert "Aucune trace" in result["scenarios"][0]["error"]
    assert list((tmp_path / "out" / "graphs").glob("*.html"))
