# Pathtrace

Pathtrace teste **le chemin suivi par un agent IA** : les skills chargées, les outils utilisés, les commandes exécutées et leur ordre.

Il complète les tests classiques : au lieu de vérifier uniquement la réponse finale, il vérifie aussi **comment l’agent y est arrivé**.

```text
prompt → agent → adaptateur → trace JSON → assertions YAML → rapport → graphe HTML
```

## Deux façons de l’utiliser

### 1. Observer puis tester une session manuelle

À choisir pour explorer un agent, comprendre une exécution réelle ou vérifier ponctuellement un tour déjà lancé par un humain.

```bash
python -m pip install -e .
pathtrace install --framework codex
codex
pathtrace test --latest --tests pathtrace.yaml --report --graph
```

Dans ce mode, **Pathtrace ne lance pas le prompt**. Il écoute les hooks de l’agent, écrit la trace, puis teste cette trace.

### 2. Lancer une campagne automatisée

À choisir pour la non-régression, la CI ou l’exécution de nombreux prompts et fichiers YAML.

```bash
pathtrace run --tests tests/scenarios/ --framework codex --report --graph
```

Dans ce mode, Pathtrace :

1. lance le prompt avec le runner de l’agent ;
2. récupère la trace produite par l’adaptateur ;
3. applique les assertions YAML ;
4. écrit les rapports et graphes ;
5. passe au scénario suivant.

## Exemple de trace lisible

```json
{
  "prompt": "Corrige le bug puis lance les tests",
  "framework": "codex",
  "summary": {
    "skills": ["conventions-code"],
    "commands": ["python -m pytest"],
    "tools": ["Read", "Bash"]
  },
  "events": [
    {
      "type": "skill",
      "name": "conventions-code",
      "tool": "Read",
      "path": ".agents/skills/conventions-code/SKILL.md",
      "status": "success"
    },
    {
      "type": "tool_call",
      "name": "Bash",
      "command": "python -m pytest",
      "status": "success"
    }
  ]
}
```

Le cœur ne connaît aucun nom de skill, commande ou outil. Chaque adaptateur traduit les événements natifs vers ce petit modèle commun.

## YAML manuel

```yaml
version: 1

tests:
  - name: le code est validé
    assertions:
      - type: must_include
        event: skill:conventions-code

      - type: must_include
        event: tool_call:Bash
        where:
          command: '*pytest*'
```

## YAML automatisé

```yaml
version: 1
framework: codex

defaults:
  project_dir: ..
  timeout: 600

scenarios:
  - name: correction suivie des tests
    prompt: |
      Corrige le bug décrit dans issue.md.
      Lance les tests avant de terminer.
    assertions:
      - type: must_include
        event: tool_call:Bash
        where:
          command: '*pytest*'

  - name: vérification de sécurité
    prompt: Analyse les changements et vérifie qu’aucune commande destructive n’est utilisée.
    tests_file: assertions/security.yaml
```

Un scénario utilise soit `assertions` directement, soit `tests_file` pour réutiliser un fichier YAML manuel.

## Architecture extensible

Deux abstractions sont volontairement séparées :

- `FrameworkAdapter` observe les événements natifs et produit une trace commune ;
- `AgentRunner` lance un prompt en mode non interactif.

Pour ajouter Claude Code demain, il suffira d’ajouter `ClaudeCodeAdapter` et `ClaudeCodeRunner`. Le moteur YAML, le rapport et le graphe ne changent pas.

## Documentation

- [Guide pas à pas et choix du mode](docs/quickstart.md)
- [Campagnes automatisées](docs/automated-runs.md)
- [Format JSON et propriétés abstraites](docs/trace-format.md)
- [Runner et adaptateur : rôles différents](docs/runners-and-adapters.md)
- [Capture et propriétés Codex](docs/codex-adapter.md)
- [Créer un adaptateur et un runner](docs/adapters.md)

## Développement

```bash
python -m pip install -e ".[dev]"
python -m pytest
```

## Licence

MIT — voir [LICENSE](LICENSE).
