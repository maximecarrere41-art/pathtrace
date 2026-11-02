# ADR-001 — Appliquer les règles Security du fournisseur et du projet

**Statut :** accepté.

## Contexte

Pathtrace utilise des hooks partagés pour Codex et Claude Code. Les règles d'un
fournisseur doivent protéger tous ses projets, y compris ceux sans fichier local.
Une règle locale ne doit pas pouvoir affaiblir ces protections. Retirer les hooks
partagés depuis un projet pourrait interrompre les autres projets.

## Décision

Conserver deux portées : le fichier `pathtrace/security.yaml` dans le répertoire
utilisateur de chaque fournisseur, et `.pathtrace/config.yaml` pour le projet.
Aucune configuration commune aux deux fournisseurs n'est introduite.

Toutes les règles actives sont réellement appliquées. La priorité est blocage,
puis demande de validation, puis autorisation. Les identifiants sont uniques dans
une portée ; un identifiant partagé ne remplace aucune règle. L'ancien champ YAML
`mode` est ignoré sans réécrire le fichier. L'audit OTLP enregistre les décisions
appliquées et indique leur portée dans l'attribut `policy`.

La commande complète et les segments séparés par `&&`, `||`, `;`, `|`, `|&`, `&`
ou un retour à la ligne sont évalués. Les guillemets et les échappements simples
empêchent une séparation artificielle. Par exemple, `rm -rf build && git status`
reste bloqué par une règle shell malgré la présence de Git. Les priorités et le
départage lexical restent inchangés. Ce découpage ne constitue pas un interpréteur.

L'installation fournisseur propose explicitement les six presets avant toute
écriture. Une acceptation les rend immédiatement actifs. Les options existantes
`--presets` et `--no-presets` permettent aussi un choix explicite. Une configuration
existante n'est jamais remplacée. Aucun preset n'est ajouté implicitement au projet.

La portée par défaut reste `project`. Depuis la racine du projet, la désinstallation
désactive uniquement l'activation locale du fournisseur choisi, sans modifier sa
configuration fournisseur ni les autres projets. Sans configuration locale explicite,
elle ne crée aucune activation Observe pour un autre fournisseur.

Depuis n'importe quel dossier, la désinstallation `provider` supprime uniquement
le fichier Security du fournisseur concerné. Les configurations locales restent
fonctionnelles. Les hooks partagés sont conservés, car les autres repositories
qui les utilisent ne sont pas recensés.

Seule la purge explicite `uninstall --purge` retire tous les hooks Pathtrace du
fournisseur et son fichier Security, avec confirmation avant toute suppression.
`--yes` exprime la confirmation pour l'automatisation. La purge ne touche jamais
aux dossiers `.pathtrace` des projets, aux hooks utilisateur ou à l'autre fournisseur.
Elle ne se combine pas avec `--scope` et ne change pas ses deux comportements.
Après purge, les hooks ne déclenchent plus les fonctionnalités dans les projets ;
une installation ou une campagne peut les réinstaller.

## Conséquences

- **Positives :** règles toujours appliquées, priorité restrictive, fournisseurs
  isolés, fichiers utilisateur préservés lors d'une installation, projets autonomes
  après suppression de la configuration fournisseur.
- **Négatives :** les presets acceptés peuvent bloquer immédiatement un workflow ;
  leurs jokers peuvent produire des faux positifs. La suppression fournisseur est
  définitive pour ses règles personnalisées. Les hooks inactifs restent installés.
  Le découpage limité ne couvre pas les alias, scripts ou interpréteurs imbriqués.
  Une purge coupe volontairement le contrôle et la capture de tous les projets du
  fournisseur, même si leurs fichiers locaux sont conservés.

## Hypothèses traitées

- Les adaptateurs existants suffisent : réponses `deny` et `ask` vérifiées dans
  les tests des deux fournisseurs ; Codex bloque les validations non prises en charge.
- On peut supprimer tous les hooks après désinstallation : infirmé, car les
  projets peuvent encore les utiliser sans configuration fournisseur.
- Les anciens champs de configuration doivent être réécrits pour appliquer les
  règles : infirmé, la lecture peut imposer leur application sans modifier le fichier.
- Un pattern couvre toutes les commandes dangereuses : infirmé par les tests.
  Les limites et les faux positifs sont documentés dans le guide Security.

## État

- **Décidé :** deux portées, règles toujours appliquées, presets consentis,
  désinstallation locale et suppression fournisseur sans retrait des hooks partagés.
- **Implémenté :** sources, pipeline, CLI, presets, découpage des commandes et tests
  dans `test_security_scopes.py`, `test_security_presets.py` et `test_security_commands.py`.
- **À faire :** vérifier, si nécessaire, la livraison des hooks lors de sessions
  natives avec les versions d'agents utilisées par l'équipe. Les tests utilisent
  des payloads représentatifs, sans exécuter les commandes surveillées.
