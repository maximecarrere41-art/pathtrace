# Runtime Security et audit des décisions

Pathtrace distingue des pipelines qui peuvent fonctionner indépendamment :

```text
Observe / Test                  Control / Audit
Agent                           Agent
  ↓                               ↓
hooks de capture                PreToolUse
  ↓                               ↓
traces Pathtrace                Policy Engine
                                  ↓
                       ALLOW / BLOCK / REQUIRE_APPROVAL
                                  ↓
                       enforcement fournisseur + audit OTLP
```

La télémétrie de ce guide concerne uniquement les décisions du Policy Engine.
Elle ne convertit pas les traces, campagnes, assertions ou graphes historiques
en données OpenTelemetry.

## Installation explicite

L'installation du package Python ne modifie aucun repository. L'activation se
fait explicitement depuis le projet à protéger :

```bash
pathtrace install observe --framework codex
pathtrace install security --framework codex
pathtrace install all --framework codex
```

Les mêmes intentions existent avec `--framework claude-code`.
`pathtrace install --framework <framework>` reste compatible et équivaut à
`observe`.

Les installations sont additives. Installer Observe puis Security, ou
Security puis Observe, active les deux capacités sans remplacer les hooks
existants. Une répétition de la même commande ne duplique pas les hooks.

Security-only crée uniquement :

```text
.pathtrace/config.yaml
```

Il ne crée ni état de capture, ni trace, ni campagne, ni rapport, ni graphe.
Les hooks du fournisseur sont fusionnés avec les entrées utilisateur
existantes. Le hook global Security-only est un no-op dans les autres
repositories tant qu'ils n'ont pas leur propre configuration explicite.
`pathtrace status` affiche l'activation locale.

## Configuration

Exemple de `.pathtrace/config.yaml` :

```yaml
version: 1
features:
  - security

security:
  mode: enforce
  rules:
    - id: block-force-push
      action: git
      decision: block
      match:
        command: "git push --force*"
      reason: Force push interdit
      risk_level: high

    - id: approve-push
      action: git
      decision: require_approval
      match:
        command: "git push *"
      reason: Un push doit être validé

    - id: protect-ssh
      action: filesystem
      decision: block
      match:
        resource: "~/.ssh/**"
      reason: Accès aux clés SSH interdit
      risk_level: critical

    - id: approve-github-writes
      action: mcp
      decision: require_approval
      match:
        mcp_server: github
        tool: "*create*"
      reason: Écriture GitHub soumise à validation

  telemetry:
    enabled: false
```

Actions supportées : `shell`, `git`, `filesystem`, `mcp`, `network` et `tool`.
Une action réseau n'est identifiable que si le hook expose une URL avant
exécution. Les champs de matching sont `command`, `resource`, `tool` et
`mcp_server`. Le matching utilise des patterns shell et ne fait aucun appel
LLM.

Une règle exige un identifiant unique, une action, une décision, au moins un
pattern et une raison. Lorsque plusieurs règles correspondent :

```text
BLOCK > REQUIRE_APPROVAL > ALLOW
```

À priorité égale, l'identifiant lexicalement le plus petit gagne. L'ordre du
YAML ne modifie donc pas la décision. Sans règle correspondante, la décision
est `ALLOW` : l'activation de Security ne bloque rien par défaut.

## Enforce et audit-only

En mode `enforce`, la décision est traduite vers la réponse native du hook.
En mode `audit_only`, les règles sont évaluées et l'événement conserve par
exemple `decision: BLOCK`, mais aucune réponse de blocage n'est envoyée au
fournisseur.

```yaml
security:
  mode: audit_only
```

## Capacités des fournisseurs

| Décision | Claude Code | Codex |
|---|---|---|
| `ALLOW` | conserve le flux de permissions natif | conserve le flux de permissions natif |
| `BLOCK` | `PreToolUse` retourne `deny` | `PreToolUse` retourne `deny` |
| `REQUIRE_APPROVAL` | `PreToolUse` retourne `ask` | `ask` non supporté : blocage explicite en enforce |

Pathtrace ne remplace ni la sandbox, ni les permissions natives, ni
l'isolation du système. Une règle ne contrôle que les informations réellement
présentes dans le payload `PreToolUse`.

## Security Telemetry via OTLP

Installer les dépendances optionnelles :

```bash
python -m pip install "pathtrace[security]"
```

Puis activer l'export OTLP/HTTP :

```yaml
security:
  mode: enforce
  rules: []
  telemetry:
    enabled: true
    otlp_endpoint: http://localhost:4318
```

L'endpoint `/v1/logs` est ajouté lorsqu'il n'est pas déjà présent. Pathtrace
émet un log `pathtrace.security.decision` par décision et aucun span pour les
traces Observe/Test.

Les attributs stables couvrent framework, session, tour, type d'action, outil,
serveur MCP, commande, ressource, décision, mode, policy, règle, raison, risque,
validation, résultat d'enforcement et timestamp.

Les valeurs ressemblant à des mots de passe, secrets, API keys, tokens,
en-têtes Authorization ou Bearer tokens sont remplacées par `[REDACTED]`. Cette
sanitization réduit les fuites courantes sans prétendre être un DLP complet.

L'audit est fail-open : dépendance OpenTelemetry absente, endpoint manquant,
collecteur indisponible ou erreur d'export n'altèrent jamais la décision ni son
enforcement. Security continue de fonctionner sans télémétrie.
