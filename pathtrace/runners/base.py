"""Contrat commun aux lanceurs d'agents."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


class RunnerExecutionError(RuntimeError):
    """Le processus de l'agent n'a pas pu être lancé."""


@dataclass(frozen=True)
class RunRequest:
    """Entrée minimale nécessaire pour exécuter un prompt."""

    prompt: str
    project_dir: Path
    timeout_seconds: float = 600
    trace_timeout_seconds: float = 10
    executable: str | None = None
    runner_args: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class RunResult:
    """Résultat technique du processus, distinct du résultat des assertions."""

    command: tuple[str, ...]
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    trace_path: Path | None
    timed_out: bool = False

    @property
    def process_passed(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


class AgentRunner(ABC):
    """Lance un agent en mode non interactif pour un prompt donné."""

    name: str

    @abstractmethod
    def run(self, request: RunRequest) -> RunResult:
        """Exécute le prompt et retourne la trace produite par l'adaptateur."""
