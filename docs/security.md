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
`pathtrace status` affiche les fonctionnalités par fournisseur et les deux portées.

## Deux portées indépendantes

`--scope project` est la valeur par défaut et conserve les commandes d'installation
existantes. `--scope provider` accepte uniquement `install security` : Observe
et les campagnes gardent leur fonctionnement par projet.

```bash
pathtrace install security --framework codex --scope provider
pathtrace install security --framework claude-code --scope provider
pathtrace install security --framework codex --scope project
pathtrace install security --framework claude-code --scope project
pathtrace status
```

| Portée | Fichier | Projets concernés |
|---|---|---|
| Fournisseur Codex | `$CODEX_HOME/pathtrace/security.yaml`, sinon `~/.codex/pathtrace/security.yaml` | Tous les projets Codex |
| Fournisseur Claude Code | `$CLAUDE_CONFIG_DIR/pathtrace/security.yaml`, sinon `~/.claude/pathtrace/security.yaml` | Tous les projets Claude Code |
| Projet | `.pathtrace/config.yaml` | Projet courant et fournisseurs activés dans `frameworks` |

Il n'existe aucune configuration commune aux deux fournisseurs. Chaque fournisseur
lit uniquement son fichier. Sans fichier projet, la protection fournisseur reste
active ; elle ne crée aucun artefact Observe. Une ancienne configuration projet
sans `frameworks` conserve son application historique aux deux fournisseurs.

Exemple de fichier fournisseur, valable séparément pour Codex et Claude Code :

```yaml
version: 1
enabled: true
security:
  mode: enforce
  rules:
    - id: block-force-push
      action: git
      decision: BLOCK
      match:
        command: "git push --force*"
      reason: Force push interdit dans les projets de ce fournisseur
  telemetry:
    enabled: false
```

L'initialisation fournisseur propose les presets décrits ci-dessous. Refuser les
presets initialise des règles vides. Un fichier fournisseur existant est conservé, y compris ses règles
et réglages OTLP. Une répétition ne duplique pas les hooks.

Les deux portées sont évaluées séparément et leurs règles sont toujours appliquées.
`BLOCK > REQUIRE_APPROVAL > ALLOW` détermine la réponse native unique.
Une règle projet ne peut jamais affaiblir un blocage fournisseur.
L'ancien champ YAML `mode` est ignoré, sans réécrire le fichier utilisateur.

Les identifiants doivent être uniques **dans chaque portée**. Le même identifiant
peut exister aux deux niveaux : les règles restent distinctes, sans remplacement.
À priorité égale entre portées, le fournisseur fournit la raison de la décision.
Dans chaque portée, le plus petit identifiant lexical gagne.

Chaque portée peut exporter son audit vers son propre collecteur. L'attribut
`pathtrace.security.policy` vaut `pathtrace.security.provider` ou
`pathtrace.security.project` et identifie la provenance sans changer les champs
du contrat OTLP. Une décision est publiée par portée active. Le résultat
d'application reflète la réponse combinée, même si une règle autorisait l'action.

Une politique invalide, un fichier fournisseur illisible ou une enveloppe invalide
bloque les actions par précaution. Les événements Observe autres que `PreToolUse`
restent capturés si Observe est activé dans le projet.

## Presets fournisseur

Le catalogue est séparé du moteur d'évaluation. Lors de la première installation
fournisseur, la CLI présente les six intentions suivantes et demande confirmation
avant d'écrire les fichiers ou les hooks. La réponse proposée par défaut est non.
Sans saisie, l'installation est abandonnée sans changement. En automatisation,
`--presets` exprime le choix d'installer le catalogue, `--no-presets` le refus.

```bash
pathtrace install security --framework codex --scope provider --presets
pathtrace install security --framework claude-code --scope provider --presets
```

Les presets acceptés sont immédiatement actifs et appliqués. Refuser le catalogue
initialise des règles vides. Les nouvelles configurations projet ne reçoivent
aucun preset et appliquent les règles qui y sont définies.

| Intention | Décision | Couverture des presets |
|---|---|---|
| Suppression récursive forcée | `BLOCK` | `rm -rf`, `-fr`, `-r -f`, `-f -r`, `--recursive --force` et ordre inverse, suivis d'un argument |
| Force push | `BLOCK` | `git push --force*`, option après la destination, `-f` avant/après les arguments ; inclut `--force-with-lease` |
| Reset dur | `REQUIRE_APPROVAL` | `git reset --hard*`, y compris après une révision |
| Nettoyage Git | `REQUIRE_APPROVAL` | `git clean -fd*`, `-df*`, `-f -d*`, `-d -f*` |
| Publication Git | `REQUIRE_APPROVAL` | `git push` seul ou suivi d'arguments |
| Clés SSH | `BLOCK` | Tout accès fichier explicite à `~/.ssh` et ses descendants, afin de couvrir les noms de clés personnalisés |

