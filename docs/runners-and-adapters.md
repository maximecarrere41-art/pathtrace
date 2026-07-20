# Runner et adaptateur

Pathtrace sépare deux responsabilités qui ne doivent pas être mélangées.

## `AgentRunner`

Le runner **lance un prompt**.

```text
prompt → CodexRunner → codex exec
```

Il connaît uniquement la manière de démarrer l’agent, son code retour, sa sortie standard et le délai d’exécution.

## `FrameworkAdapter`

L’adaptateur **observe et traduit les événements**.

```text
hooks Codex → CodexAdapter → trace Pathtrace v3
```

Il connaît les propriétés natives du fournisseur, mais produit toujours le même format commun.

## Pourquoi les séparer ?

Le chemin manuel utilise seulement l’adaptateur :

```text
utilisateur lance Codex → adaptateur capture → pathtrace test
```

Le chemin automatisé utilise les deux :

```text
pathtrace run → runner lance Codex → adaptateur capture → assertions
```

Cette séparation permet aussi de remplacer le mode d’exécution sans changer la capture, ou inversement.

## Ajouter Claude Code

Une intégration complète ajouterait :

```text
ClaudeCodeRunner
ClaudeCodeAdapter
```

Le reste reste partagé :

- format de trace ;
- moteur YAML ;
- rapports ;
- graphes ;
- campagnes.
