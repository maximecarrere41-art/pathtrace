# Bilan du Goal Security fournisseur/projet et référence CLI

Validation locale du 2 novembre 2026. Ce document décrit les vérifications de
cette évolution, pas une garantie de couverture de toutes les commandes shell.

## Purge explicite du fournisseur

`uninstall --purge` retire les hooks Pathtrace et le fichier Security fournisseur
après confirmation ; `--yes` confirme sans interaction. Les deux portées de
désinstallation restent inchangées. Les dossiers `.pathtrace` des projets, les
hooks utilisateur, les réglages natifs et l'autre fournisseur sont conservés.

`tests/test_purge.py` vérifie confirmation, refus, absence de réponse, automatisation,
idempotence, fichiers absents ou invalides, anciens hooks Codex, variantes de flags,
isolation des fournisseurs et conservation exacte des fichiers des projets.

Dernière validation : **407 tests réussis, 1 ignoré en 6,63 s**. Compilation Python
et contrôle du diff réussis. Le test ignoré nécessite le privilège Windows de
création d'un lien symbolique. Les sorties `.pathtrace/validation-purge-*` sont
nettoyées après validation. Aucune purge des agents réels n'a été effectuée.

## Application systématique des règles et désinstallation fournisseur

Les règles Security sont toujours appliquées. L'ancien champ YAML `mode` est
ignoré sans modifier les fichiers existants. Les presets explicitement acceptés
sont immédiatement actifs. L'option CLI de choix d'application a été retirée.
L'audit OTLP enregistre les décisions effectivement appliquées.

La désinstallation projet laisse la configuration fournisseur intacte. La
désinstallation fournisseur supprime uniquement son fichier Security, depuis
n'importe quel dossier, sans modifier les projets ni les hooks partagés. Une
installation ultérieure initialise un nouveau fichier après un nouveau choix
explicite ; elle ne restaure pas les règles supprimées.

La référence CLI reste un tableau à quatre colonnes et le README conserve
Security en premier, avec l'image historique dans la section Observe/Test.
Les tests vérifient la conservation exacte des fichiers utilisateur, le rejet de
l'option retirée, les décisions natives et les deux portées de désinstallation.

Dernière validation : **367 tests réussis, 1 ignoré en 5,77 s**. Compilation Python
et contrôle du diff réussis. Le test ignoré nécessite un privilège Windows pour
créer un lien symbolique. Aucune session native ni validation émulateur réalisée.
Les sorties `.pathtrace/validation-enforce-*` sont nettoyées après validation.

Les sections suivantes conservent les résultats des étapes précédentes.

## Corrections après revue

- Sans configuration locale explicite, `uninstall` n'écrit plus les valeurs Observe
  historiques comme activation d'un autre fournisseur. Tests avec et sans fichier
  fournisseur, contrôle de la capture et conservation des anciennes activations explicites.
- La commande complète et ses segments shell sont évalués ensemble, avec les
  priorités existantes. `rm -rf build && git status` et l'ordre inverse sont bloqués.
  Séparateurs, guillemets, échappements, redirection et priorités sont couverts par
  `tests/test_security_commands.py` et les tests de hooks des deux fournisseurs.
- Le README présente Runtime Security en premier et Observe/Test en complément.
  La référence CLI contient uniquement le tableau à quatre colonnes, avec toutes
  les options publiques, les exemples et les indications de portée demandées.
- Validation de ces corrections : **358 tests réussis, 1 ignoré en 5,48 s**.
  Compilation Python et contrôle du diff réussis. Le test ignoré reste celui du
  lien symbolique Windows, faute de privilège. Aucune session native ni émulateur
  lancé ; les commandes surveillées sont évaluées sans être exécutées.
- Les nouveaux fichiers sont `pathtrace/security/commands.py` et
  `tests/test_security_commands.py`. L'ADR existant et le guide Security sont actualisés.
- Les sorties `.pathtrace/validation-corrections-*` de cette validation sont nettoyées.

Les résultats ci-dessous décrivent la validation initiale, avant ces corrections.

## Audit initial

- Les deux adaptateurs installaient déjà leurs hooks dans le répertoire utilisateur
  du fournisseur, par fusion avec les réglages existants.
- Le pipeline chargeait uniquement `.pathtrace/config.yaml`. Sans ce fichier,
  Observe était actif par défaut et Security absent.
- Le moteur déterministe appliquait déjà les trois décisions et leur priorité.
  Il reste indépendant du catalogue des nouveaux presets.
- L'ancienne désinstallation CLI retirait les hooks partagés et pouvait couper
  les autres projets. Elle désactive désormais seulement la portée choisie.
- Référence avant modification : 132 tests réussis, un ignoré, en 2,45 s.

## Exigences et preuves

