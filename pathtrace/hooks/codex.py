"""Compatibilité avec l'ancien import ``pathtrace.hooks.codex``."""

from pathlib import Path
from typing import Any

from pathtrace.adapters.codex import CodexAdapter, PathtraceHookConfigError


_adapter = CodexAdapter()


def install(project_dir: Path) -> Path:
    return _adapter.install(project_dir)


def handle(event_slug: str, payload: dict[str, Any], project_dir: Path) -> Path | None:
    return _adapter.handle(event_slug, payload, project_dir)
