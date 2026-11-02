from pathlib import Path
from collections.abc import Iterable

import click

from pathtrace.adapters import available_adapters
from pathtrace.config import CONFIG_PATH, Feature, ProjectConfig, load_project_config
from pathtrace.provider_paths import provider_security_path
from pathtrace.security.config import SecuritySettings, parse_security_settings
from pathtrace.security.sources import SecuritySource, security_sources


def show_status() -> None:
    config = load_project_config(Path.cwd())
    click.echo(f"Features: {_names(config.features)}")
    click.echo(f"Configuration: {Path.cwd() / CONFIG_PATH if config.explicit else 'legacy defaults'}")
    for framework in available_adapters():
        _show_framework(framework, config)


def _show_framework(framework: str, config: ProjectConfig) -> None:
    sources = security_sources(framework, config)
    features = config.features_for(framework)
    if not config.explicit and provider_security_path(framework).is_file():
        features = frozenset()
    features = features | ({Feature.SECURITY} if sources else set())
    click.echo(f"Framework {framework}: {_names(features)}")
    _show_sources(framework, sources)


def _show_sources(framework: str, sources: list[SecuritySource]) -> None:
    click.echo(f"Security provider configuration: {provider_security_path(framework)}")
    click.echo(f"Security project configuration: {Path.cwd() / CONFIG_PATH}")
    for scope in ("provider", "project"):
        if not any(source.scope == scope for source in sources):
            click.echo(f"Security {scope}: inactive")
    for source in sources:
        settings = parse_security_settings(source.raw)
        click.echo(f"Security {source.scope}: {len(settings.rules)} rules ({settings.mode.value})")
        _show_settings(settings)


def _show_settings(settings: SecuritySettings) -> None:
    click.echo(f"Security mode: {settings.mode.value}")
    for rule in settings.rules:
        click.echo(f"  {rule.identifier}: {rule.decision.value}")
    telemetry = settings.telemetry
    state = "enabled" if telemetry.enabled else "disabled"
    if telemetry.enabled and not telemetry.otlp_endpoint:
        state = "enabled (inactive: missing OTLP endpoint)"
    click.echo(f"Security telemetry: {state}")


def _names(features: Iterable[Feature]) -> str:
    return ", ".join(sorted(feature.value for feature in features)) or "none"
