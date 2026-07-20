import json

from pathtrace.cli import cli

import json

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