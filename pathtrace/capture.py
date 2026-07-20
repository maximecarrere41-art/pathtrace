"""Persistance temporaire partagée par les adaptateurs de framework."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


class CaptureStore:
    def __init__(self, project_dir: Path, framework: str) -> None:
        self.project_dir = project_dir
        self.framework = framework

    def load(self, session_id: str, turn_id: str) -> dict[str, Any]:
        path = self.path(session_id, turn_id)
        if not path.is_file() and turn_id != "current":
            current = self.path(session_id, "current")
            if current.is_file():
                path = current
        if not path.is_file():
            return {"events": []}
        return json.loads(path.read_text(encoding="utf-8"))

    def save(self, session_id: str, turn_id: str, state: dict[str, Any]) -> Path:
        path = self.path(session_id, turn_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return path

    def remove(self, session_id: str, turn_id: str) -> None:
        candidates = {self.path(session_id, turn_id), self.path(session_id, "current")}
        for path in candidates:
            if path.is_file():
                path.unlink()

    def path(self, session_id: str, turn_id: str) -> Path:
        return (
            self.project_dir
            / ".pathtrace"
            / ".state"
            / _safe(self.framework)
            / _safe(session_id)
            / f"{_safe(turn_id)}.json"
        )


def safe_fragment(value: str) -> str:
    return _safe(value)


def _safe(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return cleaned or "unknown"
