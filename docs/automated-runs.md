# Campagnes automatisées

Une campagne automatise la boucle complète :

```text
prompt → runner → agent → hooks → adaptateur → trace → assertions → rapport → graphe
```

## Format minimal

```yaml
version: 1
framework: codex

scenarios:
  - name: validation
    prompt: Lance les tests du projet.
    assertions:
      - type: must_include
        event: tool_call:Bash
        where:
          command: '*test*'
```

## Réutiliser un fichier d’assertions

Pour éviter de dupliquer les règles :

```yaml
version: 1
framework: codex

scenarios:
  - name: scénario A
    prompt: Corrige le bug A puis valide le projet.
    tests_file: assertions/validation.yaml

  - name: scénario B
    prompt: Corrige le bug B puis valide le projet.
    tests_file: assertions/validation.yaml
```

`tests_file` pointe vers le format manuel habituel :

```yaml
version: 1

tests:
  - name: validation commune
    assertions:
      - type: must_include
        event: tool_call:Bash
        where:
          command: '*test*'
```

Un scénario doit contenir exactement une source : `assertions` ou `tests_file`.

## Propriétés d’une suite

| Propriété | Rôle |
|---|---|
| `version` | Version du format de campagne. Actuellement `1`. |
| `framework` | Runner et adaptateur utilisés par défaut. |
| `defaults` | Valeurs partagées par les scénarios. |
| `scenarios` | Liste ordonnée des prompts à exécuter. |

## Propriétés d’un scénario

| Propriété | Obligatoire | Rôle |
|---|---:|---|
| `name` | oui | Nom lisible dans le terminal et les rapports. |
| `prompt` | oui | Prompt réellement envoyé à l’agent. |
| `assertions` | au choix | Assertions écrites directement dans le scénario. |
| `tests_file` | au choix | Fichier d’assertions réutilisable. |
| `framework` | non | Remplace le framework de la suite. |
| `project_dir` | non | Projet dans lequel l’agent est lancé. |
| `timeout` | non | Délai maximal du processus agent, en secondes. |
| `trace_timeout` | non | Délai d’attente de la trace après le processus. |
| `executable` | non | Chemin de l’exécutable de l’agent. |
| `runner_args` | non | Arguments supplémentaires transmis au runner. |

Les chemins relatifs sont résolus depuis le dossier du fichier de campagne.

## Priorité des valeurs

La priorité est :

```text
options CLI → scénario → defaults → suite → valeur Pathtrace
```

Exemple :

```bash
pathtrace run \
  --tests tests/scenarios/ \
  --framework codex \
  --project-dir . \
  --timeout 900 \
  --runner-arg=--skip-git-repo-check \
  --report \
  --graph
```

## Plusieurs fichiers YAML

`--tests` accepte :

- un fichier ;
- un dossier, parcouru récursivement ;
- un motif glob ;
- plusieurs options `--tests`.

```bash
pathtrace run \
  --tests tests/core/ \
  --tests 'tests/security/*.yaml' \
  --report
```

Chaque fichier découvert doit être une suite automatisée contenant `scenarios`.

## Échecs techniques et échecs métier

Pathtrace distingue :

- l’échec du processus agent : code retour non nul ou délai dépassé ;
- l’absence de trace : hooks non exécutés ou adaptateur mal configuré ;
- l’échec d’une assertion : chemin observé différent du chemin attendu.

Le rapport JSON et le graphe contiennent ces informations.

## Isolation des scénarios

Les scénarios sont exécutés séquentiellement dans leur `project_dir`. Pathtrace ne remet pas automatiquement Git à zéro, car cela pourrait détruire des changements utilisateur.

Pour des scénarios indépendants :

- utiliser un checkout propre par job CI ;
- utiliser plusieurs worktrees ;
- ou définir un `project_dir` différent par scénario.
