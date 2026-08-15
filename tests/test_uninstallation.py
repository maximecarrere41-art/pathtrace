import json

import pytest
import yaml
from click.testing import CliRunner

from pathtrace.cli import cli


FRAMEWORKS = (
    ("codex", "CODEX_HOME", "hooks.json"),
    ("claude-code", "CLAUDE_CONFIG_DIR", "settings.json"),
)


@pytest.mark.parametrize(("framework", "home_env", "settings_name"), FRAMEWORKS)
def test_install_then_uninstall_removes_pathtrace_hooks_and_local_config(
    framework,
    home_env,
    settings_name,
    tmp_path,
    monkeypatch,
):
    agent_home = tmp_path / "agent-home"
    monkeypatch.setenv(home_env, str(agent_home))
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    installed = runner.invoke(cli, ["install", "all", "--framework", framework])
    historical_artifacts = (
        tmp_path / ".pathtrace" / "traces" / framework / "historical.json",
        tmp_path / ".pathtrace" / "reports" / "historical.json",
        tmp_path / ".pathtrace" / "graphs" / "historical.html",
        tmp_path / ".pathtrace" / "campaigns" / "historical.yaml",
    )
    for artifact in historical_artifacts:
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text("historical", encoding="utf-8")

    uninstalled = runner.invoke(cli, ["uninstall", "--framework", framework])

    assert installed.exit_code == uninstalled.exit_code == 0, uninstalled.output
    settings = json.loads(
        (agent_home / settings_name).read_text(encoding="utf-8")
    )
    assert "hooks" not in settings
    assert not (tmp_path / ".pathtrace" / "config.yaml").exists()
    assert all(artifact.is_file() for artifact in historical_artifacts)


@pytest.mark.parametrize(("framework", "home_env", "settings_name"), FRAMEWORKS)
def test_uninstall_is_idempotent_when_pathtrace_is_already_partially_removed(
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
                                {
                                    "type": "command",
                                    "command": (
                                        f"pathtrace hook receive {framework} "
                                        "pre-tool-use --security-enabled"
                                    ),
                                }
                            ],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(home_env, str(agent_home))
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    first = runner.invoke(cli, ["uninstall", "--framework", framework])
    after_first = settings_path.read_text(encoding="utf-8")
    second = runner.invoke(cli, ["uninstall", "--framework", framework])

    assert first.exit_code == second.exit_code == 0
    assert settings_path.read_text(encoding="utf-8") == after_first


@pytest.mark.parametrize(("framework", "home_env", "settings_name"), FRAMEWORKS)
def test_uninstall_preserves_user_hooks_and_provider_configuration(
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
                "theme": "dark",
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Bash",
                            "hooks": [
                                {"type": "command", "command": "user-pre-hook"},
                                {
                                    "type": "command",
                                    "command": (
                                        f"pathtrace hook receive {framework} "
                                        "pre-tool-use --configured-only "
                                        "--security-enabled"
                                    ),
                                },
                            ],
                        }
                    ],
                    "CustomEvent": [
                        {
                            "matcher": "*",
                            "hooks": [
                                {"type": "command", "command": "user-custom-hook"}
                            ],
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(home_env, str(agent_home))
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(cli, ["uninstall", "--framework", framework])

    assert result.exit_code == 0, result.output
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    assert settings["theme"] == "dark"
    assert settings["hooks"] == {
        "PreToolUse": [
            {
                "matcher": "Bash",
                "hooks": [{"type": "command", "command": "user-pre-hook"}],
            }
        ],
        "CustomEvent": [
            {
                "matcher": "*",
                "hooks": [{"type": "command", "command": "user-custom-hook"}],
            }
        ],
    }


def test_uninstall_one_framework_recalculates_features_and_keeps_the_other(
    tmp_path,
    monkeypatch,
):
    codex_home = tmp_path / "codex-home"
    claude_home = tmp_path / "claude-home"
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(claude_home))
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    runner.invoke(cli, ["install", "security", "--framework", "codex"])
    runner.invoke(cli, ["install", "observe", "--framework", "claude-code"])

    result = runner.invoke(cli, ["uninstall", "--framework", "codex"])

    assert result.exit_code == 0, result.output
    config = yaml.safe_load(
        (tmp_path / ".pathtrace" / "config.yaml").read_text(encoding="utf-8")
    )
    assert config == {
        "version": 1,
        "features": ["observe"],
        "frameworks": {"claude-code": ["observe"]},
    }
    assert "hooks" not in json.loads(
        (codex_home / "hooks.json").read_text(encoding="utf-8")
    )
    claude_hooks = json.loads(
        (claude_home / "settings.json").read_text(encoding="utf-8")
    )["hooks"]
    assert "UserPromptSubmit" in claude_hooks


@pytest.mark.parametrize(("framework", "home_env", "settings_name"), FRAMEWORKS)
def test_uninstall_removes_all_current_internal_hook_flag_variants(
    framework,
    home_env,
    settings_name,
    tmp_path,
    monkeypatch,
):
    agent_home = tmp_path / "agent-home"
    agent_home.mkdir()
    settings_path = agent_home / settings_name
    base = f"pathtrace hook receive {framework} pre-tool-use"
    commands = [
        base,
        f"{base} --configured-only",
        f"{base} --security-enabled",
        f"{base} --configured-only --security-enabled",
        f"{base} --security-enabled --configured-only",
        "user-hook",
    ]
    settings_path.write_text(
        json.dumps(
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "*",
                            "hooks": [
                                {"type": "command", "command": command}
                                for command in commands
                            ],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(home_env, str(agent_home))
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(cli, ["uninstall", "--framework", framework])

    assert result.exit_code == 0, result.output
    remaining = json.loads(settings_path.read_text(encoding="utf-8"))["hooks"]
    assert remaining["PreToolUse"][0]["hooks"] == [
        {"type": "command", "command": "user-hook"}
    ]