Le blocage SSH couvre aussi les clés publiques, `config` et `known_hosts`.
Le fichier YAML expose les patterns exacts : l'utilisateur peut les modifier,
supprimer une règle ou vider entièrement la liste. Une réinstallation conserve
ces modifications sans reproposer ni réappliquer les presets.
Même `--presets` ne remplace pas un fichier existant. La désinstallation fournisseur
supprime en revanche ce fichier ; une installation ultérieure propose une nouvelle
initialisation et ne restaure pas les règles supprimées.

### Variantes vérifiées et limites

Les tests passent les commandes dans les hooks des deux adaptateurs, sans les
exécuter. Les payloads testés comprennent `Bash`, `shell_command`, `exec_command`
et `PowerShell`, avec les champs `command`, `cmd` ou `script`.
Ils vérifient notamment `echo ok && rm -rf build`,
`git status && git push --force origin main`, `git push origin main --force`,
`git --no-pager push --force origin main` et `git reset HEAD --hard`.
Pour les demandes de validation appliquées, Claude retourne `ask` et Codex `deny`.

Les patterns utilisent des jokers de texte, pas un interpréteur de shell.
La commande complète et ses segments sont évalués. Les séparateurs pris en charge
sont `&&`, `||`, `;`, `|`, `|&`, `&` et les retours à la ligne. Les séparateurs
entre guillemets et les échappements simples sont conservés ; `2>&1` n'est pas
traité comme une commande supplémentaire. Ainsi `rm -rf build && git status`
et `git status && rm -rf build` déclenchent aussi une règle shell `rm -rf *`.
La décision la plus restrictive gagne, quel que soit l'ordre des segments.
En cas d'égalité, l'identifiant lexical départage les règles ; l'audit décrit
le segment retenu, ou la commande complète si seule celle-ci correspond.
Cas vérifiés non couverts :

- `rm -r --force build` n'est pas l'une des variantes initiales du catalogue ;
- `cat ~/.ssh/id_ed25519` est une action shell, sans ressource fichier explicite,
  et ne correspond donc pas à la règle SSH ;
- les alias, scripts, interpréteurs imbriqués, substitutions, encodages et
  suppressions PowerShell ne sont pas interprétés par ces presets ;
- les jokers peuvent produire des faux positifs : `echo 'rm -rf build'` est bloqué
  même si cette commande affiche seulement du texte.

Les presets ne garantissent pas la détection de toutes les variantes ni de tous
les accès aux secrets. Pathtrace n'est ni un antivirus ni une sandbox. Il ne
contrôle que les informations exposées par les hooks et ne remplace pas les
permissions natives. Les fichiers de règles restent modifiables par leur propriétaire.

## Désactivation sans effet implicite sur les autres projets

```bash
pathtrace uninstall --framework codex --scope project
pathtrace uninstall --framework claude-code --scope project
pathtrace uninstall --framework codex --scope provider
pathtrace uninstall --framework claude-code --scope provider
```

La désactivation projet s'exécute à sa racine. Elle conserve le fichier, les règles
et les autres fournisseurs. Une liste `features: []` et `frameworks: {}` représente
un projet désactivé. Les autres projets et la configuration fournisseur restent
inchangés ; les règles fournisseur continuent donc à s'appliquer indépendamment.

La désinstallation fournisseur s'exécute depuis n'importe quel dossier et supprime
uniquement son fichier `pathtrace/security.yaml`. Elle ne modifie aucune configuration
projet. Les projets possédant leurs propres règles continuent à fonctionner.
Les réglages natifs et la configuration de l'autre fournisseur sont conservés.

Les hooks communs restent installés : il n'est pas possible de savoir quels autres
repositories les utilisent. Ils deviennent inactifs pour les fonctionnalités
désactivées. Les réglages natifs et les hooks utilisateur restent inchangés.
**Changement documenté :** l'ancienne commande `uninstall --framework ...` reste
acceptée, mais désactive désormais seulement le projet courant au lieu de retirer
les hooks de toute la machine. Ne pas supprimer le fichier projet désactivé si l'on
veut empêcher le retour au comportement Observe historique sans configuration.

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

## Capacités des fournisseurs

| Décision | Claude Code | Codex |
|---|---|---|
| `ALLOW` | conserve le flux de permissions natif | conserve le flux de permissions natif |
| `BLOCK` | `PreToolUse` retourne `deny` | `PreToolUse` retourne `deny` |
| `REQUIRE_APPROVAL` | `PreToolUse` retourne `ask` | `ask` non supporté : blocage explicite |

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
