# Format de trace commun

Le format v3 est indépendant de Codex, Claude Code ou d'un framework applicatif. Un adaptateur doit seulement produire ce JSON.

## Propriétés de la trace

| Propriété | Obligatoire | Rôle |
|---|---:|---|
| `version` | oui | Version du format Pathtrace. Actuellement `3`. |
| `id` | oui | Identifiant global de la trace. |
| `session_id` | oui | Conversation ou session native de l'agent. |
| `turn_id` | oui | Tour ou prompt précis dans la session. |
| `prompt` | oui | Instruction de l'utilisateur pour ce tour. |
| `model` | oui | Modèle déclaré par l'agent, ou `unknown`. |
| `framework` | oui | Nom de l'adaptateur : `codex`, demain `claude-code`, etc. |
| `status` | oui | Statut global : généralement `success` ou `failure`. |
| `started_at` | non | Début du tour au format ISO 8601. |
| `ended_at` | non | Fin du tour au format ISO 8601. |
| `summary` | oui | Vue directe des skills, commandes et outils utilisés. |
| `events` | oui | Chemin ordonné réellement testé. |

## `summary`

Cette partie est calculée automatiquement à partir des événements.

```json
{
  "skills": ["pdfs", "conventions-code"],
  "commands": ["python -m pytest", "git diff"],
  "tools": ["Read", "Bash"]
}
```

Elle sert à comprendre rapidement une trace. Le moteur de test utilise `events`, qui conserve l'ordre.

## Propriétés d'un événement

Le modèle n'impose que deux types :

- `tool_call` : appel d'un outil, d'une commande, d'une API ou d'une action native ;
- `skill` : chargement ou utilisation identifiable d'une skill.

| Propriété | Obligatoire | Rôle |
|---|---:|---|
| `index` | oui | Position dans le chemin, à partir de `0`. |
| `type` | oui | `tool_call` ou `skill`. |
| `name` | oui | Nom réel de l'outil, ou nom de la skill. |
| `tool` | non | Outil natif ayant chargé la skill, par exemple `Read`. |
| `command` | non | Commande réellement exécutée, sans la renommer. |
| `path` | non | Fichier ou ressource principale ciblée. |
| `input` | non | Arguments natifs utiles de l'appel. |
| `output_summary` | non | Résumé limité de la réponse de l'outil. |
| `status` | non | `running`, `success`, `failure` ou `unknown`. |
| `raw` | non | Métadonnées techniques du fournisseur, isolées du modèle commun. |

## Pourquoi `raw` reste séparé

`raw` permet de diagnostiquer un adaptateur sans rendre le schéma principal complexe.

Exemple Codex :

```json
{
  "raw": {
    "hook": "post-tool-use",
    "call_id": "call_42"
  }
}
```

Un futur adaptateur Claude peut utiliser d'autres clés dans `raw`. Les tests portables ne doivent pas dépendre de cette partie, sauf besoin très spécifique.

## Compatibilité v2

Le loader accepte encore les anciennes traces dont les événements se trouvent dans `tools`. Elles sont normalisées en mémoire vers `events`. Les nouvelles captures sont toujours écrites en v3.
