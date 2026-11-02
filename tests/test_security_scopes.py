import json

import pytest
import yaml
from click.testing import CliRunner

from pathtrace.cli import cli
from pathtrace.config import Feature, ProjectConfig, write_project_config
from pathtrace.provider_paths import provider_security_path


@pytest.fixture(params=["codex", "claude-code"])
def environment(request, tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    monkeypatch.chdir(tmp_path)
    return request.param, tmp_path


def settings(decision="BLOCK", mode="enforce"):
    rule = dict(id="same-id", action="shell", decision=decision,
                match={"command": "danger*"}, reason="Scoped rule")
    return dict(mode=mode, rules=[rule], telemetry={"enabled": False})


def provider(framework, raw=None):
    path = provider_security_path(framework)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(dict(version=1, security=raw or settings())), encoding="utf-8")
    return path


def project(root, framework, raw):
    features = frozenset({Feature.SECURITY})
    write_project_config(root, ProjectConfig(features, raw, {framework: features}))


def receive(framework, command="danger now"):
    payload = dict(tool_name="Bash", tool_input={"command": command}, session_id="s")
    result = CliRunner().invoke(cli, ["hook", "receive", framework, "pre-tool-use",
                                     "--configured-only"], input=json.dumps(payload))
    assert result.exit_code == 0, result.output
    return json.loads(result.output)["hookSpecificOutput"]["permissionDecision"] if result.output else None


def test_provider_alone_protects_without_project_configuration(environment):
    framework, root = environment
    provider(framework)
    assert receive(framework) == "deny"
    assert not (root / ".pathtrace").exists()


def test_project_alone_still_protects(environment):
    framework, root = environment
    project(root, framework, settings())
    assert receive(framework) == "deny"


@pytest.mark.parametrize("decision", ["ALLOW", "REQUIRE_APPROVAL", "BLOCK"])
@pytest.mark.parametrize("mode", ["enforce", "audit_only"])
def test_project_cannot_weaken_provider_even_with_same_rule_id(environment, decision, mode):
    framework, root = environment
    provider(framework)
    project(root, framework, settings(decision, mode))
    assert receive(framework) == "deny"


def test_provider_rules_do_not_apply_to_other_framework(environment):
    framework, _ = environment
    provider(framework)
    other = "claude-code" if framework == "codex" else "codex"
    assert receive(other) is None


def test_project_block_beats_provider_approval_even_with_legacy_mode(environment):
    framework, root = environment
    provider(framework, settings("REQUIRE_APPROVAL"))
    project(root, framework, settings("BLOCK", "audit_only"))
    assert receive(framework) == "deny"


def test_legacy_provider_mode_always_enforces(environment):
    framework, root = environment
    provider(framework, settings("BLOCK", "audit_only"))
    assert receive(framework) == "deny"
    project(root, framework, settings("REQUIRE_APPROVAL"))
    assert receive(framework) == "deny"


def test_provider_allow_cannot_weaken_project_block(environment):
    framework, root = environment
    provider(framework, settings("ALLOW"))
    project(root, framework, settings())
    assert receive(framework) == "deny"


def test_malformed_provider_fails_closed(environment):
    framework, _ = environment
    path = provider(framework)
    path.write_text("security: [invalid", encoding="utf-8")
    assert receive(framework) == "deny"


def test_invalid_project_does_not_bypass_provider(environment):
    framework, root = environment
    provider(framework)
    path = root / ".pathtrace" / "config.yaml"
    path.parent.mkdir()
    path.write_text("version: wrong", encoding="utf-8")
    assert receive(framework) == "deny"


def test_duplicate_ids_inside_provider_fail_closed(environment):
    framework, _ = environment
    raw = settings()
    raw["rules"] *= 2
    provider(framework, raw)
    assert receive(framework) == "deny"


def invoke(*args):
    result = CliRunner().invoke(cli, list(args))
    assert result.exit_code == 0, result.output
    return result.output


def test_provider_install_is_idempotent_and_does_not_create_project(environment):
    framework, root = environment
    path = provider(framework)
    invoke("install", "security", "--framework", framework, "--scope", "provider")
    invoke("install", "security", "--framework", framework, "--scope", "provider")
    assert yaml.safe_load(path.read_text(encoding="utf-8"))["security"] == settings()
    assert not (root / ".pathtrace").exists()
    assert receive(framework) == "deny"


def test_uninstall_project_leaves_provider_protection(environment):
    framework, root = environment
    path = provider(framework)
    before = path.read_bytes()
    project(root, framework, settings("ALLOW"))
    invoke("uninstall", "--framework", framework, "--scope", "project")
    assert receive(framework) == "deny"
    assert path.read_bytes() == before


def test_provider_uninstall_preserves_shared_hooks_and_project_bytes(environment):
    framework, root = environment
    provider(framework)
    project(root, framework, settings())
    invoke("install", "security", "--framework", framework)
    from pathtrace.provider_paths import provider_home
    hook = provider_home(framework) / ("hooks.json" if framework == "codex" else "settings.json")
    before = hook.read_bytes(), (root / ".pathtrace/config.yaml").read_bytes()
    invoke("uninstall", "--framework", framework, "--scope", "provider")
    assert before == (hook.read_bytes(), (root / ".pathtrace/config.yaml").read_bytes())


