"""Contrat minimal d'un adaptateur Pathtrace."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from pathtrace.config import Feature
from pathtrace.security.model import SecurityAction, SecurityDecision


class AdapterInstallError(ValueError):
    """La configuration native du framework empêche l'installation."""


class FrameworkAdapter(ABC):
    """Traduit les événements natifs d'un agent vers la trace canonique."""

    name: str

    @abstractmethod
    def install(
        self,
        project_dir: Path,
        features: frozenset[Feature] = frozenset({Feature.OBSERVE}),
    ) -> Path:
        """Installe les hooks nécessaires aux capacités demandées."""

    @abstractmethod
    def uninstall(self, project_dir: Path) -> Path:
        """Retire les hooks gérés par Pathtrace sans toucher aux hooks utilisateur."""

    @abstractmethod
    def handle(
        self,
        event_slug: str,
        payload: dict[str, Any],
        project_dir: Path,
    ) -> Path | None:
        """Traite un événement natif et retourne la trace lorsqu'elle est finalisée."""

    def to_security_action(self, payload: dict[str, Any]) -> SecurityAction:
        """Traduit un PreToolUse natif vers une action Security canonique."""
        raise NotImplementedError(f"{self.name} ne supporte pas Runtime Security")

    def enforce_security(self, decision: SecurityDecision) -> SecurityEnforcement:
        """Traduit une décision Security vers la réponse native du framework."""
        raise NotImplementedError(f"{self.name} ne supporte pas Runtime Security")


class SecurityEnforcement:
    def __init__(
        self,
        *,
        response: dict[str, Any] | None,
        result: str,
        approval_status: str | None = None,
    ) -> None:
        self.response = response
        self.result = result
        self.approval_status = approval_status
