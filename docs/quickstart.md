# Guide pas à pas

## Installation

```bash
python -m pip install -e .
```

Pour contribuer :

```bash
python -m pip install -e ".[dev]"
python -m pytest
```

## Quel chemin choisir ?

| Besoin | Commande | Intérêt |
|---|---|---|
| Observer une session lancée manuellement | `pathtrace test` | Idéal pour explorer, déboguer et comprendre un tour réel. |
| Lancer plusieurs prompts automatiquement | `pathtrace run` | Idéal pour la non-régression, la CI et les campagnes en volume. |

Les deux chemins produisent la même trace v3 et utilisent le même moteur d’assertions, avec Codex CLI comme avec Claude Code.

# Chemin 1 — observation manuelle

## 1. Installer les hooks

### Codex CLI

```bash
pathtrace install --framework codex
```

La commande fusionne les hooks dans le répertoire global Codex, généralement `~/.codex/hooks.json`, sans supprimer la configuration existante.

### Claude Code

```bash
pathtrace install --framework claude-code
```

La commande fusionne les hooks dans `~/.claude/settings.json` sans supprimer les hooks déjà présents. Si `CLAUDE_CONFIG_DIR` est défini, ce répertoire est utilisé à la place de `~/.claude`.

### Désinstaller les hooks

```bash
pathtrace uninstall --framework codex
pathtrace uninstall --framework claude-code
```

Ces commandes retirent les hooks Pathtrace globaux de la machine : Codex dans
`~/.codex/hooks.json` (ou `CODEX_HOME`) et Claude Code dans
`~/.claude/settings.json` (ou `CLAUDE_CONFIG_DIR`). Elles affectent donc tous
les projets locaux qui utilisent Pathtrace avec le framework désinstallé.
Seuls les hooks gérés par Pathtrace, y compris leurs variantes internes, sont
retirés ; les hooks et réglages utilisateur sont conservés. La commande peut
être relancée sans erreur si les hooks sont déjà absents ou partiellement
retirés.

Seule la configuration `.pathtrace/config.yaml` du projet courant est mise à
jour pour oublier le framework choisi. Si plusieurs frameworks sont activés,
les autres restent configurés et `features` est recalculé comme leur union.
Après la désinstallation du dernier framework, seul `config.yaml` est
supprimé : les traces, rapports, graphes et campagnes historiques ne sont
jamais supprimés automatiquement.

## 2. Utiliser l’agent normalement

### Codex CLI

```bash
codex
```

### Claude Code

```bash
claude
```

Pathtrace ne lance pas le prompt dans ce chemin. Les hooks produisent une trace par tour :

```text
.pathtrace/traces/<framework>/<session_id>/<turn_id>.json
```

## 3. Déclarer le chemin attendu

Le même fichier d’assertions peut être utilisé avec les deux agents :

```yaml
version: 1

tests:
  - name: correction suivie d’une validation
    assertions:
      - type: path_matches
        sequence:
          - event: skill:conventions-code
          - event: tool_call:Bash
            where:
              command: '*pytest*'
```

## 4. Tester la trace

```bash
pathtrace test --latest --tests pathtrace.yaml --report --graph
```

Avec une trace Codex précise :

```bash
pathtrace test \
  --trace .pathtrace/traces/codex/session-1/turn-2.json \
  --tests pathtrace.yaml \
  --report \
  --graph
```

Avec une trace Claude Code précise :

```bash
pathtrace test \
  --trace .pathtrace/traces/claude-code/session-1/turn-2.json \
  --tests pathtrace.yaml \
  --report \
  --graph
```

# Chemin 2 — campagne automatisée

## 1. Écrire une suite de scénarios

### Codex CLI

```yaml
version: 1
framework: codex

defaults:
  project_dir: ..
  timeout: 600
  trace_timeout: 10

scenarios:
  - name: lancer les tests
    prompt: Corrige le problème puis lance les tests.
    assertions:
      - type: must_include
        event: tool_call:Bash
        where:
          command: '*pytest*'
```

### Claude Code

```yaml
version: 1
framework: claude-code

defaults:
  project_dir: ..
  timeout: 600
  trace_timeout: 10

scenarios:
  - name: lancer les tests
    prompt: Corrige le problème puis lance les tests.
    assertions:
      - type: must_include
        event: tool_call:Bash
        where:
          command: '*pytest*'
```

## 2. Lancer la campagne

```bash
pathtrace run --tests tests/scenarios.yaml --report --graph
```

Un dossier entier :

```bash
pathtrace run --tests tests/scenarios/ --report --graph
```

Un motif :

```bash
pathtrace run --tests 'tests/**/*.scenario.yaml' --report --graph
```

### Avec Codex CLI

`pathtrace run` installe ou complète automatiquement les hooks Codex avant chaque scénario, puis lance le prompt avec `codex exec`. Il n’est pas nécessaire d’exécuter `pathtrace install` au préalable.

### Avec Claude Code

`pathtrace run` fusionne automatiquement les hooks Claude Code dans `~/.claude/settings.json`, puis lance le prompt avec `claude -p`. Il n’est pas nécessaire d’exécuter `pathtrace install` ni de modifier `settings.json` à la main.

## 3. Lire les sorties

```text
.pathtrace/traces/<framework>/<session>/<turn>.json
.pathtrace/reports/<suite>__<scenario>__<session>__<turn>.json
.pathtrace/graphs/<suite>__<scenario>__<session>__<turn>.html
.pathtrace/campaigns/<suite>.json
```

Le code retour vaut `0` si tout passe et `1` si un scénario échoue. `--fail-fast` arrête la campagne au premier échec.

## Assertions disponibles

| Type | Utilité |
|---|---|
| `must_include` | Au moins un événement doit correspondre. |
| `must_not_include` | Aucun événement ne doit correspondre. |
| `path_matches` | Une suite d’événements doit apparaître dans cet ordre. |
| `no_direct_transition` | Deux événements ne doivent pas être voisins. |
| `min_occurrences` | Nombre minimal d’occurrences. |
| `max_occurrences` | Nombre maximal d’occurrences. |
| `status_equals` | Tous les événements ayant un statut doivent avoir la valeur attendue. |

Les échecs sont reliés aux index des événements concernés. Le graphe les met en évidence.
