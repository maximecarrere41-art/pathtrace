import json

import pytest
import yaml
from click.testing import CliRunner

from pathtrace.cli import cli
from pathtrace.provider_paths import provider_home, provider_security_path
from pathtrace.security.presets import initial_security


@pytest.fixture(params=["codex", "claude-code"])
def agent(request, tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    monkeypatch.chdir(tmp_path)
    return request.param


def install(agent, *options, answer=None):
    return CliRunner().invoke(cli, ["install", "security", "--framework", agent,
                                   "--scope", "provider", *options], input=answer)


def configured(agent):
    return yaml.safe_load(provider_security_path(agent).read_text(encoding="utf-8"))


def receive(agent, tool, inputs):
    payload = dict(tool_name=tool, tool_input=inputs)
    result = CliRunner().invoke(cli, ["hook", "receive", agent, "pre-tool-use",
                                     "--configured-only", "--security-enabled"], input=json.dumps(payload))
    assert result.exit_code == 0, result.output
    return json.loads(result.output)["hookSpecificOutput"]["permissionDecision"] if result.output else None


def test_initialization_prompts_before_writing_and_applies_rules(agent):
    result = install(agent, answer="y\n")
    assert result.exit_code == 0, result.output
    assert "Installer ces presets" in result.output
    assert "immédiatement appliquées" in result.output
    assert configured(agent)["security"] == initial_security(True)
    assert receive(agent, "Bash", {"command": "rm -rf build"}) == "deny"


def test_removed_cli_option_is_rejected_before_any_write(agent):
    result = install(agent, "--presets", "--mode", "enforce")
    assert result.exit_code == 2
    assert not provider_security_path(agent).exists()


def test_aborted_initialization_changes_nothing(agent, tmp_path):
    result = install(agent)
    assert result.exit_code == 1
    assert not provider_security_path(agent).exists()
    assert not provider_home(agent).exists()
    assert not (tmp_path / ".pathtrace").exists()


def test_declining_presets_installs_empty_enforced_policy(agent):
    assert install(agent, answer="n\n").exit_code == 0
    assert configured(agent)["security"] == initial_security(False)


def test_explicit_opt_out_works_without_input(agent):
    assert install(agent, "--no-presets").exit_code == 0
    assert configured(agent)["security"]["rules"] == []


def test_reinstall_preserves_user_edits_and_mode_byte_for_byte(agent):
    assert install(agent, "--presets").exit_code == 0
    path = provider_security_path(agent)
    original = "# user configuration\nversion: 1\nsecurity: {mode: enforce, rules: []}\n"
    path.write_text(original, encoding="utf-8")
    assert install(agent, "--presets").exit_code == 0
    assert path.read_text(encoding="utf-8") == original


def test_reinstall_preserves_legacy_configuration_but_enforces_its_rules(agent):
    assert install(agent, "--presets").exit_code == 0
    path = provider_security_path(agent)
    raw = configured(agent)
    raw["security"]["mode"] = "audit_only"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    before = path.read_bytes()
    assert install(agent, "--presets").exit_code == 0
    assert path.read_bytes() == before
    assert receive(agent, "Bash", {"command": "rm -rf build"}) == "deny"


def test_initialization_preserves_project_and_other_provider(agent, tmp_path):
    path = tmp_path / ".pathtrace" / "config.yaml"
    path.parent.mkdir()
    path.write_text("version: 1\nfeatures: [observe]\n", encoding="utf-8")
    original = path.read_bytes()
    assert install(agent, "--presets").exit_code == 0
    assert path.read_bytes() == original
    other = "claude-code" if agent == "codex" else "codex"
    assert not provider_security_path(other).exists()


@pytest.mark.parametrize("command", ["rm -rf build", "git push --force origin main",
                                     "git reset --hard HEAD", "git clean -fd", "git push origin main"])
def test_accepted_presets_are_enforced_and_audited_immediately(agent, command, monkeypatch):
    decisions = []
    monkeypatch.setattr("pathtrace.hooks.pipeline._publish_decision", lambda t, d: decisions.append(d))
    assert install(agent, "--presets").exit_code == 0
    response = receive(agent, "Bash", {"command": command})
    assert response == ("ask" if agent == "claude-code" and command.startswith(("git reset", "git clean", "git push origin")) else "deny")
    assert decisions[0].rule_id.startswith("preset-")
    assert decisions[0].enforcement_result in {"blocked", "approval_requested", "blocked_approval_unsupported"}


@pytest.mark.parametrize("command", ["rm -rf build", "rm -fr build", "echo ok && rm -rf build",
                                     "rm -rf build && git status", "git status && rm -rf build",
                                     "git push --force origin main", "git push origin main --force",
                                     "git push -f", "git status && git push --force origin main",
                                     "git --no-pager push --force origin main"])
def test_enforce_block_variants_and_composites(agent, command):
    assert install(agent, "--presets").exit_code == 0
    assert receive(agent, "Bash", {"command": command}) == "deny"


@pytest.mark.parametrize("separator", [" && ", " || ", ";", "|", "|&", "&", "\n", "\r\n"])
@pytest.mark.parametrize("reverse", [False, True])
def test_composite_deletion_cannot_hide_behind_git(agent, separator, reverse):
    assert install(agent, "--presets").exit_code == 0
    parts = ["rm -rf build", "git status"]
    assert receive(agent, "Bash", {"command": separator.join(reversed(parts) if reverse else parts)}) == "deny"


@pytest.mark.parametrize("command", ["git reset --hard HEAD", "git reset HEAD --hard", "git clean -fd",
                                     "git clean -df", "git clean -f -d", "git push origin main", "git push"])
def test_native_approval_capabilities_are_preserved(agent, command):
    assert install(agent, "--presets").exit_code == 0
    assert receive(agent, "Bash", {"command": command}) == ("ask" if agent == "claude-code" else "deny")


def test_ssh_resource_access_is_blocked(agent):
    assert install(agent, "--presets").exit_code == 0
    assert receive(agent, "Read", {"file_path": "~/.ssh/id_ed25519"}) == "deny"


@pytest.mark.parametrize(("tool", "field"), [("Bash", "command"), ("shell_command", "command"),
                                           ("exec_command", "cmd"), ("PowerShell", "script")])
def test_command_payload_variants_are_evaluated(agent, tool, field):
    assert install(agent, "--presets").exit_code == 0
    assert receive(agent, tool, {field: "git push --force origin main"}) == "deny"


def test_initialization_merges_user_settings_without_duplicating_hooks(agent):
    home = provider_home(agent)
    path = home / ("hooks.json" if agent == "codex" else "settings.json")
    home.mkdir()
    path.write_text(json.dumps(dict(theme="dark", hooks={"PreToolUse": [dict(hooks=[dict(type="command", command="user-hook")])]})), encoding="utf-8")
    assert install(agent, "--presets").exit_code == 0
    before = path.read_bytes()
    assert install(agent, "--presets").exit_code == 0
    assert path.read_bytes() == before
    assert json.loads(before)["theme"] == "dark"
    assert before.count(b"user-hook") == before.count(b"pathtrace hook receive") == 1


def test_initialization_options_cannot_modify_project_configuration(agent, tmp_path):
    result = CliRunner().invoke(cli, ["install", "security", "--framework", agent, "--presets"])
    assert result.exit_code == 1
    assert not (tmp_path / ".pathtrace").exists()


@pytest.mark.parametrize("command", ["git status", "git commit -m ok", "cat ~/.ssh/id_ed25519",
                                     "rm -r --force build"])
def test_documented_detection_limits_and_benign_commands(agent, command):
    assert install(agent, "--presets").exit_code == 0
    assert receive(agent, "Bash", {"command": command}) is None


def test_documented_text_matching_false_positive(agent):
    assert install(agent, "--presets").exit_code == 0
    assert receive(agent, "Bash", {"command": "echo 'rm -rf build'"}) == "deny"


def test_presets_are_not_shared_mutable_state():
    first = initial_security(True)
    first["rules"][0]["match"]["command"].clear()
    assert initial_security(True)["rules"][0]["match"]["command"]
