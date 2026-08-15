import json

import pytest
import yaml
from click.testing import CliRunner

from pathtrace.cli import cli
from pathtrace.security.audit import SecurityAuditEvent


@pytest.mark.parametrize("framework", ["codex", "claude-code"])
def test_block_is_enforced_before_execution_for_supported_frameworks(
    framework, tmp_path, monkeypatch
):
    _configure(
        tmp_path,
        mode="enforce",
        decision="block",
        features=["security"],
    )
    monkeypatch.chdir(tmp_path)

    result = _pre_tool_use(framework, command="rm -rf build")

    assert result.exit_code == 0, result.output
    response = json.loads(result.output)
    assert response["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert not (tmp_path / ".pathtrace" / ".state").exists()
    assert not (tmp_path / ".pathtrace" / "traces").exists()


def test_claude_code_uses_native_approval(tmp_path, monkeypatch):
    _configure(
        tmp_path,
        mode="enforce",
        decision="require_approval",
        action="git",
    )
    monkeypatch.chdir(tmp_path)

    result = _pre_tool_use("claude-code", command="git push origin main")

    response = json.loads(result.output)
    assert response["hookSpecificOutput"]["permissionDecision"] == "ask"


def test_codex_blocks_when_native_approval_is_not_supported(tmp_path, monkeypatch):
    _configure(
        tmp_path,
        mode="enforce",
        decision="require_approval",
        action="git",
    )
    monkeypatch.chdir(tmp_path)

    result = _pre_tool_use("codex", command="git push origin main")

    response = json.loads(result.output)
    specific = response["hookSpecificOutput"]
    assert specific["permissionDecision"] == "deny"
    assert "ne supporte pas" in specific["permissionDecisionReason"]


@pytest.mark.parametrize("framework", ["codex", "claude-code"])
def test_invalid_enforce_config_blocks_fail_closed(
    framework,
    tmp_path,
    monkeypatch,
):
    _configure(tmp_path, mode="enforce", decision="allow")
    config_path = tmp_path / ".pathtrace" / "config.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["security"]["rules"] = "invalid"
    config_path.write_text(
        yaml.safe_dump(config, sort_keys=False),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    result = _pre_tool_use(framework, command="python -m pytest")

    assert result.exit_code == 0, result.output
    response = json.loads(result.output)["hookSpecificOutput"]
    assert response["permissionDecision"] == "deny"
    assert "failed" in response["permissionDecisionReason"]


@pytest.mark.parametrize("framework", ["codex", "claude-code"])
def test_internal_policy_error_blocks_fail_closed(
    framework,
    tmp_path,
    monkeypatch,
):
    _configure(tmp_path, mode="enforce", decision="allow")
    monkeypatch.setattr(
        "pathtrace.hooks.pipeline.PolicyEngine.evaluate",
        lambda self, action: (_ for _ in ()).throw(RuntimeError("engine failure")),
    )
    monkeypatch.chdir(tmp_path)

    result = _pre_tool_use(framework, command="python -m pytest")

    assert result.exit_code == 0, result.output
    response = json.loads(result.output)["hookSpecificOutput"]
    assert response["permissionDecision"] == "deny"
    assert "RuntimeError" in response["permissionDecisionReason"]


def test_malformed_yaml_blocks_when_installed_security_hook_declares_itself(
    tmp_path,
    monkeypatch,
):
    _configure(tmp_path, mode="enforce", decision="allow")
    (tmp_path / ".pathtrace" / "config.yaml").write_text(
        "features: [security\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        cli,
        [
            "hook",
            "receive",
            "codex",
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

    assert result.exit_code == 0, result.output
    response = json.loads(result.output)["hookSpecificOutput"]
    assert response["permissionDecision"] == "deny"
    assert "ProjectConfigError" in response["permissionDecisionReason"]


def test_audit_only_keeps_the_native_action_unmodified(tmp_path, monkeypatch):
    _configure(tmp_path, mode="audit_only", decision="block")
    monkeypatch.chdir(tmp_path)

    result = _pre_tool_use("codex", command="rm -rf build")

    assert result.exit_code == 0
    assert result.output == ""


def test_security_disabled_preserves_historical_observe_pipeline(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    result = _pre_tool_use("codex", command="python -m pytest")

    assert result.exit_code == 0
    assert (tmp_path / ".pathtrace" / ".state" / "codex" / "s" / "t.json").is_file()


def test_allow_block_and_approval_publish_security_audit_events(tmp_path, monkeypatch):
    events: list[SecurityAuditEvent] = []

    class Publisher:
        def publish(self, event):
            events.append(event)

    monkeypatch.setattr(
        "pathtrace.hooks.pipeline.build_security_audit_publisher",
        lambda config: Publisher(),
    )
    monkeypatch.chdir(tmp_path)

    for decision in ("allow", "block", "require_approval"):
        _configure(tmp_path, mode="enforce", decision=decision, action="git")
        _pre_tool_use("claude-code", command="git push origin main")

    assert [event.decision for event in events] == [
        "ALLOW",
        "BLOCK",
        "REQUIRE_APPROVAL",
    ]
    assert all(event.session_id == "s" for event in events)


def test_observe_only_never_initializes_security_telemetry(tmp_path, monkeypatch):
    called = False

    def publisher(config):
        nonlocal called
        called = True
        raise AssertionError("Security telemetry must not be initialized")

    monkeypatch.setattr(
        "pathtrace.hooks.pipeline.build_security_audit_publisher",
        publisher,
    )
    monkeypatch.chdir(tmp_path)

    _pre_tool_use("codex", command="python -m pytest")

    assert called is False


def test_security_only_with_telemetry_is_a_first_class_pipeline(tmp_path, monkeypatch):
    received = []

    class Publisher:
        def publish(self, event):
            received.append(event)

    _configure(tmp_path, mode="enforce", decision="allow")
    config_path = tmp_path / ".pathtrace" / "config.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["security"]["telemetry"] = {
        "enabled": True,
        "otlp_endpoint": "http://collector:4318",
    }
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    monkeypatch.setattr(
        "pathtrace.hooks.pipeline.build_security_audit_publisher",
        lambda telemetry: Publisher(),
    )
    monkeypatch.chdir(tmp_path)

    result = _pre_tool_use("codex", command="python -m pytest")

    assert result.exit_code == 0
    assert len(received) == 1
    assert not (tmp_path / ".pathtrace" / "traces").exists()


def _pre_tool_use(framework, *, command):
    return CliRunner().invoke(
        cli,
        ["hook", "receive", framework, "pre-tool-use"],
        input=json.dumps(
            {
                "session_id": "s",
                "turn_id": "t",
                "tool_name": "Bash",
                "tool_input": {"command": command},
            }
        ),
    )


def _configure(
    tmp_path,
    *,
    mode,
    decision,
    action="shell",
    features=("security",),
):
    config_path = tmp_path / ".pathtrace" / "config.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "features": list(features),
                "security": {
                    "mode": mode,
                    "rules": [
                        {
                            "id": f"{action}-policy",
                            "action": action,
                            "decision": decision,
                            "match": {"command": "*"},
                            "reason": "Configured policy",
                        }
                    ],
                    "telemetry": {"enabled": False},
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
