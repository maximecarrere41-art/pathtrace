"""Contrat minimal d'un adaptateur Pathtrace."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class AdapterInstallError(ValueError):
    """La configuration native du framework empêche l'installation."""


class FrameworkAdapter(ABC):
    """Traduit les événements natifs d'un agent vers la trace canonique."""

    name: str

    @abstractmethod
    def install(self, project_dir: Path) -> Path:
        """Installe la capture passive native au framework."""

    @abstractmethod
    def handle(
        self,
        event_slug: str,
        payload: dict[str, Any],
        project_dir: Path,
    ) -> Path | None:
        """Traite un événement natif et retourne la trace lorsqu'elle est finalisée."""
