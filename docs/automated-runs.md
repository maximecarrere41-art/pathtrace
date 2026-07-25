# Campagnes automatisées

Une campagne automatise la boucle complète :

```text
prompt → runner → agent → hooks → adaptateur → trace → assertions → rapport → graphe
```

## Installation automatique des hooks

### Codex CLI

Avant chaque scénario `codex`, `pathtrace run` installe ou complète les hooks Codex, puis lance le prompt avec `codex exec`. La configuration existante est conservée et les entrées Pathtrace ne sont pas dupliquées.

Il n’est donc pas nécessaire d’exécuter `pathtrace install --framework codex` avant une campagne automatisée.

### Claude Code

Avant chaque scénario `claude-code`, `pathtrace run` fusionne les hooks Claude Code dans `~/.claude/settings.json`, puis lance le prompt avec `claude -p`. La configuration existante est conservée et les entrées Pathtrace ne sont pas dupliquées.

Il ne faut donc ni exécuter `pathtrace install --framework claude-code` au préalable, ni modifier `settings.json` à la main.

## Format minimal

### Codex CLI

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

### Claude Code

```yaml
version: 1
framework: claude-code

scenarios:
  - name: validation
    prompt: Lance les tests du projet.
    assertions:
      - type: must_include
        event: tool_call:Bash
        where:
          command: '*test*'
```

Le reste du format de campagne est commun aux deux frameworks.

## Réutiliser un fichier d’assertions

Pour éviter de dupliquer les règles :

```yaml
version: 1
framework: codex

scenarios:
  - name: scénario A
    prompt: Corrige le bug A puis valide le projet.
    tests_file: assertions/validation.yaml

  - name: scénario B avec Claude Code
    framework: claude-code
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
| `framework` | Runner et adaptateur utilisés par défaut : `codex` ou `claude-code`. |
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

### Exemple Codex CLI

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

### Exemple Claude Code

```bash
pathtrace run \
  --tests tests/scenarios/ \
  --framework claude-code \
  --project-dir . \
  --timeout 900 \
  --runner-arg=--model \
  --runner-arg=sonnet \
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
