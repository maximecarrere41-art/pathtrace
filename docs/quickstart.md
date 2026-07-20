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

Les deux chemins produisent la même trace v3 et utilisent le même moteur d’assertions.

# Chemin 1 — observation manuelle

## 1. Installer les hooks

```bash
pathtrace install --framework codex
```

La commande fusionne les hooks dans `.codex/hooks.json` sans supprimer la configuration existante.

## 2. Utiliser Codex normalement

```bash
codex
```

Pathtrace ne lance pas le prompt dans ce chemin. Les hooks produisent une trace par tour :

```text
.pathtrace/traces/codex/<session_id>/<turn_id>.json
```

## 3. Déclarer le chemin attendu

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

Ou avec une trace précise :

```bash
pathtrace test \
  --trace .pathtrace/traces/codex/session-1/turn-2.json \
  --tests pathtrace.yaml \
  --report \
  --graph
```

# Chemin 2 — campagne automatisée

## 1. Écrire une suite de scénarios

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

Le runner lance chaque prompt séquentiellement. L’adaptateur capture ensuite le chemin réellement suivi.

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
