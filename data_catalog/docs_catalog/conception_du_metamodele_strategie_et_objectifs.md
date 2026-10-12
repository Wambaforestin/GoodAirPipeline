# Conception du Métamodèle GoodAir : Stratégie et Périmètre (en cours...)

## 1. Contexte et Objectif Principal

Dans le cadre de l'amélioration de la gouvernance des données initiée par l'entreprise **TotalGreen**, le laboratoire **GoodAir** met en place un catalogue de données pour sa plateforme.

**La mission du catalogue (Le problème à résoudre) :**
> Permettre aux chercheurs de GoodAir de trouver, comprendre et exploiter les données environnementales en toute autonomie pour accélérer l'innovation.

## 2. Définition du Périmètre et des Actifs (Qu'allons-nous cataloguer ?)

Actuellement, l'entrepôt de données GoodAir possède une architecture très propre mais très technique : un schéma en étoile avec 1 table de faits (`FactMesures`) et 2 tables de dimensions (`DimLieux`, `DimTemps`).

**Le constat :**
Si le catalogue ne référence que ces trois tables physiques, il n'apportera pas beaucoup de valeur aux chercheurs, qui pensent en termes de "Sujets d'étude" et non en termes de "Clés étrangères".

**La stratégie d'actifs (Les Data Products) :**
Pour répondre au besoin d'autonomie des chercheurs, nos actifs principaux dans le catalogue ne seront pas de simples tables SQL, mais des **Produits de Données (Data Products)**.
Techniquement, ces produits prendront la forme de **Vues (ou Vues Matérialisées)** créées dans SQL Server, qui masquent la complexité du schéma en étoile.

*Exemples d'actifs qui peupleront le catalogue :*

- **Vue Consolidée** : "Historique Météo & Qualité de l'Air par Ville" (jointure pré-faite entre Faits et Dimensions).
- **Dataset Analytique** : "Moyennes Journalières des Polluants" (données pré-agrégées).
- **Dataset Machine Learning** : "Features ML et Alertes Prédites" (pour les data scientists).

En cataloguant ces Vues / Data Products, le chercheur trouve immédiatement un tableau prêt à être exporté dans R, Python ou Power BI, sans avoir à écrire de requêtes SQL complexes.

## 3. L'Approche de Modélisation (Capacités vs Processus)

Pour organiser ces futurs Produits de Données dans le catalogue, nous devons structurer nos **Domaines de Données**.

Conformément aux meilleures pratiques, nous choisissons d'organiser le métamodèle autour des **Capacités Métier (Business Capabilities)** du laboratoire GoodAir, et non de ses processus.

- **Pourquoi ?** Les processus changent avec les outils (ex: la façon dont un chercheur extrait la donnée aujourd'hui changera demain). Les capacités sont l'essence du laboratoire et sont stables dans le temps.
- **Résultat attendu :** Les domaines du catalogue représenteront les grands piliers d'expertise du laboratoire GoodAir (ex: Étude du Climat, Analyse de la Pollution, etc.).
  