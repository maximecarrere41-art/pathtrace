from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from pathtrace.config import Feature, ProjectConfig
from pathtrace.provider_paths import provider_security_path
from pathtrace.security.config import SecurityConfigError


@dataclass(frozen=True)
class SecuritySource:
    scope: str
    raw: dict[str, Any]


def read_provider_config(framework: str) -> dict[str, Any] | None:
    path = provider_security_path(framework)
    if not path.is_file():
        return None
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise SecurityConfigError(f"{path}: {type(error).__name__}") from error
    return _validate_provider(value, path)


def _validate_provider(value: Any, path: Path) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("version") != 1:
        raise SecurityConfigError(f"{path} doit déclarer version: 1")
    if not isinstance(value.get("enabled", True), bool):
        raise SecurityConfigError(f"{path}.enabled doit être un booléen")
    if not isinstance(value.get("security", {}), dict):
        raise SecurityConfigError(f"{path}.security doit être un objet")
    return value


def provider_source(framework: str) -> SecuritySource | None:
    if framework not in {"codex", "claude-code"}:
        return None
    value = read_provider_config(framework)
    if value is None or not value.get("enabled", True):
        return None
    return SecuritySource("provider", value.get("security", {}))


def security_sources(framework: str, config: ProjectConfig) -> list[SecuritySource]:
    provider = provider_source(framework)
    sources = [provider] if provider else []
    if Feature.SECURITY in config.features_for(framework):
        sources.append(SecuritySource("project", config.security or {}))
    return sources


def write_initial_provider_config(framework: str, initial_security: dict[str, Any]) -> Path:
    path = provider_security_path(framework)
    if path.exists():
        return path
    return _write_provider(path, {"version": 1, "security": initial_security})


def remove_provider_config(framework: str) -> Path:
    path = provider_security_path(framework)
    path.unlink(missing_ok=True)
    return path


def _write_provider(path: Path, value: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as stream:
            stream.write(yaml.safe_dump(value, sort_keys=False))
    except FileExistsError:
        pass
    return path
