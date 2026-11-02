from copy import deepcopy
from typing import Any


PRESET_RULES = (
    dict(id="preset-recursive-delete", action="shell", decision="BLOCK",
         match={"command": ["*rm -rf *", "*rm -fr *", "*rm -r -f *", "*rm -f -r *",
                            "*rm --recursive --force *", "*rm --force --recursive *"]},
         reason="Suppression récursive forcée interdite"),
    dict(id="preset-force-push", action="git", decision="BLOCK",
         match={"command": ["*git push --force*", "*git push * --force*",
                            "*git push -f", "*git push -f *", "*git push * -f", "*git push * -f *"]},
         reason="Force push interdit"),
    dict(id="preset-hard-reset", action="git", decision="REQUIRE_APPROVAL",
         match={"command": ["*git reset --hard*", "*git reset * --hard*"]},
         reason="Valider la perte des modifications locales"),
    dict(id="preset-git-clean", action="git", decision="REQUIRE_APPROVAL",
         match={"command": ["*git clean -fd*", "*git clean -df*",
                            "*git clean -f -d*", "*git clean -d -f*"]},
         reason="Valider la suppression des fichiers non suivis"),
    dict(id="preset-git-push", action="git", decision="REQUIRE_APPROVAL",
         match={"command": ["git push", "*git push *"]},
         reason="Valider la publication Git"),
    dict(id="preset-ssh-keys", action="filesystem", decision="BLOCK",
         match={"resource": ["~/.ssh", "~/.ssh/**"]},
         reason="Accès au répertoire SSH interdit, y compris ses clés privées"),
)


def initial_security(use_presets: bool) -> dict[str, Any]:
    rules = deepcopy(list(PRESET_RULES)) if use_presets else []
    return dict(mode="enforce", rules=rules, telemetry={"enabled": False})
