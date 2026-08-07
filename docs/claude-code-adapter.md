# Intégration Claude Code

L’intégration contient :

- `ClaudeCodeAdapter`, qui transforme les hooks natifs en trace Pathtrace v3 ;
- `ClaudeCodeRunner`, qui lance Claude Code en mode non interactif.

## Campagne automatisée : aucun réglage manuel

Une suite utilise simplement le framework `claude-code` :

```yaml
version: 1
framework: claude-code

defaults:
  project_dir: ..
  timeout: 600

scenarios:
  - name: validation
    prompt: Lance les tests du projet.
    assertions:
      - type: must_include
        event: tool_call:Bash
        where:
          command: '*test*'
```

Puis :

```bash
pathtrace run --tests tests/scenarios.yaml --report --graph
```

Avant chaque scénario, Pathtrace fusionne automatiquement ses hooks dans `~/.claude/settings.json`. La configuration existante est conservée et les entrées Pathtrace ne sont pas dupliquées.

Il ne faut donc pas :

- créer les hooks à la main ;
- modifier `settings.json` ;
- lancer `pathtrace install` avant `pathtrace run`.

Si `CLAUDE_CONFIG_DIR` est défini, Pathtrace utilise ce répertoire à la place de `~/.claude`.

## Observation d’une session manuelle

Pour une session Claude lancée directement par l’utilisateur, une installation préalable reste nécessaire :

```bash
pathtrace install --framework claude-code
claude
pathtrace test --latest --tests pathtrace.yaml --report --graph
```

## Hooks capturés

| Hook Claude Code | Utilité Pathtrace |
|---|---|
| `SessionStart` | Mémorise le modèle lorsqu’il est fourni. |
| `SessionEnd` | Nettoie l’état de session temporaire. |
| `UserPromptSubmit` | Démarre un tour et mémorise le prompt. |
| `PreToolUse` | Enregistre le début d’un appel d’outil. |
| `PostToolUse` | Termine un appel réussi. |
| `PostToolUseFailure` | Termine un appel en échec. |
| `Stop` | Finalise une trace réussie. |
| `StopFailure` | Finalise une trace en échec. |

En activation `security`, seul `PreToolUse` est installé. Claude Code sait
traduire les trois décisions communes avec `allow`, `deny` et `ask`. Pathtrace
utilise donc `ask` pour `REQUIRE_APPROVAL`, sans construire de workflow
interactif parallèle.

Voir [Runtime Security et audit des décisions](security.md).

`tool_use_id` corrèle les événements avant/après afin qu’un appel ne soit présent qu’une fois dans la trace.

## Propriétés traduites

| Propriété Claude Code | Propriété Pathtrace |
|---|---|
| `session_id` | `trace.session_id` |
| `prompt` | `trace.prompt` |
| `model` | `trace.model` lorsqu’il est disponible |
| `tool_name` | `event.name` |
| `tool_input` | `event.input`, `event.command` et `event.path` |
| `tool_response` | `event.status` et `event.output_summary` |
| `error` | statut et résumé d’un appel en échec |
| `tool_use_id` | corrélation conservée dans `event.raw` |
| `duration_ms` | `event.raw.duration_ms` |

Claude Code n’expose pas d’identifiant de tour dans ses hooks. Pathtrace en génère donc un à chaque `UserPromptSubmit`.

## Runner

Le runner utilise :

```text
claude -p --output-format json <prompt>
```

Les arguments déclarés dans `runner_args` sont transmis à Claude Code. Exemple :

```yaml
defaults:
  runner_args:
    - --model
    - sonnet
    - --permission-mode
    - acceptEdits
```

L’exécutable est résolu dans cet ordre :

```text
scenario.executable / defaults.executable
        ↓
PATHTRACE_CLAUDE_CODE_EXECUTABLE
        ↓
claude trouvé dans PATH
```

La sortie JSON de Claude fournit le `session_id`, utilisé avec le prompt pour sélectionner la bonne trace lorsqu’une campagne produit plusieurs fichiers.

## Fichiers générés

```text
.pathtrace/.state/claude-code/<session_id>/current.json
.pathtrace/traces/claude-code/<session_id>/<turn_id>.json
```

L’état `current.json` est supprimé après finalisation.

## Diagnostic

### Aucune trace créée

Vérifiez :

- que `pathtrace` est disponible dans le `PATH` du processus Claude ;
- que les hooks ne sont pas désactivés avec `disableAllHooks` ;
- que `runner_args` ne contient pas `--bare`, car ce mode désactive les hooks ;
- qu’une politique gérée n’interdit pas les hooks utilisateur ;
- que Claude Code est authentifié et fonctionne seul avec `claude -p "hello" --output-format json`.

### Exécutable introuvable

Définissez `executable` dans la suite ou la variable `PATHTRACE_CLAUDE_CODE_EXECUTABLE`.
