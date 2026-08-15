"""Adaptateur Codex : hooks natifs -> modèle canonique Pathtrace."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Iterable

from pathtrace.adapters.base import (
    AdapterInstallError,
    FrameworkAdapter,
    SecurityEnforcement,
)
from pathtrace.capture import CaptureStore, safe_fragment
from pathtrace.config import Feature
from pathtrace.model import build_trace, utc_now
from pathtrace.security.action import build_security_action
from pathtrace.security.model import (
    SecurityAction,
    SecurityDecision,
    SecurityDecisionType,
)


HOOK_COMMAND_PREFIX = "pathtrace hook receive codex"
MANAGED_EVENTS = ("UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop")
EVENT_SLUGS = {
    "UserPromptSubmit": "user-prompt-submit",
    "PreToolUse": "pre-tool-use",
    "PostToolUse": "post-tool-use",
    "Stop": "stop",
}
SKILL_PATH = re.compile(r"(?:^|[\\/])skills[\\/]([^\\/]+)[\\/]SKILL\.md(?:$|\s|[\"'])", re.IGNORECASE)


class PathtraceHookConfigError(AdapterInstallError):
    """La configuration hooks existante est illisible."""


def _codex_home() -> Path:
    """Retourne le répertoire global utilisé par Codex."""
    configured_home = os.getenv("CODEX_HOME")
    if configured_home:
        return Path(configured_home).expanduser()
    return Path.home() / ".codex"


class CodexAdapter(FrameworkAdapter):
    name = "codex"

    def install(
        self,
        project_dir: Path,
        features: frozenset[Feature] = frozenset({Feature.OBSERVE}),
    ) -> Path:
        # Les hooks Codex sont globaux et ne doivent pas dépendre
        # du répertoire courant depuis lequel la commande est lancée.
        config_path = _codex_home() / "hooks.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config = _read_existing_config(config_path)
        hooks = config.setdefault("hooks", {})

        managed_events = set(MANAGED_EVENTS) if Feature.OBSERVE in features else set()
        if Feature.SECURITY in features:
            managed_events.add("PreToolUse")
        for event_name in MANAGED_EVENTS:
            if event_name not in managed_events:
                continue
            entries = hooks.setdefault(event_name, [])
            _ensure_entry(
                entries,
                event_name,
                configured_only=(
                    event_name == "PreToolUse"
                    and Feature.OBSERVE not in features
                ),
                security_enabled=(
                    event_name == "PreToolUse"
                    and Feature.SECURITY in features
                ),
            )

        config_path.write_text(
            json.dumps(config, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return config_path

    def uninstall(self, project_dir: Path) -> Path:
        """Retire uniquement les hooks Pathtrace de la configuration Codex."""
        config_path = _codex_home() / "hooks.json"
        if not config_path.is_file():
            return config_path
        config = _read_existing_config(config_path)
        hooks = config.get("hooks")
        if hooks is None:
            return config_path
        if not isinstance(hooks, dict):
            raise PathtraceHookConfigError(
                f"{config_path} contient une propriété hooks qui n'est pas un objet JSON"
            )
        if not _remove_managed_hooks(hooks, config_path):
            return config_path
        if not hooks:
            config.pop("hooks")
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
        turn_id = _text(payload, "turn_id", "turnId") or "current"
        store = CaptureStore(project_dir, self.name)

        if event_slug == "user-prompt-submit":
            state = store.load(session_id, turn_id)
            state["prompt"] = _prompt(payload)
            state["model"] = _model(payload)
            state.setdefault("started_at", utc_now())
            store.save(session_id, turn_id, state)
            return None

        if event_slug in {"pre-tool-use", "post-tool-use"}:
            state = store.load(session_id, turn_id)
            event = _to_event(payload, event_slug)
            if event is not None:
                _upsert_event(state.setdefault("events", []), event, event_slug)
            state.setdefault("started_at", utc_now())
            state.setdefault("model", _model(payload))
            store.save(session_id, turn_id, state)
            return None

        if event_slug == "stop":
            return _finalize(payload, project_dir, store, session_id, turn_id)

        raise ValueError(f"Événement Codex non supporté : {event_slug}")

    def to_security_action(self, payload: dict[str, Any]) -> SecurityAction:
        return build_security_action(
            framework=self.name,
            session_id=_text(payload, "session_id", "sessionId"),
            turn_id=_text(payload, "turn_id", "turnId"),
            tool=_text(payload, "tool_name", "toolName", "name"),
            tool_input=payload.get("tool_input", payload.get("toolInput")),
            cwd=_text(payload, "cwd", "working_directory", "workingDirectory"),
        )

    def enforce_security(self, decision: SecurityDecision) -> SecurityEnforcement:
        if decision.decision is SecurityDecisionType.ALLOW:
            return SecurityEnforcement(response=None, result="allowed_by_policy")
        reason = decision.reason
        result = "blocked"
        approval_status = None
        if decision.decision is SecurityDecisionType.REQUIRE_APPROVAL:
            reason = f"{reason} Codex PreToolUse ne supporte pas la demande de validation."
            result = "blocked_approval_unsupported"
            approval_status = "unsupported"
        response = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        }
        return SecurityEnforcement(
            response=response,
            result=result,
            approval_status=approval_status,
        )


def _read_existing_config(config_path: Path) -> dict[str, Any]:
    if not config_path.is_file():
        return {}
    try:
        value = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise PathtraceHookConfigError(
            f"{config_path} existe mais n'est pas un JSON valide. Corrige-le avant l'installation."
        ) from error
    if not isinstance(value, dict):
        raise PathtraceHookConfigError(f"{config_path} doit contenir un objet JSON")
    return value


def _ensure_entry(
    entries: list[dict[str, Any]],
    event_name: str,
    *,
    configured_only: bool = False,
    security_enabled: bool = False,
) -> None:
    base_command = f"{HOOK_COMMAND_PREFIX} {EVENT_SLUGS[event_name]}"
    flags = []
    if configured_only:
        flags.append("--configured-only")
    if security_enabled:
        flags.append("--security-enabled")
    command = " ".join((base_command, *flags))
    managed_commands = {
        base_command,
        f"{base_command} --configured-only",
        f"{base_command} --security-enabled",
        f"{base_command} --configured-only --security-enabled",
    }
    for entry in entries:
        for hook in entry.get("hooks", []):
            existing = hook.get("command")
            if existing in managed_commands:
                existing_security = "--security-enabled" in existing
                existing_configured_only = "--configured-only" in existing
                merged_flags = []
                if existing_configured_only and configured_only:
                    merged_flags.append("--configured-only")
                if existing_security or security_enabled:
                    merged_flags.append("--security-enabled")
                hook["command"] = " ".join((base_command, *merged_flags))
                return
    entries.append({"matcher": "*", "hooks": [{"type": "command", "command": command}]})


def _remove_managed_hooks(hooks: dict[str, Any], config_path: Path) -> bool:
    changed = False
    for event_name in MANAGED_EVENTS:
        entries = hooks.get(event_name)
        if entries is None:
            continue
        if not isinstance(entries, list):
            raise PathtraceHookConfigError(
                f"{config_path} contient hooks.{event_name} qui n'est pas une liste"
            )
        remaining_entries = []
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("hooks"), list):
                remaining_entries.append(entry)
                continue
            remaining_hooks = [
                hook
                for hook in entry["hooks"]
                if not _is_managed_hook(hook, event_name)
            ]
            if len(remaining_hooks) == len(entry["hooks"]):
                remaining_entries.append(entry)
                continue
            changed = True
            if remaining_hooks:
                updated_entry = dict(entry)
                updated_entry["hooks"] = remaining_hooks
                remaining_entries.append(updated_entry)
        if remaining_entries:
            hooks[event_name] = remaining_entries
        elif event_name in hooks:
            hooks.pop(event_name)
    return changed


def _is_managed_hook(hook: Any, event_name: str) -> bool:
    if not isinstance(hook, dict):
        return False
    command = hook.get("command")
    if not isinstance(command, str):
        return False
    base_parts = f"{HOOK_COMMAND_PREFIX} {EVENT_SLUGS[event_name]}".split()
    command_parts = command.split()
    flags = command_parts[len(base_parts) :]
    return (
        command_parts[: len(base_parts)] == base_parts
        and all(flag in {"--configured-only", "--security-enabled"} for flag in flags)
    )


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

    event: dict[str, Any] = {
        "type": "skill" if skill_name else "tool_call",
        "name": skill_name or tool_name,
        "tool": tool_name if skill_name else None,
        "command": command,
        "path": skill_path or path,
        "input": tool_input or None,
        "status": "running" if hook == "pre-tool-use" else _status(payload),
        "output_summary": _output_summary(payload) if hook == "post-tool-use" else None,
        "raw": {
            "hook": hook,
            "call_id": call_id,
        },
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
    if hook == "post-tool-use":
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
    payload: dict[str, Any],
    project_dir: Path,
    store: CaptureStore,
    session_id: str,
    requested_turn_id: str,
) -> Path:
    state = store.load(session_id, requested_turn_id)
    turn_id = requested_turn_id
    if turn_id == "current":
        turn_id = _text(payload, "turn_id", "turnId") or "current"

    events = state.get("events", [])
    for event in events:
        if event.get("status") == "running":
            event["status"] = "unknown"

    trace = build_trace(
        framework="codex",
        session_id=session_id,
        turn_id=turn_id,
        prompt=_prompt(payload) or str(state.get("prompt") or ""),
        model=_model(payload) if _model(payload) != "unknown" else str(state.get("model") or "unknown"),
        events=events,
        status=_stop_status(payload, events),
        started_at=str(state.get("started_at") or utc_now()),
    )

    output_path = (
        project_dir
        / ".pathtrace"
        / "traces"
        / "codex"
        / safe_fragment(session_id)
        / f"{safe_fragment(turn_id)}.json"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(trace, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    store.remove(session_id, requested_turn_id)
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
    elif isinstance(value, list):
        for item in value:
            yield from _string_values(item)


def _status(payload: dict[str, Any]) -> str:
    response = payload.get("tool_response", payload.get("toolResponse"))
    if isinstance(response, dict):
        if response.get("success") is False or response.get("error"):
            return "failure"
        status = response.get("status")
        if isinstance(status, str):
            return "failure" if status.lower() in {"failed", "failure", "error"} else "success"
    if payload.get("error"):
        return "failure"
    return "success"


def _stop_status(payload: dict[str, Any], events: list[dict[str, Any]]) -> str:
    if payload.get("error") or any(event.get("status") == "failure" for event in events):
        return "failure"
    return "success"


def _output_summary(payload: dict[str, Any]) -> str | None:
    response = payload.get("tool_response", payload.get("toolResponse"))
    if response is None:
        return None
    if isinstance(response, dict):
        for key in ("output", "content", "message", "error"):
            value = response.get(key)
            if value not in (None, ""):
                return str(value)[:500]
    return str(response)[:500]


def _prompt(payload: dict[str, Any]) -> str:
    return _text(payload, "prompt", "user_prompt", "userPrompt", "message") or ""


def _model(payload: dict[str, Any]) -> str:
    return _text(payload, "model", "model_name", "modelName") or "unknown"


def _first_text(data: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    return _text(data, *keys)


def _text(data: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
    return None
