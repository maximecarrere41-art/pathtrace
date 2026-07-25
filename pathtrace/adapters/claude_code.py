"""Adaptateur Claude Code : hooks natifs -> modèle canonique Pathtrace."""

from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path
from typing import Any, Iterable

from pathtrace.adapters.base import AdapterInstallError, FrameworkAdapter
from pathtrace.capture import CaptureStore, safe_fragment
from pathtrace.model import build_trace, utc_now


HOOK_COMMAND_PREFIX = "pathtrace hook receive claude-code"
MANAGED_EVENTS = (
    "SessionStart",
    "SessionEnd",
    "UserPromptSubmit",
    "PreToolUse",
    "PostToolUse",
    "PostToolUseFailure",
    "Stop",
    "StopFailure",
)
EVENT_SLUGS = {
    "SessionStart": "session-start",
    "SessionEnd": "session-end",
    "UserPromptSubmit": "user-prompt-submit",
    "PreToolUse": "pre-tool-use",
    "PostToolUse": "post-tool-use",
    "PostToolUseFailure": "post-tool-use-failure",
    "Stop": "stop",
    "StopFailure": "stop-failure",
}
TOOL_EVENTS = {"PreToolUse", "PostToolUse", "PostToolUseFailure"}
SKILL_PATH = re.compile(
    r"(?:^|[\\/])skills[\\/]([^\\/]+)[\\/]SKILL\.md(?:$|\s|[\"'])",
    re.IGNORECASE,
)


class PathtraceClaudeHookConfigError(AdapterInstallError):
    """La configuration Claude Code existante empêche l'installation."""


def _claude_home() -> Path:
    configured_home = os.getenv("CLAUDE_CONFIG_DIR")
    if configured_home:
        return Path(configured_home).expanduser()
    return Path.home() / ".claude"