| Exigence | Réalisation et validation |
|---|---|
| Fournisseur seul, projet seul, combinaison, absence de fichier local | `tests/test_security_scopes.py` passe les payloads par la CLI et le pipeline des deux fournisseurs |
| Projet incapable d'affaiblir le fournisseur | Croisement des trois décisions projet et des deux modes contre un blocage fournisseur ; priorité inverse et validation appliquée face à un blocage audité |
| Identifiants et isolation | Même identifiant conservé aux deux niveaux ; doublons dans une portée rejetés ; fournisseur opposé non affecté ; attribut d'audit `policy` distinct |
| Modes indépendants et configurations invalides | Tests d'audit seul, d'enforcement et de blocage par précaution ; aucun mode projet ne remplace celui du fournisseur |
| Installation, désactivation et réactivation | Tests d'idempotence, préservation des hooks utilisateur, règles personnalisées, mode et fichiers ; désactivation locale sans coupure d'un autre repository ni activation Observe d'un fournisseur Security seul |
| Presets et choix initial | `tests/test_security_presets.py` vérifie confirmation avant écriture, abandon sans effet, choix explicites, audit initial et application native des règles |
| Variantes et limites des patterns | Tests des commandes composites, variantes Git et suppression, payloads natifs, accès SSH explicite, faux positifs et cas non détectés documentés |
| Observe/Test et campagnes | Suite complète existante conservée, exemple réel de trace produisant rapport et graphe, runners testés avec leurs doubles de processus |
| Audit OTLP | Tests existants de caviardage, export différé, indisponibilité et exporteur lent ; tests de provenance et résultats des deux portées |
| Diagnostic | `status` expose les fonctionnalités par fournisseur, les chemins des deux portées, les règles, les modes et l'état OTLP |
| README et référence exhaustive | Deux piliers avec schéma, exemple, commandes et liens ; `tests/test_cli_reference.py` confronte toutes les commandes/options publiques et la syntaxe des exemples à Click |

## Fichiers modifiés ou ajoutés

| Ensemble | Fichiers |
|---|---|
| Chemins et activation | `pathtrace/provider_paths.py`, `pathtrace/activation.py`, `pathtrace/config.py` |
| CLI et diagnostic | `pathtrace/cli.py`, `pathtrace/status.py` |
| Pipeline et adaptateurs | `pathtrace/hooks/pipeline.py`, `pathtrace/hooks/security.py`, `pathtrace/adapters/codex.py`, `pathtrace/adapters/claude_code.py` |
| Sources Security et presets | `pathtrace/security/sources.py`, `pathtrace/security/presets.py`, `pathtrace/security/initialization.py`, `pathtrace/security/action.py` |
| Tests | `tests/test_security_scopes.py`, `tests/test_security_presets.py`, `tests/test_cli_reference.py`, `tests/test_uninstallation.py` |
| Documentation | `README.md`, `docs/cli-reference.md`, `docs/security.md`, `docs/quickstart.md`, `docs/codex-adapter.md`, `docs/claude-code-adapter.md`, `docs/adr/ADR-001-security-fournisseur-projet.md`, ce bilan |
| Nettoyage | `.gitignore` : `.validation*/` et `.test-tmp/` ; les sorties suivantes sont produites sous `.pathtrace/`, déjà ignoré |

Les décisions sont décrites dans l'[ADR-001](adr/ADR-001-security-fournisseur-projet.md).
Aucune nouvelle dépendance applicative n'est introduite. Les options Security
existantes et les outils de build ont été utilisés dans un dossier de validation
isolé, sans modifier l'installation Python globale.

## Vérifications exécutées

- Suite complète finale avec les dépendances OTLP : **274 réussis, 1 ignoré**,
  **5,72 s** d'exécution pytest. Les commandes passent par RTK.
- `python -m compileall -q pathtrace` : réussi.
- `git diff --check` : réussi.
- Construction du wheel `pathtrace-1.1.0-py3-none-any.whl` via
  `setuptools.build_meta.build_wheel` depuis une copie temporaire des sources
  finales : réussie, environ 1,74 s de commande.
- Contrôle AST des nouveaux modules : corps des fonctions limité à dix lignes.
- Les dossiers `.validation-*` de la session sont supprimés. Les dépendances,
  copies de packaging et sorties de validation isolées sont nettoyées en fin
  d'exécution. Les tests sources sont conservés.

Le temps actif de développement n'a pas été mesuré. Les durées ci-dessus sont
celles des commandes, pas des heures de développement. La charge restante pour
le périmètre implémenté est nulle ; les contrôles natifs optionnels restent à
l'équipe selon son environnement.

## Limites et contrôles manuels

- Le test ignoré nécessite la création d'un lien symbolique de répertoire.
  Windows retourne `WinError 1314`, faute de privilège. Le relancer dans un
  environnement permettant cette opération. Les autres tests de chemins et de
  jonctions restent couverts par la suite.
- Les tests de hooks utilisent des payloads représentatifs et vérifient leurs
  réponses natives. Aucune session réelle Codex ou Claude n'a été lancée et
  aucun agent utilisateur n'a été reconfiguré pour ces validations. Un contrôle
  manuel de livraison des hooks par les versions installées reste possible.
- Aucun collecteur OTLP externe n'est requis ni sollicité par les tests ; les
  comportements d'export et d'échec sont vérifiés avec des doubles contrôlés.
- Les limites des presets sont explicites dans le [guide Security](security.md#presets-fournisseur).
- Les premiers essais de tests et de packaging ont rencontré des refus d'accès
  aux dossiers temporaires dans le sandbox ; les validations ont réussi avec
  accès aux dossiers de validation. Le backend de build était absent de Python
  global ; il a été utilisé depuis le dossier isolé.
- Le build signale une dépréciation préexistante de la forme TOML `project.license`.
  Elle n'est pas modifiée dans ce Goal.
- `graphify update . --no-cluster --force` a été tenté avant et après les
  modifications ; il échoue sur un refus d'accès Windows. L'analyse et la revue
  ont donc été faites directement dans les sources ; aucun index généré n'a été
  modifié manuellement.
- Aucune validation sur émulateur n'est pertinente pour cette CLI Python.
- Aucun commit, push, branche ou Pull Request n'a été créé.
