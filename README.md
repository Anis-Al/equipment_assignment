# Affectation des équipements

Module Odoo 19 pour suivre le matériel de l’entreprise : ordinateurs, téléphones, outils, accessoires, etc.

L’objectif est simple : savoir **qui a quoi**, ce qui est disponible, et garder un historique des affectations.

---

## 1. Le besoin

Aujourd’hui, le suivi se fait surtout sur Excel et par email.

Le module permet de répondre rapidement à quelques questions :

* Qui détient cet équipement ?
* Est-il disponible ou déjà affecté ?
* Qui l’avait avant ?
* Depuis combien de temps ?
* Quels équipements sont inutilisés ou en retard de restitution ?

Deux profils sont prévus :

| Profil          | Accès                                                                                          |
| --------------- | ---------------------------------------------------------------------------------------------- |
| **Agent**       | Ajouter, affecter, récupérer, transférer et envoyer du matériel en maintenance                 |
| **Responsable** | Meme accès + rapports, catégories, mise au rebut, correction de l’historique et valeur d’achat |

---

## 2. Fonctionnement

J’ai choisi de faire un **module indépendant de Maintenance**.

Odoo possède déjà une gestion des équipements, mais elle ne garde pas correctement l’historique des anciens détenteurs. Ici, chaque affectation est enregistrée avec sa date de début et sa date de retour.

Le module repose sur trois éléments :

* **Catégories** : Informatique, Outillage, etc.
* **Équipements** : avec les statuts *Disponible*, *Affecté*, *En maintenance* et *Au rebut*.
* **Historique** : une ligne par affectation.

Le statut n’est pas modifiable directement. Il change via les actions **Affecter**, **Restituer**, **Transférer**, **Maintenance** et **Mise au rebut**.

Cela évite notamment qu’un équipement soit affecté à deux personnes en meme temps.

L’historique garde aussi les informations du moment. Si un employé change de service plus tard, les anciennes affectations gardent l’ancien service.

---

## 3. Quelques règles

* Un équipement est unique et peut avoir un seul détenteur à la fois.
* Les affectations se font aux **employés**, pas aux utilisateurs Odoo.
* Les dates sont gérées en jours.
* Les affectations passées peuvent etre ajoutées pour reprendre un ancien historique.
* L’historique est en lecture seule, sauf pour les notes. Les responsables peuvent corriger les dates.
* Chaque société voit uniquement son matériel.
* La valeur d’achat est informative et visible uniquement par les responsables.
* Lorsqu’un employé quitte l’entreprise, ses équipements encore affectés sont visibles dans le processus de départ.

Les réparations détaillées, amortissements, stock et codes-barres ne sont pas dans le périmètre actuel.

---

## 4. Performances

Le module est prévu pour fonctionner avec un volume important, jusqu’à environ **50 000 équipements et 1 million d’affectations**.

Pour cela :

* les recherches principales sont indexées ;
* la situation actuelle est disponible directement sur l’équipement ;
* l’historique chargé par défaut est limité ;
* les retards sont calculés à la demande ;
* les actions groupées sont testées sur plusieurs équipements ;
* aucun chatter n’est ajouté aux lignes d’historique pour éviter de faire grossir inutilement la table.

Si l’historique devient beaucoup plus important dans le futur, il pourra etre archivé par année.

---

## 5. Utilisation

Après installation :

1. Donner le rôle **Agent** ou **Responsable** aux utilisateurs.
2. Créer les catégories.
3. Ajouter les équipements. La référence est générée automatiquement, par exemple **EQ-000001**.
4. Utiliser **Affecter**, **Restituer** ou **Transférer** depuis les fiches.
5. Utiliser *Affectations › En cours* pour voir qui détient quoi.
6. Les responsables peuvent utiliser la partie **Analyse** pour les tableaux et graphiques.
