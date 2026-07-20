"""Lanceur non interactif de Codex CLI."""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

from pathtrace.runners.base import AgentRunner, RunRequest, RunResult, RunnerExecutionError


class CodexRunner(AgentRunner):
    """Lance ``codex exec`` puis récupère la trace créée par les hooks."""

    name = "codex"

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
                f"Exécutable Codex introuvable : {executable}. Installe Codex CLI ou configure executable."
            ) from error
        except subprocess.TimeoutExpired as error:
            exit_code = 124
            stdout = _text_output(error.stdout)
            stderr = _text_output(error.stderr) or (
                f"Codex a dépassé le délai de {request.timeout_seconds:g} secondes."
            )
            timed_out = True

        trace_path = _wait_for_trace(
            project_dir=project_dir,
            framework=self.name,
            known_traces=known_traces,
            prompt=request.prompt,
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
        executable = request.executable or os.environ.get("PATHTRACE_CODEX_EXECUTABLE") or "codex"
        return [executable, "exec", "--json", *request.runner_args, request.prompt]


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
    timeout_seconds: float,
) -> Path | None:
    deadline = time.monotonic() + max(timeout_seconds, 0)
    while True:
        candidates = _new_traces(project_dir, framework, known_traces)
        if candidates:
            exact = [path for path in candidates if _trace_prompt(path) == prompt]
            return max(exact or candidates, key=lambda path: path.stat().st_mtime_ns)
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


def _trace_prompt(path: Path) -> str | None:
    try:
        data: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    value = data.get("prompt") if isinstance(data, dict) else None
    return value if isinstance(value, str) else None


def _text_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    return value.decode(errors="replace") if isinstance(value, bytes) else value
