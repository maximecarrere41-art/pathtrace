from pathlib import Path
from collections.abc import Iterable

import click

from pathtrace.adapters import available_adapters, get_adapter
from pathtrace.config import (
    Feature, InstallTarget, ProjectConfig, load_project_config,
    prepare_activation, write_project_config,
)
from pathtrace.security.config import parse_security_settings
from pathtrace.security.sources import read_provider_config, write_initial_provider_config, remove_provider_config
from pathtrace.security.initialization import choose_initial_security
from pathtrace.provider_paths import provider_security_path


def install_target(target: str, framework: str, scope: str,
                   presets: bool | None = None) -> None:
    _validate_install_options(target, scope, presets)
    if scope == "provider":
        _install_provider(framework, presets)
        return
    config = prepare_activation(Path.cwd(), InstallTarget(target), framework)
    features = config.features_for(framework)
    hooks = get_adapter(framework).install(Path.cwd(), features)
    path = write_project_config(Path.cwd(), config)
    click.echo(f"Pathtrace {framework} activé ({_names(features)}) : {hooks}")
    click.echo(f"Configuration locale : {path}")


def _validate_install_options(target: str, scope: str,
                              presets: bool | None) -> None:
    if scope == "provider" and target != "security":
        raise ValueError("La portée provider accepte uniquement install security")
    if scope != "provider" and presets is not None:
        raise ValueError("--presets/--no-presets nécessitent --scope provider")


def _install_provider(framework: str, presets: bool | None) -> None:
    initial = choose_initial_security(framework, presets)
    value = read_provider_config(framework)
    parse_security_settings(value.get("security") if value else initial)
    hooks = get_adapter(framework).install(Path.cwd(), frozenset({Feature.SECURITY}))
    path = write_initial_provider_config(framework, initial) if value is None else provider_security_path(framework)
    click.echo(f"Pathtrace {framework} Security fournisseur activé : {hooks}")
    click.echo(f"Configuration fournisseur : {path}")


def uninstall_target(framework: str, scope: str) -> None:
    if scope == "provider":
        path = remove_provider_config(framework)
    else:
        path = _disable_project(framework)
    click.echo(f"Pathtrace {framework} désactivé ({scope}) : {path}")
    click.echo("Configuration fournisseur supprimée." if scope == "provider" else "Configuration projet désactivée.")
    click.echo("Hooks partagés conservés ; les autres projets restent actifs.")


def purge_target(framework: str, yes: bool) -> None:
    click.echo(f"Purge globale {framework} : retrait des hooks Pathtrace et de la configuration Security fournisseur.")
    click.echo("Observe/Test et Security ne seront plus déclenchés par ces hooks dans aucun projet.")
    click.echo("Les dossiers .pathtrace des projets et les hooks utilisateur seront conservés.")
    if not yes:
        click.confirm("Confirmer cette suppression pour tous les projets de ce fournisseur ?", default=False, abort=True)
    hook_path = get_adapter(framework).uninstall(Path.cwd())
    config_path = remove_provider_config(framework)
    click.echo(f"Hooks Pathtrace retirés : {hook_path}")
    click.echo(f"Configuration Security fournisseur supprimée : {config_path}")


def _disable_project(framework: str) -> Path:
    current = load_project_config(Path.cwd())
    frameworks = _existing_frameworks(current)
    frameworks.pop(framework, None)
    features = frozenset(f for enabled in frameworks.values() for f in enabled)
    config = ProjectConfig(features, current.security, frameworks)
    return write_project_config(Path.cwd(), config)


def _existing_frameworks(config: ProjectConfig) -> dict[str, frozenset[Feature]]:
    if not config.explicit:
        return {}
    if config.frameworks is not None:
        return dict(config.frameworks)
    return {name: config.features for name in available_adapters()}


def _names(features: Iterable[Feature]) -> str:
    return ", ".join(sorted(feature.value for feature in features))
