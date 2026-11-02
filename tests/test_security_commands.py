import pytest

from pathtrace.security.action import build_security_action
from pathtrace.security.commands import split_shell_commands
from pathtrace.security.config import parse_security_settings
from pathtrace.security.policy import PolicyEngine


SEPARATORS = [" && ", " || ", "; ", " | ", " |& ", " & ", "\n", "\r\n"]


def action(command):
    return build_security_action(framework="codex", session_id="s", turn_id="t",
                                 tool="shell_command", tool_input={"command": command})


def rule(identifier, kind, command, decision):
    return dict(id=identifier, action=kind, decision=decision,
                match={"command": command}, reason=identifier)


def evaluate(command, rules):
    return PolicyEngine(parse_security_settings({"rules": rules})).evaluate(action(command))


@pytest.mark.parametrize("separator", SEPARATORS)
@pytest.mark.parametrize("parts", [("rm -rf build", "git status"), ("git status", "rm -rf build")])
def test_every_segment_is_evaluated_with_anchored_rules(separator, parts):
    rules = [rule("block-delete", "shell", "rm -rf *", "BLOCK"),
             rule("allow-git", "git", "git *", "ALLOW")]
    decision = evaluate(separator.join(parts), rules)
    assert decision.decision.value == "BLOCK"
    assert decision.rule_id == "block-delete"
    assert decision.action.command == "rm -rf build"


@pytest.mark.parametrize("separator", SEPARATORS)
def test_approval_beats_allow_across_segments(separator):
    rules = [rule("approve-push", "git", "git push *", "REQUIRE_APPROVAL"),
             rule("allow-shell", "shell", "echo *", "ALLOW")]
    assert evaluate(f"echo ok{separator}git push origin main", rules).decision.value == "REQUIRE_APPROVAL"


def test_existing_full_command_rule_still_applies():
    command = "echo ready && rm -rf build"
    decision = evaluate(command, [rule("complete-command", "shell", command, "BLOCK")])
    assert decision.rule_id == "complete-command"


def test_equal_priority_keeps_lexical_rule_order_across_segments():
    rules = [rule("z-shell", "shell", "rm -rf *", "BLOCK"),
             rule("a-git", "git", "git push *", "BLOCK")]
    assert evaluate("rm -rf build && git push origin main", rules).rule_id == "a-git"


@pytest.mark.parametrize("quoted", ["'a && b; c | d & e'", '"a || b; c | d & e"'])
def test_quoted_separators_are_not_split(quoted):
    assert split_shell_commands(f"echo {quoted} && git status") == (f"echo {quoted}", "git status")


@pytest.mark.parametrize("escaped", [r"echo a\;b", r"echo a\&b", "echo a`;b", "echo a`|b"])
def test_escaped_separator_is_preserved(escaped):
    assert split_shell_commands(f"{escaped} && git status") == (escaped, "git status")


def test_redirection_ampersand_is_not_a_command_separator():
    assert split_shell_commands("echo ok 2>&1 && git status") == ("echo ok 2>&1", "git status")


def test_empty_segments_are_ignored():
    assert split_shell_commands("\n echo ok;\n\n git status\n") == ("echo ok", "git status")
