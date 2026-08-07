# Intégration Codex

L’intégration Codex contient deux composants séparés :

- `CodexAdapter` observe les hooks Codex et transforme leurs données en trace Pathtrace ;
- `CodexRunner` lance Codex automatiquement pour exécuter une campagne de scénarios.

Cette séparation permet de conserver le même moteur de test, le même format de trace et le même graphe lorsqu’un autre agent sera ajouté plus tard.

---

## Deux modes d’utilisation

### 1. Observation manuelle

Ce mode sert à analyser un prompt lancé directement dans Codex.

```text
Utilisateur dans Codex
        ↓
Hooks Codex
        ↓
CodexAdapter
        ↓
trace.json
        ↓
pathtrace test
```

Utilisez ce mode pour :

- comprendre ce que Codex a réellement exécuté ;
- vérifier les skills chargées ;
- contrôler l’ordre des outils et commandes ;
- écrire ou ajuster progressivement un fichier YAML de test.

Exemple :

```powershell
cd C:\Dev\mon-projet
codex
```

Après le prompt :

```powershell
pathtrace test --latest --tests .pathtrace\tests\test.yaml --report --graph
```

### 2. Campagne automatisée

Ce mode sert à lancer un ou plusieurs prompts sans ouvrir Codex manuellement.

```text
scenarios.yaml
      ↓
CodexRunner
      ↓
codex exec
      ↓
Hooks Codex
      ↓
CodexAdapter
      ↓
trace.json
      ↓
assertions + rapport + graphe
```

Utilisez ce mode pour :

- automatiser plusieurs prompts ;
- exécuter une campagne de non-régression ;
- intégrer Pathtrace dans une CI ;
- comparer les comportements après une modification de skill, de configuration ou de modèle.

Exemple :

```powershell
pathtrace run --tests .pathtrace\tests\scenarios.yaml --report --graph
```

---

# Adaptateur Codex

## Hooks installés

| Hook Codex | Utilité Pathtrace |
|---|---|
| `UserPromptSubmit` | Mémorise le prompt et le modèle au début du tour. |
| `PreToolUse` | Enregistre le début d’un appel et ses arguments. |
| `PostToolUse` | Complète le même appel avec son statut et sa sortie. |
| `Stop` | Finalise et écrit la trace du tour. |

En activation `security`, seul `PreToolUse` est nécessaire. Pathtrace peut y
retourner `deny` pour bloquer une action. La valeur `ask` n'est actuellement
pas supportée par le hook Codex : `REQUIRE_APPROVAL` est donc bloqué
explicitement en mode enforce. Pathtrace ne retourne pas `allow`, afin de
conserver les permissions natives de Codex.

Voir [Runtime Security et audit des décisions](security.md).

`PreToolUse` et `PostToolUse` sont reliés par `tool_use_id` ou `call_id` lorsqu’il est disponible. Un appel n’est donc compté qu’une fois.

## Propriétés Codex interceptées

| Propriété native | Utilisation Pathtrace |
|---|---|
| `session_id` / `sessionId` | `trace.session_id` |
| `turn_id` / `turnId` | `trace.turn_id` |
| `prompt`, `user_prompt`, `message` | `trace.prompt` |
| `model`, `model_name` | `trace.model` |
| `tool_name` / `toolName` | `event.name` |
| `tool_input` / `toolInput` | `event.input` |
| `tool_response` / `toolResponse` | `event.status` et `event.output_summary` |
| `tool_use_id`, `call_id`, `id` | Corrélation technique dans `event.raw` |

## Commandes

Les propriétés natives `command`, `cmd` ou `script` deviennent directement `event.command`.

```json
{
  "type": "tool_call",
  "name": "Bash",
  "command": "python -m pytest"
}
```

Pathtrace ne contient aucune liste codée en dur de commandes comme `pytest`, `git` ou `dotnet`.

## Skills

Une skill est reconnue lorsque :

1. l’outil natif s’appelle `Skill` ou `Skills` et fournit un nom ;
2. un argument ou une commande contient un chemin `skills/<nom>/SKILL.md`.

