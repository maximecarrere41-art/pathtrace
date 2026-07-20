"""Modèle canonique, volontairement petit, commun à tous les agents."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


TRACE_VERSION = 3
EVENT_TYPES = {"tool_call", "skill"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_trace(data: dict[str, Any]) -> dict[str, Any]:
    """Convertit une trace v2 ou v3 vers le modèle v3 utilisé par le moteur."""
    raw_events = data.get("events")
    if not isinstance(raw_events, list):
        legacy_tools = data.get("tools")
        raw_events = legacy_tools if isinstance(legacy_tools, list) else []

    events = [normalize_event(event, index) for index, event in enumerate(raw_events)]
    session_id = str(data.get("session_id") or "unknown-session")
    turn_id = str(data.get("turn_id") or "unknown-turn")

    trace = {
        "version": TRACE_VERSION,
        "id": str(data.get("id") or data.get("trace_id") or f"{session_id}:{turn_id}"),
        "session_id": session_id,
        "turn_id": turn_id,
        "prompt": str(data.get("prompt") or data.get("task") or ""),
        "model": str(data.get("model") or "unknown"),
        "framework": str(data.get("framework") or "unknown"),
        "status": str(data.get("status") or _trace_status(events)),
        "events": events,
        "summary": build_summary(events),
    }
    for field in ("started_at", "ended_at"):
        if isinstance(data.get(field), str):
            trace[field] = data[field]
    return trace


def normalize_event(event: Any, index: int) -> dict[str, Any]:
    if not isinstance(event, dict):
        return {"index": index, "type": "tool_call", "name": "unknown"}

    normalized = dict(event)
    normalized["index"] = index
    normalized["type"] = str(event.get("type") or "tool_call")
    normalized["name"] = str(event.get("name") or "unknown")
    return normalized


def build_trace(
    *,
    framework: str,
    session_id: str,
    turn_id: str,
    prompt: str,
    model: str,
    events: list[dict[str, Any]],
    status: str | None = None,
    started_at: str | None = None,
    ended_at: str | None = None,
) -> dict[str, Any]:
    clean_events = [_public_event(event, index) for index, event in enumerate(events)]
    return {
        "version": TRACE_VERSION,
        "id": f"{framework}:{session_id}:{turn_id}",
        "session_id": session_id,
        "turn_id": turn_id,
        "prompt": prompt,
        "model": model,
        "framework": framework,
        "status": status or _trace_status(clean_events),
        "started_at": started_at or utc_now(),
        "ended_at": ended_at or utc_now(),
        "summary": build_summary(clean_events),
        "events": clean_events,
    }


def build_summary(events: list[dict[str, Any]]) -> dict[str, list[str]]:
    skills: list[str] = []
    commands: list[str] = []
    tools: list[str] = []

    for event in events:
        if event.get("type") == "skill":
            _append_unique(skills, event.get("name"))
        command = event.get("command")
        if isinstance(command, str) and command:
            _append_unique(commands, command)
        tool = event.get("tool") if event.get("type") == "skill" else event.get("name")
        _append_unique(tools, tool)

    return {"skills": skills, "commands": commands, "tools": tools}


def _public_event(event: dict[str, Any], index: int) -> dict[str, Any]:
    public = {
        key: value
        for key, value in event.items()
        if not key.startswith("_") and value is not None
    }
    public["index"] = index
    public["type"] = str(public.get("type") or "tool_call")
    public["name"] = str(public.get("name") or "unknown")
    return public


def _trace_status(events: list[dict[str, Any]]) -> str:
    return "failure" if any(event.get("status") == "failure" for event in events) else "success"


def _append_unique(values: list[str], value: Any) -> None:
    if isinstance(value, str) and value and value not in values:
        values.append(value)
