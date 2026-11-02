import json

import pytest
from click.testing import CliRunner

from pathtrace.cli import cli
from pathtrace.provider_paths import provider_home, provider_security_path


@pytest.fixture(params=["codex", "claude-code"])
def agent(request, tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex-home"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude-home"))
    monkeypatch.chdir(tmp_path)
    return request.param, tmp_path


@pytest.fixture
def populated(agent, monkeypatch):
    framework, root = agent
    project = root / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    _install(framework)
    _project_artifacts(root)
    hooks = _user_hooks(framework)
    return framework, root, hooks


def _install(framework):
    for args in (["install", "all", "--framework", framework],
                 ["install", "security", "--framework", framework, "--scope", "provider", "--presets"]):
        result = CliRunner().invoke(cli, args)
        assert result.exit_code == 0, result.output


def _project_artifacts(root):
    for project in ("project", "other-project"):
        for name in ("config.yaml", "traces/session.json", "reports/report.json", "graphs/graph.html"):
            path = root / project / ".pathtrace" / name
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("project data", encoding="utf-8")


def _hooks_path(framework):
    return provider_home(framework) / ("hooks.json" if framework == "codex" else "settings.json")


def _user_hooks(framework):
    path = _hooks_path(framework)
    value = json.loads(path.read_text(encoding="utf-8"))
    value["theme"] = "dark"
    value["hooks"]["PreToolUse"][0]["hooks"].append(dict(type="command", command="user-hook", timeout=12))
    value["hooks"]["CustomEvent"] = [dict(hooks=[dict(type="command", command="user-custom-hook")])]
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _snapshot(root):
    return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def _projects_snapshot(root):
    return {name: _snapshot(root / name / ".pathtrace") for name in ("project", "other-project")}


def _purge(framework, *options, answer=None):
    return CliRunner().invoke(cli, ["uninstall", "--framework", framework, "--purge", *options], input=answer)


@pytest.mark.parametrize("answer", [None, "n\n", "\n"])
def test_purge_requires_explicit_confirmation_without_any_write(populated, answer):
    framework, root, _ = populated
    before = _snapshot(root)
    result = _purge(framework, answer=answer)
    assert result.exit_code == 1
    assert "tous les projets" in result.output
    assert _snapshot(root) == before


@pytest.mark.parametrize("automated", [False, True])
def test_purge_removes_managed_hooks_and_provider_config_but_preserves_projects(populated, automated):
    framework, root, hooks = populated
    before = _projects_snapshot(root)
    result = _purge(framework, *( ["--yes"] if automated else []), answer=None if automated else "y\n")
    assert result.exit_code == 0, result.output
    assert not provider_security_path(framework).exists()
    value = json.loads(hooks.read_text(encoding="utf-8"))
    assert value == dict(theme="dark", hooks={"PreToolUse": [dict(matcher="*", hooks=[dict(type="command", command="user-hook", timeout=12)])],
                                              "CustomEvent": [dict(hooks=[dict(type="command", command="user-custom-hook")])]})
    assert _projects_snapshot(root) == before


def test_purge_is_idempotent_after_removal(populated):
    framework, root, _ = populated
    assert _purge(framework, "--yes").exit_code == 0
    before = _snapshot(root)
    assert _purge(framework, "--yes").exit_code == 0
    assert _snapshot(root) == before


def test_purge_does_not_affect_other_provider(populated):
    framework, _, _ = populated
    other = "claude-code" if framework == "codex" else "codex"
    _install(other)
    before = _snapshot(provider_home(other))
    assert _purge(framework, "--yes").exit_code == 0
    assert _snapshot(provider_home(other)) == before


def test_purge_from_an_unrelated_directory_keeps_all_projects(populated, monkeypatch):
    framework, root, _ = populated
    before = _projects_snapshot(root)
    monkeypatch.chdir(root)
    assert _purge(framework, "--yes").exit_code == 0
    assert _projects_snapshot(root) == before
    assert not (root / ".pathtrace").exists()


def test_purge_when_nothing_exists_creates_nothing(agent):
    framework, root = agent
    assert _purge(framework, "--yes").exit_code == 0
    assert list(root.iterdir()) == []


def test_invalid_hooks_do_not_delete_provider_config(populated):
    framework, _, hooks = populated
    hooks.write_text("invalid JSON", encoding="utf-8")
    before = provider_security_path(framework).read_bytes()
    assert _purge(framework, "--yes").exit_code == 1
    assert hooks.read_text(encoding="utf-8") == "invalid JSON"
    assert provider_security_path(framework).read_bytes() == before


def test_purge_removes_invalid_provider_config_when_hooks_are_absent(agent):
    framework, _ = agent
    path = provider_security_path(framework)
    path.parent.mkdir(parents=True)
    path.write_text("invalid YAML", encoding="utf-8")
    assert _purge(framework, "--yes").exit_code == 0
    assert not path.exists()


@pytest.mark.parametrize("scope", ["project", "provider"])
def test_purge_rejects_an_explicit_scope_before_writing(populated, scope):
    framework, root, _ = populated
    before = _snapshot(root)
    assert _purge(framework, "--yes", "--scope", scope).exit_code == 2
    assert _snapshot(root) == before


def test_yes_without_purge_is_rejected_before_writing(populated):
    framework, root, _ = populated
    before = _snapshot(root)
    result = CliRunner().invoke(cli, ["uninstall", "--framework", framework, "--yes"])
    assert result.exit_code == 2
    assert _snapshot(root) == before


def test_purge_removes_legacy_codex_hook(tmp_path, monkeypatch):
    framework = "codex"
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex-home"))
    hooks = _hooks_path(framework)
    hooks.parent.mkdir(parents=True)
    hooks.write_text(json.dumps(dict(hooks={"Stop": [dict(hooks=[dict(type="command", command="pathtrace hook codex stop")])]})), encoding="utf-8")
    assert _purge(framework, "--yes").exit_code == 0
    assert json.loads(hooks.read_text(encoding="utf-8")) == {}


@pytest.mark.parametrize("flags", ["", " --configured-only", " --security-enabled",
                                   " --configured-only --security-enabled", " --security-enabled --configured-only"])
def test_purge_removes_flag_variants_and_preserves_similar_user_commands(agent, flags):
    framework, _ = agent
    path = _hooks_path(framework)
    path.parent.mkdir(parents=True)
    base = f"pathtrace hook receive {framework} pre-tool-use"
    commands = [base + flags, f"echo '{base}'", base + " --custom-user-option"]
    path.write_text(json.dumps(dict(hooks={"PreToolUse": [dict(hooks=[dict(type="command", command=c) for c in commands])]})), encoding="utf-8")
    assert _purge(framework, "--yes").exit_code == 0
    remaining = json.loads(path.read_text(encoding="utf-8"))["hooks"]["PreToolUse"][0]["hooks"]
    assert [hook["command"] for hook in remaining] == commands[1:]
