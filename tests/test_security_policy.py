import os
import subprocess

import pytest

from pathtrace.security.action import build_security_action
from pathtrace.security.config import SecurityConfigError, parse_security_settings
from pathtrace.security.model import (
    EnforcementMode,
    SecurityActionType,
    SecurityDecisionType,
)
from pathtrace.security.policy import PolicyEngine


def _rule(identifier, decision):
    return {
        "id": identifier,
        "action": "shell",
        "decision": decision,
        "match": {"command": "deploy *"},
        "reason": f"Rule {identifier}",
    }


def test_action_classifies_shell_git_filesystem_mcp_and_network():
    shell = _action(tool="Bash", tool_input={"command": "python -m pytest"})
    git = _action(tool="shell_command", tool_input={"command": "git push origin main"})
    filesystem = _action(tool="Read", tool_input={"file_path": "/tmp/file"})
    mcp = _action(tool="mcp__github__create_issue", tool_input={"title": "bug"})
    network = _action(tool="Fetch", tool_input={"url": "https://example.com"})

    assert shell.action_type is SecurityActionType.SHELL
    assert git.action_type is SecurityActionType.GIT
    assert filesystem.action_type is SecurityActionType.FILESYSTEM
    assert mcp.action_type is SecurityActionType.MCP
    assert mcp.mcp_server == "github"
    assert network.action_type is SecurityActionType.NETWORK


def test_non_shell_tool_with_command_payload_is_not_misclassified():
    action = _action(
        tool="apply_patch",
        tool_input={"command": "*** Update File: README.md"},
    )

    assert action.action_type is SecurityActionType.TOOL
    assert action.command == "*** Update File: README.md"


@pytest.mark.parametrize(
    "command",
    [
        "git push --force origin main",
        "cd C:\\repo && git push --force origin main",
        "cd C:\\repo & git push --force origin main",
        "git -C C:\\repo push --force origin main",
        'git -C "C:\\repo with spaces" push --force origin main',
        "cmd /c git -C C:\\repo push --force origin main",
        "cmd /c GIT push --force origin main",
        'powershell -Command "Set-Location C:\\repo; GIT push --force origin main"',
    ],
)
def test_git_wrappers_are_classified_and_matched_deterministically(command):
    engine = PolicyEngine(
        _settings(
            [
                {
                    "id": "git-force",
                    "action": "git",
                    "decision": "block",
                    "match": {"command": "git push --force*"},
                    "reason": "Force push denied",
                }
            ]
        )
    )

    action = _action(
        tool="shell_command",
        tool_input={"command": command},
        cwd="C:\\repo",
    )

    assert action.action_type is SecurityActionType.GIT
    assert engine.evaluate(action).decision is SecurityDecisionType.BLOCK


@pytest.mark.parametrize(
    ("cwd", "resource", "pattern"),
    [
        (
            "/workspace/project/work",
            "../secrets/key.txt",
            "/workspace/project/secrets/**",
        ),
        (
            "C:\\Workspace\\Project\\work",
            "..\\SECRETS\\key.txt",
            "c:/workspace/project/secrets/**",
        ),
        (
            "C:\\Workspace\\Project",
            "C:/WORKSPACE/PROJECT/secrets/../SECRETS/key.txt",
            "C:\\workspace\\project\\secrets\\**",
        ),
        (
            "C:\\Workspace\\Project",
            "\\SECRETS\\key.txt",
            "c:/secrets/**",
        ),
    ],
)
def test_filesystem_rules_cannot_be_bypassed_by_equivalent_paths(
    cwd,
    resource,
    pattern,
):
    engine = PolicyEngine(
        _settings(
            [
                {
                    "id": "sensitive-files",
                    "action": "filesystem",
                    "decision": "block",
                    "match": {"resource": pattern},
                    "reason": "Sensitive path",
                }
            ]
        )
    )

    decision = engine.evaluate(
        _action(tool="Write", tool_input={"path": resource}, cwd=cwd)
    )

    assert decision.decision is SecurityDecisionType.BLOCK


def test_filesystem_rule_follows_symlink_to_sensitive_directory(tmp_path):
    protected = tmp_path / "protected"
    protected.mkdir()
    alias = tmp_path / "public-alias"
    try:
        alias.symlink_to(protected, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"directory symlink unavailable: {error}")
    engine = PolicyEngine(
        _settings(
            [
                {
                    "id": "protected-directory",
                    "action": "filesystem",
                    "decision": "block",
                    "match": {"resource": f"{protected.as_posix()}/**"},
                    "reason": "Protected directory",
                }
            ]
        )
    )

    decision = engine.evaluate(
        _action(
            tool="Write",
            tool_input={"path": str(alias / "not-created-yet.txt")},
            cwd=str(tmp_path),
        )
    )

    assert decision.decision is SecurityDecisionType.BLOCK


@pytest.mark.skipif(os.name != "nt", reason="Windows reparse point test")
def test_windows_directory_reparse_point_cannot_bypass_policy(tmp_path):
    protected = tmp_path / "protected"
    protected.mkdir()
    alias = tmp_path / "reparse-alias"
    created = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(alias), str(protected)],
        capture_output=True,
        text=True,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if created.returncode != 0:
        pytest.skip(f"Windows junction unavailable: {created.stderr.strip()}")
    engine = PolicyEngine(
        _settings(
            [
                {
                    "id": "protected-reparse-target",
                    "action": "filesystem",
                    "decision": "block",
                    "match": {"resource": f"{protected.as_posix()}/**"},
                    "reason": "Protected directory",
                }
            ]
        )
    )

    try:
        decision = engine.evaluate(
            _action(
                tool="Write",
                tool_input={"path": str(alias / "secret.txt")},
                cwd=str(tmp_path),
            )
        )
    finally:
        os.rmdir(alias)

    assert decision.decision is SecurityDecisionType.BLOCK


