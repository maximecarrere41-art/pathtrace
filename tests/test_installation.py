import json

import pytest
import yaml
from click.testing import CliRunner

from pathtrace.cli import cli


def test_install_security_only_creates_minimal_local_config_and_pre_tool_hook(
    tmp_path, monkeypatch
):
    codex_home = tmp_path / "codex-home"
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        cli, ["install", "security", "--framework", "codex"]
    )

    assert result.exit_code == 0, result.output
    config = yaml.safe_load(
        (tmp_path / ".pathtrace" / "config.yaml").read_text(encoding="utf-8")
    )
    assert config["features"] == ["security"]
    assert config["frameworks"] == {"codex": ["security"]}
    assert config["security"] == {
        "mode": "enforce",
        "rules": [],
        "telemetry": {"enabled": False},
    }
    hooks = json.loads(
        (codex_home / "hooks.json").read_text(encoding="utf-8")
    )["hooks"]
    assert set(hooks) == {"PreToolUse"}
    command = hooks["PreToolUse"][0]["hooks"][0]["command"]
    assert command.endswith(
        "pre-tool-use --configured-only --security-enabled"
    )
    assert not (tmp_path / ".pathtrace" / ".state").exists()
    assert not (tmp_path / ".pathtrace" / "traces").exists()
    assert [path.name for path in (tmp_path / ".pathtrace").iterdir()] == [
        "config.yaml"
    ]


def test_install_observe_keeps_the_historical_cli_syntax(tmp_path, monkeypatch):
    codex_home = tmp_path / "codex-home"
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(cli, ["install", "--framework", "codex"])

    assert result.exit_code == 0, result.output
    config = yaml.safe_load(
        (tmp_path / ".pathtrace" / "config.yaml").read_text(encoding="utf-8")
    )
    assert config == {
        "version": 1,
        "features": ["observe"],
        "frameworks": {"codex": ["observe"]},
    }


def test_install_all_enables_both_features(tmp_path, monkeypatch):
    claude_home = tmp_path / "claude-home"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(claude_home))
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        cli, ["install", "all", "--framework", "claude-code"]
    )

    assert result.exit_code == 0, result.output
    config = yaml.safe_load(
        (tmp_path / ".pathtrace" / "config.yaml").read_text(encoding="utf-8")
    )
    assert config["features"] == ["observe", "security"]
    assert config["frameworks"] == {
        "claude-code": ["observe", "security"]
    }
    hooks = json.loads(
        (claude_home / "settings.json").read_text(encoding="utf-8")
    )["hooks"]
    assert "PreToolUse" in hooks
    assert "Stop" in hooks


def test_installations_merge_and_are_idempotent(tmp_path, monkeypatch):
    codex_home = tmp_path / "codex-home"
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    first = runner.invoke(cli, ["install", "security", "--framework", "codex"])
    second = runner.invoke(cli, ["install", "observe", "--framework", "codex"])
    config_path = tmp_path / ".pathtrace" / "config.yaml"
    before_repeat = config_path.read_text(encoding="utf-8")
    repeated = runner.invoke(cli, ["install", "observe", "--framework", "codex"])

    assert first.exit_code == second.exit_code == repeated.exit_code == 0
    assert yaml.safe_load(before_repeat)["features"] == ["observe", "security"]
    assert config_path.read_text(encoding="utf-8") == before_repeat
    hooks = json.loads(
        (codex_home / "hooks.json").read_text(encoding="utf-8")
    )
    commands = [
        hook["command"]
        for entry in hooks["hooks"]["PreToolUse"]
        for hook in entry["hooks"]
    ]
    assert commands.count(
        "pathtrace hook receive codex pre-tool-use --security-enabled"
    ) == 1
    assert not any("--configured-only" in command for command in commands)


