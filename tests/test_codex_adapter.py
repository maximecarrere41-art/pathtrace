import json

from pathtrace.adapters.codex import CodexAdapter


adapter = CodexAdapter()


def test_install_preserves_existing_hooks_and_adds_all_managed_events(tmp_path, monkeypatch):
    codex_home = tmp_path / ".codex"
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    hooks_path = codex_home / "hooks.json"
    hooks_path.parent.mkdir(parents=True)
    hooks_path.write_text(
        json.dumps(
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Bash",
                            "hooks": [{"type": "command", "command": "existing hook"}],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    adapter.install(tmp_path)

    config = json.loads(hooks_path.read_text(encoding="utf-8"))
    assert set(config["hooks"]) >= {"UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop"}
    commands = _commands(config, "PreToolUse")
    assert "existing hook" in commands
    assert "pathtrace hook receive codex pre-tool-use" in commands


def test_install_is_idempotent(tmp_path, monkeypatch):
    codex_home = tmp_path / ".codex"
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    adapter.install(tmp_path)
    adapter.install(tmp_path)

    config = json.loads((codex_home / "hooks.json").read_text(encoding="utf-8"))
    assert _commands(config, "UserPromptSubmit").count(
        "pathtrace hook receive codex user-prompt-submit"
    ) == 1


def test_prompt_and_pre_post_hooks_create_one_command_event(tmp_path):
    adapter.handle(
        "user-prompt-submit",
        {"session_id": "s1", "turn_id": "t1", "prompt": "run tests", "model": "codex-model"},
        tmp_path,
    )
    adapter.handle(
        "pre-tool-use",
        {
            "session_id": "s1",
            "turn_id": "t1",
            "tool_use_id": "call-1",
            "tool_name": "Bash",
            "tool_input": {"command": "python -m pytest"},
        },
        tmp_path,
    )
    adapter.handle(
        "post-tool-use",
        {
            "session_id": "s1",
            "turn_id": "t1",
            "tool_use_id": "call-1",
            "tool_name": "Bash",
            "tool_input": {"command": "python -m pytest"},
            "tool_response": {"success": True, "output": "12 passed"},
        },
        tmp_path,
    )

    output = adapter.handle("stop", {"session_id": "s1", "turn_id": "t1"}, tmp_path)
    trace = json.loads(output.read_text(encoding="utf-8"))

    assert trace["version"] == 3
    assert trace["prompt"] == "run tests"
    assert trace["turn_id"] == "t1"
    assert trace["summary"]["commands"] == ["python -m pytest"]
    assert trace["summary"]["tools"] == ["Bash"]
    assert len(trace["events"]) == 1
    assert trace["events"][0]["command"] == "python -m pytest"
    assert trace["events"][0]["status"] == "success"
    assert trace["events"][0]["output_summary"] == "12 passed"
    assert not (tmp_path / ".pathtrace" / ".state" / "codex" / "s1" / "t1.json").exists()


def test_skill_is_extracted_dynamically_from_skill_path(tmp_path):
    adapter.handle(
        "post-tool-use",
        {
            "session_id": "s1",
            "turn_id": "t2",
            "tool_name": "Read",
            "tool_input": {"file_path": ".agents/skills/pdfs/SKILL.md"},
            "tool_response": {"success": True},
        },
        tmp_path,
    )

    output = adapter.handle("stop", {"session_id": "s1", "turn_id": "t2"}, tmp_path)
    trace = json.loads(output.read_text(encoding="utf-8"))

    assert trace["summary"]["skills"] == ["pdfs"]
    assert trace["summary"]["tools"] == ["Read"]
    assert trace["events"][0]["type"] == "skill"
    assert trace["events"][0]["name"] == "pdfs"
    assert trace["events"][0]["tool"] == "Read"


def test_direct_skill_tool_uses_provided_name(tmp_path):
    adapter.handle(
        "post-tool-use",
        {
            "session_id": "s1",
            "turn_id": "t3",
            "tool_name": "Skill",
            "tool_input": {"skill": "conventions-code"},
            "tool_response": {"success": True},
        },
        tmp_path,
    )
    output = adapter.handle("stop", {"session_id": "s1", "turn_id": "t3"}, tmp_path)
    trace = json.loads(output.read_text(encoding="utf-8"))

    assert trace["events"][0]["type"] == "skill"
    assert trace["events"][0]["name"] == "conventions-code"


def test_turns_are_written_to_separate_files(tmp_path):
    first = adapter.handle("stop", {"session_id": "same", "turn_id": "one", "prompt": "one"}, tmp_path)
    second = adapter.handle("stop", {"session_id": "same", "turn_id": "two", "prompt": "two"}, tmp_path)

    assert first != second
    assert first.is_file()
    assert second.is_file()
    assert first.parent == second.parent


def test_finalize_without_events_produces_empty_summary(tmp_path):
    output = adapter.handle("stop", {"session_id": "empty", "turn_id": "t1"}, tmp_path)
    trace = json.loads(output.read_text(encoding="utf-8"))

    assert trace["events"] == []
    assert trace["summary"] == {"skills": [], "commands": [], "tools": []}


def _commands(config, event_name):
    return [
        hook["command"]
        for entry in config["hooks"][event_name]
        for hook in entry["hooks"]
    ]

def test_install_writes_hooks_in_codex_home(tmp_path, monkeypatch):
    codex_home = tmp_path / "global-codex"
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    path = CodexAdapter().install(tmp_path / "project")

    assert path == codex_home / "hooks.json"
    assert path.is_file()