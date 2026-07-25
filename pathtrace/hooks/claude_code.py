"""Compatibilité avec l'import ``pathtrace.hooks.claude_code``."""

from pathlib import Path
from typing import Any

from pathtrace.adapters.claude_code import ClaudeCodeAdapter, PathtraceClaudeHookConfigError


_adapter = ClaudeCodeAdapter()


def install(project_dir: Path) -> Path:
    return _adapter.install(project_dir)


def handle(event_slug: str, payload: dict[str, Any], project_dir: Path) -> Path | None:
    return _adapter.handle(event_slug, payload, project_dir)
