"""Activation locale des capacités Pathtrace."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Iterable

import yaml


CONFIG_VERSION = 1
CONFIG_PATH = Path(".pathtrace/config.yaml")


class ProjectConfigError(ValueError):
    """La configuration locale Pathtrace est invalide."""


class Feature(str, Enum):
    OBSERVE = "observe"
    SECURITY = "security"


class InstallTarget(str, Enum):
    OBSERVE = "observe"
    SECURITY = "security"
    ALL = "all"

    @property
    def features(self) -> frozenset[Feature]:
        if self is InstallTarget.ALL:
            return frozenset(Feature)
        return frozenset({Feature(self.value)})


@dataclass(frozen=True)
class ProjectConfig:
    features: frozenset[Feature]
    security: dict[str, Any] | None = None
    frameworks: dict[str, frozenset[Feature]] | None = None
    explicit: bool = True

    def features_for(self, framework: str) -> frozenset[Feature]:
        if not self.explicit or self.frameworks is None:
            return self.features
        return self.frameworks.get(framework, frozenset())


def load_project_config(project_dir: Path) -> ProjectConfig:
    """Charge la configuration, avec Observe comme comportement historique."""
    path = project_dir / CONFIG_PATH
    if not path.is_file():
        return ProjectConfig(
            features=frozenset({Feature.OBSERVE}),
            frameworks={},
            explicit=False,
        )
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise ProjectConfigError(f"{path} n'est pas un YAML valide") from error
    if not isinstance(value, dict):
        raise ProjectConfigError(f"{path} doit contenir un objet YAML")
    if value.get("version") != CONFIG_VERSION:
        raise ProjectConfigError(f"{path} doit déclarer version: {CONFIG_VERSION}")

    features = _parse_features(value.get("features"), f"{path}.features")

    raw_frameworks = value.get("frameworks")
    frameworks = None
    if raw_frameworks is not None:
        if not isinstance(raw_frameworks, dict):
            raise ProjectConfigError(f"{path}.frameworks doit être un objet")
        frameworks = {}
        for framework, raw_framework_features in raw_frameworks.items():
            if not isinstance(framework, str) or not framework.strip():
                raise ProjectConfigError(
                    f"{path}.frameworks doit utiliser des noms non vides"
                )
            frameworks[framework] = _parse_features(
                raw_framework_features,
                f"{path}.frameworks.{framework}",
            )
        union = frozenset(
            feature
            for framework_features in frameworks.values()
            for feature in framework_features
        )
        if union != features:
            raise ProjectConfigError(
                f"{path}.features doit être l'union des features par framework"
            )

    security = value.get("security")
    if security is not None and not isinstance(security, dict):
        raise ProjectConfigError(f"{path}.security doit être un objet")
    return ProjectConfig(
        features=features,
        security=security,
        frameworks=frameworks,
    )


def prepare_activation(
    project_dir: Path,
    target: InstallTarget,
    framework: str,
) -> ProjectConfig:
    """Calcule une activation additive sans modifier le repository."""
    current = load_project_config(project_dir)
    if current.explicit and current.frameworks is None:
        if target.features <= current.features:
            return current
        frameworks = {framework: current.features | target.features}
    else:
        frameworks = dict(current.frameworks or {})
        frameworks[framework] = (
            frameworks.get(framework, frozenset()) | target.features
        )
    features = frozenset(
        feature
        for framework_features in frameworks.values()
        for feature in framework_features
    )
    security = current.security
    if Feature.SECURITY in features and security is None:
        security = {
            "mode": "enforce",
            "rules": [],
            "telemetry": {"enabled": False},
        }
    return ProjectConfig(
        features=features,
        security=security,
        frameworks=frameworks,
    )


def write_project_config(project_dir: Path, config: ProjectConfig) -> Path:
    """Écrit la configuration seulement lorsque son contenu change."""
    path = project_dir / CONFIG_PATH
    if path.is_file():
        current = load_project_config(project_dir)
        if (
            current.features == config.features
            and current.security == config.security
            and current.frameworks == config.frameworks
        ):
            return path
    value: dict[str, Any] = {
        "version": CONFIG_VERSION,
        "features": _ordered_features(config.features),
    }
    if config.frameworks is not None:
        value["frameworks"] = {
            framework: _ordered_features(features)
            for framework, features in sorted(config.frameworks.items())
        }
    if config.security is not None:
        value["security"] = config.security
    content = yaml.safe_dump(value, sort_keys=False, allow_unicode=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _ordered_features(features: Iterable[Feature]) -> list[str]:
    order = (Feature.OBSERVE, Feature.SECURITY)
    return [feature.value for feature in order if feature in features]


def _parse_features(raw: Any, field: str) -> frozenset[Feature]:
    if not isinstance(raw, list) or not raw:
        raise ProjectConfigError(f"{field} doit être une liste non vide")
    try:
        return frozenset(Feature(item) for item in raw)
    except (TypeError, ValueError) as error:
        raise ProjectConfigError(
            f"{field} accepte uniquement observe et security"
        ) from error