```json
{
  "type": "skill",
  "name": "conventions-code",
  "tool": "Bash",
  "path": "\\skills\\conventions-code\\SKILL.md"
}
```

---

# Configuration de Codex pour les campagnes automatisées

## 1. Installer Codex CLI

Installation avec npm :

```powershell
npm install -g @openai/codex
```

Vérification :

```powershell
codex --version
Get-Command codex
```

Le mode automatisé de Pathtrace utilise la commande non interactive `codex exec`.

## 2. Authentifier Codex

Avant une campagne, vérifiez que Codex fonctionne seul :

```powershell
codex
```

Si Codex demande une authentification, terminez-la avant de lancer Pathtrace.

Pathtrace ne gère pas lui-même l’authentification OpenAI.

## 3. Configurer l’exécutable

Par défaut, Pathtrace cherche :

```text
codex
```

Sous Windows, l’exécutable réel peut être un fichier `codex.cmd`.

Pour le trouver :

```powershell
(Get-Command codex).Source
```

Vous pouvez le définir dans le YAML :

```yaml
defaults:
  executable: "...\\codex.cmd"
```

Ou avec une variable d’environnement :

```powershell
$env:PATHTRACE_CODEX_EXECUTABLE = (Get-Command codex).Source
pathtrace run --tests .pathtrace\tests\scenarios.yaml
```

La valeur définie dans le scénario ou dans `defaults` doit être prioritaire sur la variable d’environnement.

## 4. Choisir le modèle

Pathtrace ne sélectionne pas directement le LLM. Il transmet les arguments au CLI Codex.

```yaml
defaults:
  runner_args:
    - --model
    - gpt-5.6-terra
```

Commande équivalente :

```powershell
codex exec --json --model gpt-5.6-terra "Votre prompt"
```

Le nom du modèle doit être accepté par la version de Codex installée et disponible pour votre compte.

## 5. Définir l’effort de raisonnement

Les valeurs de configuration Codex peuvent être surchargées avec `--config` ou `-c`.

```yaml
defaults:
  runner_args:
    - --model
    - gpt-5.6-terra
    - --config
    - model_reasoning_effort="medium"
```

Exemple avec un effort élevé :

```yaml
defaults:
  runner_args:
    - --config
    - model_reasoning_effort="high"
```

## 6. Utiliser un profil Codex

Codex permet d’utiliser un profil de configuration.

Dans le fichier utilisateur :

```text
C:\Users\<utilisateur>\.codex\config.toml
```

Exemple :

```toml
[profiles.pathtrace]
model = "gpt-5.6-terra"
model_reasoning_effort = "medium"
```

Dans le scénario Pathtrace :

```yaml
defaults:
  runner_args:
    - --profile
    - pathtrace
```

Les options explicites passées dans `runner_args` permettent de surcharger les valeurs de configuration Codex.

## 7. Configurer la sandbox

Le mode sandbox contrôle les accès accordés aux commandes lancées par Codex.

```yaml
defaults:
  runner_args:
    - --sandbox
    - workspace-write
```

Modes courants :

| Valeur | Utilisation |
|---|---|
| `read-only` | Lecture uniquement. Adapté à une analyse sans modification. |
| `workspace-write` | Lecture et écriture dans le workspace. Recommandé pour la majorité des campagnes. |
| `danger-full-access` | Accès très large. À réserver aux environnements isolés et maîtrisés. |

Pour une campagne publique ou une CI, privilégiez `read-only` ou `workspace-write`.

## 8. Définir le dossier de travail

Une campagne doit être lancée depuis le dépôt concerné :

```powershell
cd C:\Dev\mon-projet
pathtrace run --tests .pathtrace\tests\scenarios.yaml
```

Le dossier courant sert notamment à :

- localiser `.pathtrace` ;
- écrire les états et les traces ;
- donner à Codex le bon workspace ;
- résoudre les chemins relatifs des fichiers YAML.

Évitez de lancer Codex ou Pathtrace depuis :

```text
C:\Windows\System32
```

## 9. Passer des arguments supplémentaires

Les arguments sont transmis directement à Codex sans passer par un shell.

```yaml
defaults:
  runner_args:
    - --skip-git-repo-check
    - --sandbox
    - workspace-write
```

