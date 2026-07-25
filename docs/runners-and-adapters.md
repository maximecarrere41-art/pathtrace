# Runner et adaptateur

Pathtrace sépare deux responsabilités qui ne doivent pas être mélangées.

## `AgentRunner`

Le runner **lance un prompt** en mode non interactif.

```text
prompt → CodexRunner → codex exec
prompt → ClaudeCodeRunner → claude -p
```

Il connaît uniquement la manière de démarrer l’agent, son code retour, sa sortie standard et le délai d’exécution.

## `FrameworkAdapter`

L’adaptateur **installe la capture, observe et traduit les événements**.

```text
hooks Codex → CodexAdapter → trace Pathtrace v3
hooks Claude Code → ClaudeCodeAdapter → trace Pathtrace v3
```

Il connaît les propriétés natives du fournisseur, mais produit toujours le même format commun.

## Pourquoi les séparer ?

Le chemin manuel utilise seulement l’adaptateur :

```text
utilisateur lance l’agent → adaptateur capture → pathtrace test
```

Le chemin automatisé utilise les deux :

```text
pathtrace run → installation des hooks → runner → adaptateur → assertions
```

`pathtrace run` appelle automatiquement `adapter.install()` avant chaque scénario. L’utilisateur n’a donc aucune configuration de hooks à réaliser pour une campagne.

## Intégrations disponibles

| Framework | Runner | Adaptateur |
|---|---|---|
| `codex` | `CodexRunner` | `CodexAdapter` |
| `claude-code` | `ClaudeCodeRunner` | `ClaudeCodeAdapter` |

Le reste est partagé :

- format de trace ;
- moteur YAML ;
- rapports ;
- graphes ;
- campagnes.
