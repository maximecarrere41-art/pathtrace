"""Registre des lanceurs disponibles."""

from __future__ import annotations

from pathtrace.runners.base import AgentRunner
from pathtrace.runners.claude_code import ClaudeCodeRunner
from pathtrace.runners.codex import CodexRunner


_RUNNERS: dict[str, AgentRunner] = {
    "claude-code": ClaudeCodeRunner(),
    "codex": CodexRunner(),
}


def available_runners() -> tuple[str, ...]:
    return tuple(sorted(_RUNNERS))


def get_runner(name: str) -> AgentRunner:
    try:
        return _RUNNERS[name]
    except KeyError as error:
        supported = ", ".join(available_runners())
        raise ValueError(f"Runner non supporté : {name}. Disponibles : {supported}") from error