def test_provider_uninstall_from_unrelated_directory_is_isolated(environment, monkeypatch):
    framework, root = environment
    path = provider(framework)
    other = "claude-code" if framework == "codex" else "codex"
    other_path = provider(other)
    elsewhere = root / "unrelated"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    invoke("uninstall", "--framework", framework, "--scope", "provider")
    assert not path.exists() and other_path.exists() and not (elsewhere / ".pathtrace").exists()


def test_provider_uninstall_is_idempotent_even_for_invalid_configuration(environment):
    framework, _ = environment
    path = provider(framework)
    path.write_text("invalid: [", encoding="utf-8")
    invoke("uninstall", "--framework", framework, "--scope", "provider")
    invoke("uninstall", "--framework", framework, "--scope", "provider")
    assert not path.exists()


def test_uninstall_provider_removes_file_and_preserves_project(environment):
    framework, root = environment
    path = provider(framework)
    project(root, framework, settings())
    invoke("uninstall", "--framework", framework, "--scope", "provider")
    assert receive(framework) == "deny"
    assert not path.exists()


def test_project_reactivation_restores_its_custom_rules(environment):
    framework, root = environment
    project(root, framework, settings())
    invoke("uninstall", "--framework", framework)
    assert receive(framework) is None
    invoke("install", "security", "--framework", framework)
    assert receive(framework) == "deny"


def test_project_uninstall_does_not_interrupt_another_repository(environment, monkeypatch):
    framework, root = environment
    other = root / "other-project"
    project(root, framework, settings())
    project(other, framework, settings())
    invoke("install", "security", "--framework", framework)
    invoke("uninstall", "--framework", framework)
    monkeypatch.chdir(other)
    assert receive(framework) == "deny"


def test_provider_reinstallation_initializes_only_after_new_explicit_choice(environment):
    framework, _ = environment
    provider(framework)
    invoke("uninstall", "--framework", framework, "--scope", "provider")
    assert receive(framework) is None
    invoke("install", "security", "--framework", framework, "--scope", "provider", "--no-presets")
    assert receive(framework) is None


def test_project_uninstall_does_not_activate_observe_for_provider_only(environment):
    framework, root = environment
    other = "claude-code" if framework == "codex" else "codex"
    provider(framework)
    provider(other)
    invoke("uninstall", "--framework", framework, "--scope", "project")
    assert receive(other) == "deny"
    assert not (root / ".pathtrace" / ".state").exists()


def test_provider_block_in_composite_survives_project_allow(environment):
    framework, root = environment
    raw = settings()
    raw["rules"][0]["match"] = {"command": "rm -rf *"}
    provider(framework, raw)
    project(root, framework, settings("ALLOW"))
    assert receive(framework, "rm -rf build && git status") == "deny"


@pytest.mark.parametrize("provider_present", [False, True])
def test_uninstall_without_project_config_never_creates_other_activation(environment, provider_present):
    framework, root = environment
    if provider_present:
        provider(framework)
    invoke("uninstall", "--framework", framework)
    value = yaml.safe_load((root / ".pathtrace/config.yaml").read_text(encoding="utf-8"))
    assert value["frameworks"] == {}
    assert value["features"] == []


def test_uninstall_does_not_capture_other_provider_without_local_configuration(environment):
    framework, root = environment
    other = "claude-code" if framework == "codex" else "codex"
    invoke("uninstall", "--framework", framework)
    assert receive(other) is None
    assert not (root / ".pathtrace/.state").exists()


def test_uninstall_preserves_explicit_legacy_features_for_other_provider(environment):
    framework, root = environment
    write_project_config(root, ProjectConfig(frozenset({Feature.OBSERVE})))
    invoke("uninstall", "--framework", framework)
    other = "claude-code" if framework == "codex" else "codex"
    value = yaml.safe_load((root / ".pathtrace/config.yaml").read_text(encoding="utf-8"))
    assert value["frameworks"] == {other: ["observe"]}


def test_status_exposes_each_source_without_secrets(environment):
    framework, root = environment
    provider(framework)
    project(root, framework, settings("ALLOW", "audit_only"))
    output = invoke("status")
    assert "Security provider: 1 rules (enforce)" in output
    assert "Security project: 1 rules (enforce)" in output
    assert "Security telemetry: disabled" in output


def test_audit_identifies_colliding_rule_ids(environment, monkeypatch):
    framework, root = environment
    events = []
    monkeypatch.setattr("pathtrace.hooks.pipeline._publish_decision", lambda t, d: events.append(d))
    provider(framework)
    project(root, framework, settings("BLOCK", "audit_only"))
    assert receive(framework) == "deny"
    assert {d.policy for d in events} == {"pathtrace.security.provider", "pathtrace.security.project"}
    assert {d.enforcement_result for d in events} == {"blocked"}