@pytest.mark.parametrize(
    ("configured", "expected"),
    [
        ("allow", SecurityDecisionType.ALLOW),
        ("block", SecurityDecisionType.BLOCK),
        ("require_approval", SecurityDecisionType.REQUIRE_APPROVAL),
    ],
)
def test_policy_engine_returns_configured_decision(configured, expected):
    settings = _settings(
        [
            {
                "id": "shell-rule",
                "action": "shell",
                "decision": configured,
                "match": {"command": "python *"},
                "reason": "Explicit test rule",
            }
        ]
    )

    decision = PolicyEngine(settings).evaluate(
        _action(tool="Bash", tool_input={"command": "python -m pytest"})
    )

    assert decision.decision is expected
    assert decision.rule_id == "shell-rule"
    assert decision.reason == "Explicit test rule"


def test_absence_of_rule_allows_without_enabling_security_implicitly():
    settings = _settings([])

    decision = PolicyEngine(settings).evaluate(
        _action(tool="Bash", tool_input={"command": "rm -rf build"})
    )

    assert decision.decision is SecurityDecisionType.ALLOW
    assert decision.rule_id is None


def test_conflict_priority_is_block_then_approval_then_allow():
    rules = [
        _rule("z-allow", "allow"),
        _rule("a-approval", "require_approval"),
        _rule("m-block", "block"),
    ]

    decision = PolicyEngine(_settings(rules)).evaluate(
        _action(tool="Bash", tool_input={"command": "deploy production"})
    )

    assert decision.decision is SecurityDecisionType.BLOCK
    assert decision.rule_id == "m-block"


def test_same_priority_uses_rule_identifier_not_collection_order():
    rules = [_rule("z-block", "block"), _rule("a-block", "block")]

    decision = PolicyEngine(_settings(rules)).evaluate(
        _action(tool="Bash", tool_input={"command": "deploy production"})
    )

    assert decision.rule_id == "a-block"


def test_git_filesystem_and_mcp_patterns_match_only_their_action_type(tmp_path):
    settings = _settings(
        [
            {
                "id": "git-force",
                "action": "git",
                "decision": "block",
                "match": {"command": "git push --force*"},
                "reason": "Force push denied",
            },
            {
                "id": "credentials",
                "action": "filesystem",
                "decision": "block",
                "match": {"resource": f"{tmp_path.as_posix()}/secrets/**"},
                "reason": "Sensitive path",
            },
            {
                "id": "github-write",
                "action": "mcp",
                "decision": "require_approval",
                "match": {"mcp_server": "github", "tool": "*create*"},
                "reason": "External write",
            },
        ]
    )
    engine = PolicyEngine(settings)

    assert engine.evaluate(
        _action(tool="Bash", tool_input={"command": "git push --force origin main"})
    ).decision is SecurityDecisionType.BLOCK
    assert engine.evaluate(
        _action(tool="Write", tool_input={"path": str(tmp_path / "secrets" / "key")})
    ).decision is SecurityDecisionType.BLOCK
    assert engine.evaluate(
        _action(tool="mcp__github__create_issue", tool_input={})
    ).decision is SecurityDecisionType.REQUIRE_APPROVAL


def test_network_rule_matches_when_the_provider_exposes_a_url():
    engine = PolicyEngine(
        _settings(
            [
                {
                    "id": "block-production-api",
                    "action": "network",
                    "decision": "block",
                    "match": {"resource": "https://api.example.com/*"},
                    "reason": "Production network denied",
                }
            ]
        )
    )

    decision = engine.evaluate(
        _action(tool="Fetch", tool_input={"url": "https://api.example.com/data"})
    )

    assert decision.decision is SecurityDecisionType.BLOCK


def test_audit_only_preserves_the_policy_decision():
    settings = parse_security_settings(
        {"mode": "audit_only", "rules": [_rule("deny", "block")]}
    )

    decision = PolicyEngine(settings).evaluate(
        _action(tool="Bash", tool_input={"command": "deploy production"})
    )

    assert decision.decision is SecurityDecisionType.BLOCK
    assert decision.enforcement_mode is EnforcementMode.AUDIT_ONLY


@pytest.mark.parametrize(
    "raw",
    [
        {"mode": "sometimes"},
        {"rules": "not-a-list"},
        {"rules": [{"id": "x"}]},
        {"rules": [_rule("same", "allow"), _rule("same", "block")]},
        {"rules": [{**_rule("x", "allow"), "unexpected": True}]},
    ],
)
def test_invalid_rules_are_rejected(raw):
    with pytest.raises(SecurityConfigError):
        parse_security_settings(raw)


def _action(*, tool, tool_input, cwd=None):
    return build_security_action(
        framework="test",
        session_id="session",
        turn_id="turn",
        tool=tool,
        tool_input=tool_input,
        cwd=cwd,
    )


def _settings(rules):
    return parse_security_settings({"mode": "enforce", "rules": rules})