class ClaudeCodeAdapter(FrameworkAdapter):
    """Capture un tour Claude Code et le traduit au format Pathtrace v3."""

    name = "claude-code"

    def install(self, project_dir: Path) -> Path:
        """Fusionne les hooks Pathtrace dans les paramètres utilisateur Claude."""
        config_path = _claude_home() / "settings.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config = _read_existing_config(config_path)
        hooks = config.setdefault("hooks", {})
        if not isinstance(hooks, dict):
            raise PathtraceClaudeHookConfigError(
                f"{config_path} contient une propriété hooks qui n'est pas un objet JSON"
            )

        for event_name in MANAGED_EVENTS:
            entries = hooks.setdefault(event_name, [])
            if not isinstance(entries, list):
                raise PathtraceClaudeHookConfigError(
                    f"{config_path} contient hooks.{event_name} qui n'est pas une liste"
                )
            _ensure_entry(entries, event_name)

        config_path.write_text(
            json.dumps(config, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return config_path

    def handle(
        self,
        event_slug: str,
        payload: dict[str, Any],
        project_dir: Path,
    ) -> Path | None:
        session_id = _text(payload, "session_id", "sessionId") or "unknown-session"
        store = CaptureStore(project_dir, self.name)

        if event_slug == "session-start":
            state = store.load(session_id, "session")
            state["model"] = _model(payload)
            store.save(session_id, "session", state)
            return None

        if event_slug == "session-end":
            store.remove(session_id, "session")
            return None

        if event_slug == "user-prompt-submit":
            previous = store.load(session_id, "session")
            state = {
                "events": [],
                "prompt": _prompt(payload),
                "model": _preferred_model(payload, previous),
                "turn_id": _turn_id(payload),
                "started_at": utc_now(),
            }
            store.save(session_id, "current", state)
            return None

        if event_slug in {"pre-tool-use", "post-tool-use", "post-tool-use-failure"}:
            state = _load_turn_state(store, session_id, payload)
            event = _to_event(payload, event_slug)
            if event is not None:
                _upsert_event(state.setdefault("events", []), event, event_slug)
            store.save(session_id, "current", state)
            return None

        if event_slug in {"stop", "stop-failure"}:
            return _finalize(
                payload=payload,
                project_dir=project_dir,
                store=store,
                session_id=session_id,
                failed=event_slug == "stop-failure",
            )

        raise ValueError(f"Événement Claude Code non supporté : {event_slug}")


def _read_existing_config(config_path: Path) -> dict[str, Any]:
    if not config_path.is_file():
        return {}
    try:
        value = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise PathtraceClaudeHookConfigError(
            f"{config_path} existe mais n'est pas un JSON valide. Corrige-le avant l'installation."
        ) from error
    if not isinstance(value, dict):
        raise PathtraceClaudeHookConfigError(f"{config_path} doit contenir un objet JSON")
    return value


def _ensure_entry(entries: list[Any], event_name: str) -> None:
    command = f"{HOOK_COMMAND_PREFIX} {EVENT_SLUGS[event_name]}"
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        hooks = entry.get("hooks", [])
        if not isinstance(hooks, list):
            continue
        if any(isinstance(hook, dict) and hook.get("command") == command for hook in hooks):
            return

    entry: dict[str, Any] = {
        "hooks": [{"type": "command", "command": command}],
    }
    if event_name in TOOL_EVENTS:
        entry["matcher"] = "*"
    entries.append(entry)


def _load_turn_state(
    store: CaptureStore,
    session_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    state = store.load(session_id, "current")
    state.setdefault("events", [])
    state.setdefault("turn_id", _turn_id(payload))
    state.setdefault("prompt", _prompt(payload))
    session_state = store.load(session_id, "session")
    state.setdefault("model", _preferred_model(payload, session_state))
    state.setdefault("started_at", utc_now())
    return state


def _to_event(payload: dict[str, Any], hook: str) -> dict[str, Any] | None:
    tool_name = _text(payload, "tool_name", "toolName", "name")
    if not tool_name:
        return None

    tool_input = payload.get("tool_input", payload.get("toolInput", {}))
    if not isinstance(tool_input, dict):
        tool_input = {"value": tool_input}

    command = _first_text(tool_input, ("command", "cmd", "script"))
    path = _first_text(tool_input, ("file_path", "filePath", "path"))
    skill_name, skill_path = _extract_skill(tool_name, tool_input)
    call_id = _text(payload, "tool_use_id", "toolUseId", "call_id", "callId", "id")
    raw = {
        "hook": hook,
        "call_id": call_id,
        "duration_ms": payload.get("duration_ms"),
        "transcript_path": _text(payload, "transcript_path", "transcriptPath"),
    }

    event: dict[str, Any] = {
        "type": "skill" if skill_name else "tool_call",
        "name": skill_name or tool_name,
        "tool": tool_name if skill_name else None,
        "command": command,
        "path": skill_path or path,
        "input": tool_input or None,
        "status": _event_status(payload, hook),
        "output_summary": _output_summary(payload, hook),
        "raw": {key: value for key, value in raw.items() if value is not None},
        "_call_id": call_id,
        "_pending": hook == "pre-tool-use",
    }
    return {key: value for key, value in event.items() if value is not None}


def _upsert_event(events: list[dict[str, Any]], event: dict[str, Any], hook: str) -> None:
    call_id = event.get("_call_id")
    existing = _find_pending(events, call_id, event)
    if existing is None:
        events.append(event)
        return

    for key, value in event.items():
        if value is not None:
            existing[key] = value
    if hook != "pre-tool-use":
        existing["_pending"] = False


def _find_pending(
    events: list[dict[str, Any]],
    call_id: Any,
    event: dict[str, Any],
) -> dict[str, Any] | None:
    if call_id:
        return next((item for item in events if item.get("_call_id") == call_id), None)
    for item in reversed(events):
        if item.get("_pending") and item.get("name") == event.get("name"):
            return item
    return None


def _finalize(
    *,
    payload: dict[str, Any],
    project_dir: Path,
    store: CaptureStore,
    session_id: str,
    failed: bool,
) -> Path:
    state = _load_turn_state(store, session_id, payload)
    events = state.get("events", [])
    for event in events:
        if event.get("status") == "running":
            event["status"] = "unknown"

    turn_id = str(state.get("turn_id") or _turn_id(payload))
    trace = build_trace(
        framework="claude-code",
        session_id=session_id,
        turn_id=turn_id,
        prompt=_prompt(payload) or str(state.get("prompt") or ""),
        model=_preferred_model(payload, state),
        events=events,
        status="failure" if failed or _has_failure(events) else "success",
        started_at=str(state.get("started_at") or utc_now()),
    )
    output_path = (
        project_dir
        / ".pathtrace"
        / "traces"
        / "claude-code"
        / safe_fragment(session_id)
        / f"{safe_fragment(turn_id)}.json"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(trace, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    store.remove(session_id, "current")
    return output_path


def _extract_skill(tool_name: str, tool_input: dict[str, Any]) -> tuple[str | None, str | None]:
    if tool_name.lower() in {"skill", "skills"}:
        name = _first_text(tool_input, ("skill", "skill_name", "skillName", "name"))
        if name:
            return name, None

    for value in _string_values(tool_input):
        match = SKILL_PATH.search(value)
        if match:
            return match.group(1), match.group(0).strip(" \"'")
    return None, None


def _string_values(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _string_values(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _string_values(item)


def _event_status(payload: dict[str, Any], hook: str) -> str:
    if hook == "pre-tool-use":
        return "running"
    if hook == "post-tool-use-failure":
        return "failure"
    response = payload.get("tool_response", payload.get("toolResponse"))
    if isinstance(response, dict):
        if response.get("success") is False or response.get("error"):
            return "failure"
        status = response.get("status")
        if isinstance(status, str) and status.lower() in {"failed", "failure", "error"}:
            return "failure"
    return "failure" if payload.get("error") else "success"


def _output_summary(payload: dict[str, Any], hook: str) -> str | None:
    if hook == "post-tool-use-failure":
        error = payload.get("error")
        return str(error)[:500] if error not in (None, "") else None

    response = payload.get("tool_response", payload.get("toolResponse"))
    if response is None:
        return None
    if isinstance(response, dict):
        for key in ("output", "content", "message", "error"):
            value = response.get(key)
            if value not in (None, ""):
                return str(value)[:500]
    return str(response)[:500]


def _has_failure(events: list[dict[str, Any]]) -> bool:
    return any(event.get("status") == "failure" for event in events)


def _prompt(payload: dict[str, Any]) -> str:
    return _text(payload, "prompt", "user_prompt", "userPrompt", "message") or ""


def _model(payload: dict[str, Any]) -> str:
    return _text(payload, "model", "model_name", "modelName") or "unknown"


def _preferred_model(payload: dict[str, Any], state: dict[str, Any]) -> str:
    payload_model = _model(payload)
    if payload_model != "unknown":
        return payload_model
    return str(state.get("model") or "unknown")


def _turn_id(payload: dict[str, Any]) -> str:
    return _text(payload, "turn_id", "turnId") or f"turn-{uuid.uuid4().hex}"


def _first_text(data: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    return _text(data, *keys)


def _text(data: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
    return None
