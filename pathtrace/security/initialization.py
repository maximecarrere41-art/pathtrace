import click
from typing import Any

from pathtrace.security.presets import PRESET_RULES, initial_security
from pathtrace.security.sources import read_provider_config


def choose_initial_security(framework: str, presets: bool | None) -> dict[str, Any] | None:
    if read_provider_config(framework) is not None:
        click.echo("Configuration fournisseur existante conservée.")
        return None
    click.echo(f"Initialisation Security {framework} : les règles seront immédiatement appliquées.")
    if presets is None:
        presets = _confirm_presets()
    return initial_security(presets)


def _confirm_presets() -> bool:
    click.echo("Presets proposés (patterns limités, voir docs/security.md) :")
    for rule in PRESET_RULES:
        click.echo(f"  {rule['id']}: {rule['decision']} — {rule['reason']}")
    return click.confirm("Installer ces presets modifiables ?", default=False)