def test_observe_then_security_keeps_both_capabilities(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex-home"))
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    observe = runner.invoke(cli, ["install", "observe", "--framework", "codex"])
    security = runner.invoke(cli, ["install", "security", "--framework", "codex"])

    assert observe.exit_code == security.exit_code == 0
    config = yaml.safe_load(
        (tmp_path / ".pathtrace" / "config.yaml").read_text(encoding="utf-8")
    )
    assert config["features"] == ["observe", "security"]


def test_status_describes_local_activation(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex-home"))
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    runner.invoke(cli, ["install", "security", "--framework", "codex"])

    result = runner.invoke(cli, ["status"])

    assert result.exit_code == 0
    assert "Features: security" in result.output
    assert "Security mode: enforce" in result.output
    assert "Security telemetry: disabled" in result.output


def test_repeated_install_preserves_equivalent_user_formatted_config(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex-home"))
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / ".pathtrace" / "config.yaml"
    config_path.parent.mkdir()
    original = """# keep this comment
version: 1
features: [observe]
"""
    config_path.write_text(original, encoding="utf-8")

    result = CliRunner().invoke(cli, ["install", "observe", "--framework", "codex"])

    assert result.exit_code == 0
    assert config_path.read_text(encoding="utf-8") == original


def test_security_only_hook_is_noop_outside_an_activated_repository(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    payload = json.dumps(
        {
            "session_id": "s",
            "turn_id": "t",
            "tool_name": "Bash",
            "tool_input": {"command": "python -m pytest"},
        }
    )

    result = CliRunner().invoke(
        cli,
        [
            "hook",
            "receive",
            "codex",
            "pre-tool-use",
            "--configured-only",
        ],
        input=payload,
    )

    assert result.exit_code == 0
    assert result.output == ""
    assert not (tmp_path / ".pathtrace").exists()


def test_features_are_scoped_to_the_framework_whose_hooks_are_installed(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex-home"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude-home"))
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    security = runner.invoke(
        cli,
        ["install", "security", "--framework", "codex"],
    )
    observe = runner.invoke(
        cli,
        ["install", "observe", "--framework", "claude-code"],
    )

    assert security.exit_code == observe.exit_code == 0
    config_path = tmp_path / ".pathtrace" / "config.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert config["frameworks"] == {
        "claude-code": ["observe"],
        "codex": ["security"],
    }
    config["security"]["rules"] = [
        {
            "id": "block-shell",
            "action": "shell",
            "decision": "block",
            "match": {"command": "*"},
            "reason": "Configured policy",
        }
    ]
    config_path.write_text(
        yaml.safe_dump(config, sort_keys=False),
        encoding="utf-8",
    )
    payload = json.dumps(
        {
            "session_id": "s",
            "turn_id": "t",
            "tool_name": "Bash",
            "tool_input": {"command": "rm -rf build"},
        }
    )

    codex = runner.invoke(
        cli,
        ["hook", "receive", "codex", "pre-tool-use"],
        input=payload,
    )
    claude = runner.invoke(
        cli,
        ["hook", "receive", "claude-code", "pre-tool-use"],
        input=payload,
    )

    assert json.loads(codex.output)["hookSpecificOutput"][
        "permissionDecision"
    ] == "deny"
    assert claude.output == ""
    assert (
        tmp_path / ".pathtrace" / ".state" / "claude-code" / "s" / "current.json"
    ).is_file()
    assert not (tmp_path / ".pathtrace" / ".state" / "codex").exists()


@pytest.mark.parametrize(
    ("framework", "home_env", "settings_name"),
    [
        ("codex", "CODEX_HOME", "hooks.json"),
        ("claude-code", "CLAUDE_CONFIG_DIR", "settings.json"),
    ],
)
def test_observe_install_in_another_repo_preserves_global_security_hook(
    framework,
    home_env,
    settings_name,
    tmp_path,
    monkeypatch,
):
    agent_home = tmp_path / "agent-home"
    agent_home.mkdir()
    settings_path = agent_home / settings_name
    settings_path.write_text(
        json.dumps(
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "*",
                            "hooks": [
                                {"type": "command", "command": "user-hook"}
                            ],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(home_env, str(agent_home))
    repo_security = tmp_path / "repo-security"
    repo_observe = tmp_path / "repo-observe"
    repo_security.mkdir()
    repo_observe.mkdir()
    runner = CliRunner()

    monkeypatch.chdir(repo_security)
    security = runner.invoke(
        cli,
        ["install", "security", "--framework", framework],
    )
    monkeypatch.chdir(repo_observe)
    observe = runner.invoke(
        cli,
        ["install", "observe", "--framework", framework],
    )

    assert security.exit_code == observe.exit_code == 0
    hooks = json.loads(settings_path.read_text(encoding="utf-8"))["hooks"]
    commands = [
        hook["command"]
        for entry in hooks["PreToolUse"]
        for hook in entry["hooks"]
    ]
    assert "user-hook" in commands
    pathtrace_commands = [
        command for command in commands if command.startswith("pathtrace hook receive")
    ]
    assert len(pathtrace_commands) == 1
    assert "--security-enabled" in pathtrace_commands[0]
    assert "--configured-only" not in pathtrace_commands[0]

    (repo_security / ".pathtrace" / "config.yaml").write_text(
        "features: [security\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(repo_security)
    blocked = runner.invoke(
        cli,
        [
            "hook",
            "receive",
            framework,
            "pre-tool-use",
            "--security-enabled",
        ],
        input=json.dumps(
            {
                "session_id": "s",
                "turn_id": "t",
                "tool_name": "Bash",
                "tool_input": {"command": "python -m pytest"},
            }
        ),
    )

    assert blocked.exit_code == 0, blocked.output
    assert json.loads(blocked.output)["hookSpecificOutput"][
        "permissionDecision"
    ] == "deny"

    monkeypatch.chdir(repo_observe)
    observed = runner.invoke(
        cli,
        [
            "hook",
            "receive",
            framework,
            "pre-tool-use",
            "--security-enabled",
        ],
        input=json.dumps(
            {
                "session_id": "s",
                "turn_id": "t",
                "tool_name": "Bash",
                "tool_input": {"command": "python -m pytest"},
            }
        ),
    )

    assert observed.exit_code == 0
    assert observed.output == ""
    assert (repo_observe / ".pathtrace" / ".state" / framework).is_dir()
