"""Lanceur non interactif de Claude Code."""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

from pathtrace.runners.base import AgentRunner, RunRequest, RunResult, RunnerExecutionError


class ClaudeCodeRunner(AgentRunner):
    """Lance ``claude -p`` puis récupère la trace créée par les hooks."""

    name = "claude-code"

    def run(self, request: RunRequest) -> RunResult:
        project_dir = request.project_dir.resolve()
        command = self.build_command(request)
        known_traces = _snapshot_traces(project_dir, self.name)
        started = time.monotonic()

        try:
            completed = subprocess.run(
                command,
                cwd=project_dir,
                capture_output=True,
                text=True,
                timeout=request.timeout_seconds,
                check=False,
                env=os.environ.copy(),
            )
            exit_code = completed.returncode
            stdout = completed.stdout or ""
            stderr = completed.stderr or ""
            timed_out = False
        except FileNotFoundError as error:
            executable = command[0]
            raise RunnerExecutionError(
                f"Exécutable Claude Code introuvable : {executable}. "
                "Installe Claude Code ou configure executable."
            ) from error
        except subprocess.TimeoutExpired as error:
            exit_code = 124
            stdout = _text_output(error.stdout)
            stderr = _text_output(error.stderr) or (
                f"Claude Code a dépassé le délai de {request.timeout_seconds:g} secondes."
            )
            timed_out = True

        trace_path = _wait_for_trace(
            project_dir=project_dir,
            framework=self.name,
            known_traces=known_traces,
            prompt=request.prompt,
            session_id=_session_id(stdout),
            timeout_seconds=request.trace_timeout_seconds,
        )
        return RunResult(
            command=tuple(command),
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            duration_seconds=round(time.monotonic() - started, 3),
            trace_path=trace_path,
            timed_out=timed_out,
        )

    def build_command(self, request: RunRequest) -> list[str]:
        if "--bare" in request.runner_args:
            raise RunnerExecutionError(
                "L'option Claude Code --bare désactive les hooks nécessaires à Pathtrace."
            )
        executable = (
            request.executable
            or os.environ.get("PATHTRACE_CLAUDE_CODE_EXECUTABLE")
            or "claude"
        )
        return [
            executable,
            "-p",
            *request.runner_args,
            "--output-format",
            "json",
            request.prompt,
        ]


def _snapshot_traces(project_dir: Path, framework: str) -> dict[Path, int]:
    root = project_dir / ".pathtrace" / "traces" / framework
    if not root.is_dir():
        return {}
    return {path.resolve(): path.stat().st_mtime_ns for path in root.rglob("*.json") if path.is_file()}


def _wait_for_trace(
    *,
    project_dir: Path,
    framework: str,
    known_traces: dict[Path, int],
    prompt: str,
    session_id: str | None,
    timeout_seconds: float,
) -> Path | None:
    deadline = time.monotonic() + max(timeout_seconds, 0)
    while True:
        candidates = _new_traces(project_dir, framework, known_traces)
        if candidates:
            return _best_trace(candidates, prompt, session_id)
        if time.monotonic() >= deadline:
            return None
        time.sleep(0.05)


def _new_traces(project_dir: Path, framework: str, known: dict[Path, int]) -> list[Path]:
    root = project_dir / ".pathtrace" / "traces" / framework
    if not root.is_dir():
        return []
    candidates: list[Path] = []
    for path in root.rglob("*.json"):
        if not path.is_file():
            continue
        resolved = path.resolve()
        if resolved not in known or path.stat().st_mtime_ns > known[resolved]:
            candidates.append(path)
    return candidates


def _best_trace(candidates: list[Path], prompt: str, session_id: str | None) -> Path:
    metadata = [(path, _trace_data(path)) for path in candidates]
    combined = [
        path
        for path, data in metadata
        if data.get("prompt") == prompt
        and (session_id is None or data.get("session_id") == session_id)
    ]
    session_matches = [
        path for path, data in metadata if session_id is not None and data.get("session_id") == session_id
    ]
    prompt_matches = [path for path, data in metadata if data.get("prompt") == prompt]
    return max(combined or session_matches or prompt_matches or candidates, key=lambda path: path.stat().st_mtime_ns)


def _trace_data(path: Path) -> dict[str, Any]:
    try:
        value: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _session_id(stdout: str) -> str | None:
    candidates = [stdout, *reversed([line for line in stdout.splitlines() if line.strip()])]
    for candidate in candidates:
        try:
            value: Any = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            session_id = value.get("session_id")
            if isinstance(session_id, str) and session_id:
                return session_id
    return None


def _text_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    return value.decode(errors="replace") if isinstance(value, bytes) else value