Avant de les utiliser dans Pathtrace, vérifiez leur compatibilité :

```powershell
codex exec --help
```

Les options disponibles peuvent évoluer selon la version de Codex CLI.

---

# Exemple complet de campagne Windows

```yaml
version: 1
framework: codex

defaults:
  executable: "...\\codex.cmd"
  timeout: 300
  runner_args:
    - --model
    - gpt-5.6-terra
    - --config
    - model_reasoning_effort="medium"
    - --sandbox
    - workspace-write
    - --skip-git-repo-check

scenarios:
  - name: model-routing chargé
    prompt: >
      utilise uniquement la skill model-routing, puis dis moi quel modele pour lire un fichier de code et donner un compte rendu ?
    assertions:
      - type: must_include
        event: "skill:model-routing"

  - name: conventions chargées dans le bon ordre
    prompt: >
      Va lire la skill conventions-code puis la skill conventions-dotnet,
      dans cet ordre.
    assertions:
      - type: path_matches
        sequence:
          - event: "skill:conventions-code"
          - event: "skill:conventions-dotnet"
```

Lancement :

```powershell
pathtrace run \
  --tests .pathtrace\tests\scenarios.yaml \
  --report \
  --graph
```

Sous PowerShell sur une seule ligne :

```powershell
pathtrace run --tests .pathtrace\tests\scenarios.yaml --report --graph
```

---

# Priorité de configuration

Pour les options Codex, la priorité recommandée est :

```text
runner_args du scénario
        ↓
defaults.runner_args
        ↓
profil Codex
        ↓
config.toml utilisateur
        ↓
valeurs par défaut de Codex
```

Pour l’exécutable :

```text
scenario.executable
        ↓
defaults.executable
        ↓
PATHTRACE_CODEX_EXECUTABLE
        ↓
codex trouvé dans PATH
```

---

# Fichiers générés

Pendant un tour :

```text
.pathtrace/.state/codex/<session_id>/<turn_id>.json
```

Après le hook `Stop` :

```text
.pathtrace/traces/codex/<session_id>/<turn_id>.json
```

Rapports de campagne :

```text
.pathtrace/campaigns/<nom-campagne>.json
```

Graphes et rapports individuels :

```text
.pathtrace/reports/
.pathtrace/graphs/
```

Le dossier `.state` est temporaire. Les tests YAML, rapports et graphes doivent utiliser les traces finales.

---

# Diagnostic

## Erreur : exécutable Codex introuvable

```text
Exécutable Codex introuvable : codex
```

Vérifiez :

```powershell
Get-Command codex
(Get-Command codex).Source
```

Puis configurez le chemin complet dans `defaults.executable` ou dans `PATHTRACE_CODEX_EXECUTABLE`.

## Erreur : accès refusé dans System32

Lancez Pathtrace depuis le dépôt voulu

## Erreur : invalid stop hook JSON output

Le hook `Stop` doit écrire uniquement un objet JSON valide sur stdout, par exemple :

```json
{}
```

Les chemins de trace et les messages de diagnostic ne doivent pas être imprimés sur stdout par le hook.

## Les hooks sont chargés deux fois

Si Codex affiche :

```text
loading hooks from both hooks.json and config.toml
```

Conservez la déclaration des hooks dans un seul emplacement afin d’éviter les doubles appels.

## Vérifier la commande réellement construite

Testez d’abord Codex sans Pathtrace :

```powershell
codex exec --json --model gpt-5.6-terra "Réponds uniquement OK"
```

Puis lancez la campagne Pathtrace.

---

# Point de validation réel

Pathtrace tolère plusieurs variantes de noms de propriétés dans les payloads Codex. Cependant, une campagne réelle reste nécessaire après chaque évolution importante de Codex CLI afin de vérifier :

- le format exact des hooks ;
- les options acceptées par `codex exec` ;
- le comportement du modèle sélectionné ;
- la sandbox et les permissions ;
- la création correcte des traces.

Utilisez toujours :

```powershell
codex --version
codex exec --help
```

avant de diagnostiquer un problème propre à une version de Codex.
