# Ajouter un nouvel agent

Une intégration complète contient généralement deux petites classes indépendantes. Codex et Claude Code peuvent servir de références concrètes.

## 1. Ajouter l’adaptateur

L’adaptateur installe la capture native et traduit les événements vers la trace commune.

```python
from pathlib import Path
from typing import Any

from pathtrace.adapters.base import FrameworkAdapter


class FutureAgentAdapter(FrameworkAdapter):
    name = "future-agent"

    def install(self, project_dir: Path) -> Path:
        ...

    def uninstall(self, project_dir: Path) -> Path:
        ...

    def handle(
        self,
        event_slug: str,
        payload: dict[str, Any],
        project_dir: Path,
    ) -> Path | None:
        ...
```

L’ajouter au registre `pathtrace/adapters/__init__.py` rend disponible :

```bash
pathtrace install --framework future-agent
pathtrace uninstall --framework future-agent
```

`uninstall` doit retirer uniquement les hooks appartenant à Pathtrace et
conserver toute configuration utilisateur du fournisseur.

## 2. Ajouter le runner

Le runner lance l’agent en mode non interactif.

```python
from pathtrace.runners.base import AgentRunner, RunRequest, RunResult


class FutureAgentRunner(AgentRunner):
    name = "future-agent"

    def run(self, request: RunRequest) -> RunResult:
        ...
```

L’ajouter au registre `pathtrace/runners/__init__.py` rend disponible :

```bash
pathtrace run --framework future-agent --tests tests/scenarios/
```

## Règles de traduction

L’adaptateur doit rester simple :

- conserver le vrai nom de l’outil dans `name` ;
- conserver la vraie commande dans `command` ;
- ne pas coder de liste de commandes, outils ou skills ;
- utiliser `skill` uniquement lorsqu’une skill est réellement identifiable ;
- utiliser `tool_call` dans tous les autres cas ;
- placer les détails fournisseur dans `raw` ;
- produire une trace par tour lorsque l’agent expose cette notion.

## Ce qui est partagé automatiquement

Une fois le runner et l’adaptateur enregistrés, le nouvel agent bénéficie de :

- `pathtrace test` ;
- `pathtrace run` ;
- toutes les assertions YAML ;
- rapports JSON ;
- graphes HTML ;
- exécution en CI.

## Tests minimaux

### Adaptateur

1. installation non destructive et idempotente ;
2. capture du prompt ;
3. corrélation début/fin d’un appel ;
4. extraction d’une commande ;
5. extraction dynamique d’une skill ;
6. séparation session/tour ;
7. nettoyage de l’état temporaire.

### Runner

1. construction correcte de la commande ;
2. respect du projet de travail ;
3. gestion du timeout ;
4. gestion de l’exécutable absent ;
5. récupération de la nouvelle trace ;
6. signalement clair si aucune trace n’est créée.
