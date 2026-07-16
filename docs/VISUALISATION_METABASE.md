# Visualisation Metabase GoodAir

Ce document explique la mise en place de la visualisation des données du pipeline GoodAir via Metabase, les choix effectués, les visuels créés et les perspectives d'évolution.

---

## Contexte et objectif

Le pipeline GoodAir collecte des données météo et de qualité de l'air pour 11 villes françaises chaque heure. Ces données sont stockées dans un Data Warehouse SQL Server (schéma en étoile). Sans outil de visualisation, les chercheurs et experts du laboratoire TotalGreen n'ont accès aux données que via des requêtes SQL, ce qui n'est pas accessible à tous.

Metabase répond à ce besoin en permettant de créer des dashboards interactifs directement connectés au Data Warehouse, sans écrire de code. Les chercheurs peuvent explorer les données, filtrer par ville et par période, et consulter les prédictions ML en temps réel.

---

## Architecture technique

```text
Pipeline Airflow (horaire)
        ↓
SQL Server — GoodAirDW
        ↓
Metabase (connecté via JDBC)
        ↓
Dashboard accessible sur http://localhost:3001
```

Metabase tourne dans un conteneur Docker dédié, connecté au même réseau que SQL Server. Il utilise PostgreSQL (déjà présent pour Airflow) comme base de données interne pour stocker ses configurations, questions et dashboards.

---

## Configuration Docker

```yaml
metabase:
  image: metabase/metabase:latest
  container_name: metabase
  hostname: metabase
  volumes:
    - /dev/urandom:/dev/random:ro
  ports:
    - "3001:3000"
  environment:
    MB_DB_TYPE: postgres
    MB_DB_DBNAME: metabase
    MB_DB_PORT: 5432
    MB_DB_USER: airflow
    MB_DB_PASS: airflow
    MB_DB_HOST: postgres
    MB_JAVA_OPTS: "-Xmx1g -Xms512m"
  depends_on:
    postgres:
      condition: service_healthy
  restart: always
  mem_limit: 2g
```

**Points importants :**

- `/dev/urandom:/dev/random:ro` pour éviter le blocage au démarrage lié à l'entropie Linux
- `MB_JAVA_OPTS: "-Xmx1g"` :  alloue 1 Go de heap Java pour éviter les OutOfMemoryError
- `mem_limit: 2g` :  limite la consommation mémoire du conteneur
- Port `3001` choisi pour éviter les conflits avec les autres services dans mon environnement docker.

---

## Connexion à SQL Server

Dans Metabase → Administration → Bases de données → Ajouter une base de données :

| Paramètre       | Valeur      |
| --------------- | ----------- |
| Type            | SQL Server  |
| Nom             | GoodAir     |
| Hôte            | sqlserver   |
| Port            | 1433        |
| Base de données | GoodAirDW   |
| Utilisateur     | sa          |
| Mot de passe    | (voir .env) |
| SSL             | Désactivé   |

Metabase détecte automatiquement toutes les tables et leurs relations grâce aux clés étrangères définies dans SQL Server. Les jointures entre FactMesures, DimLieux et DimTemps sont proposées automatiquement sans écrire de SQL.

---

## Structure du dashboard

Le dashboard **Tableau de Bord de Surveillance : GoodAir** est organisé en deux onglets avec deux filtres globaux dynamiques.

### Filtres globaux

**Filtre Ville**: liste déroulante permettant de sélectionner une ou plusieurs villes parmi les 11 surveillées. Tous les graphiques se mettent à jour automatiquement selon la sélection.

**Filtre Date**: sélecteur de période permettant de filtrer par jour, semaine, mois ou plage personnalisée. Par défaut aucune valeur fixe — le dashboard affiche tout l'historique disponible.

---

## Onglet 1: Vue générale

### KPIs — Vue générale

| Indicateur                   | Valeur observée | Source      |
| ---------------------------- | --------------- | ----------- |
| Nombre de villes surveillées | 11              | DimLieux    |
| Total des mesures collectées | 11 666          | FactMesures |
| AQI moyen global             | 39.34           | FactMesures |
| Température moyenne globale  | 18.43 °C        | FactMesures |

Ces 4 KPIs sont affichés en haut du dashboard pour donner une vue d'ensemble immédiate. Ils sont volontairement globaux et ne sont pas affectés par le filtre Ville pour conserver les chiffres de référence.

### AQI moyen par ville

Graphique à barres verticales montrant l'indice de qualité de l'air moyen pour chaque ville sélectionnée. Paris apparaît systématiquement comme la ville la plus polluée (45.87) et Lyon comme la moins polluée (19.42) en raison de l'absence de capteurs PM25 et O3 sur sa station AQICN.

### Évolution de l'AQI dans le temps

Courbe temporelle montrant l'évolution journalière de l'indice de qualité de l'air depuis le début de la collecte (mars 2026). Chaque ville sélectionnée a sa propre courbe colorée. On observe clairement les pics de pollution à Paris en juin avec un maximum à 120 sur la courbe journalière.

### Prédictions de l'AQI pour les 6 prochaines heures

Graphique montrant les prédictions générées par le modèle Random Forest pour chaque ville et chaque heure future. Ces données proviennent de la table Gold.AlertesPredites et sont mises à jour à chaque run horaire d'Airflow. Le graphique est filtré sur la journée courante pour n'afficher que les prédictions pertinentes.

### Évolution de la température

Courbe temporelle de la température moyenne journalière par ville. Une ligne d'objectif rouge à 40°C matérialise le seuil de **Température extrême**. On observe clairement la montée progressive des températures de mars à juillet 2026.

---

## Onglet 2: Analyse détaillée

### KPIs Analyse détaillée

| Indicateur                | Valeur observée | Source          |
| ------------------------- | --------------- | --------------- |
| Nombre d'alertes prédites | 1 474           | AlertesPredites |
| Humidité moyenne globale  | 61.36 %         | FactMesures     |
| PM10 moyen global         | 37.08           | FactMesures     |
| Vitesse du vent moyenne   | 3.21 m/s        | FactMesures     |

La vitesse du vent est affichée sous forme de **jauge** avec des zones colorées (rouge, orange, vert) pour une lecture immédiate. C'est un choix de visualisation plus parlant qu'un simple chiffre.

### PM10, PM25 et O3 moyens par ville

Graphique à barres groupées montrant les trois polluants principaux côte à côte pour chaque ville. Cette visualisation permet de comparer facilement le profil de pollution de chaque ville. Paris a le PM25 le plus élevé, Lyon a des valeurs très basses sur PM25 et O3 en raison de l'absence de capteurs.

### Évolution de l'humidité

Courbe temporelle de l'humidité moyenne journalière par ville. L'humidité varie entre 30% et 90% selon les périodes, avec une tendance à la baisse en été, cohérente avec la montée des températures observée dans l'onglet 1.

### Disponibilité des APIs

Deux graphiques à barres montrant le nombre de mesures avec statut OK vs FAILED pour MeteoStatus (API OpenWeatherMap) et AirStatus (API AQICN). Ces graphiques confirment la très haute fiabilité des deux APIs sur la période avec moins de 0.1% de pannes pour OpenWeatherMap et moins de 0.03% pour AQICN.

---

## Rafraîchissement des données

Metabase met les résultats en cache par défaut. Deux options de mise à jour sont disponibles.

**Rafraîchissement automatique**: configuré à 1 heure pour être synchronisé avec la fréquence du pipeline Airflow. Les données auront au maximum 1 heure de décalage.

**Rafraîchissement manuel**: via l'icône de rafraîchissement en haut à droite du dashboard. Utile immédiatement après un run manuel d'Airflow.

---

## Pourquoi Metabase plutôt que Power BI ou Tableau

| Critère                     | Metabase | Power BI | Tableau |
| --------------------------- | -------- | -------- | ------- |
| Open source                 | oui      | non      | non     |
| Intégration Docker          | oui      | non      | non     |
| Gratuit                     | oui      | Limité   | non     |
| Connexion SQL Server        | oui      | oui      | oui     |
| Courbe d'apprentissage      | Faible   | Moyenne  | Élevée  |
| Adapté à notre infra locale | oui      | non      | non     |

Metabase s'intègre naturellement dans notre stack Docker et ne nécessite aucune licence. C'est le choix le plus cohérent pour un MVP local open source.

---

## Perspectives d'évolution

### Onglet 3: Performance du pipeline

Un troisième onglet dédié à la surveillance du pipeline lui-même avec le nombre de runs réussis vs échoués par jour, le nombre de lignes insérées par run, les villes avec le plus de pannes API, et l'historique des alertes email déclenchées.

### Onglet 4: Analyse météorologique approfondie

Un onglet dédié aux variables météo avec des corrélations entre vent, pression et qualité de l'air, une carte de chaleur de la température par ville et par mois, et des boxplots de distribution de chaque variable météo.

### Onglet 5: Qualité de l'air par polluant

Un onglet détaillé sur chaque polluant (PM25, PM10, NO2, O3) avec leur évolution dans le temps, leur répartition par ville et leur comparaison avec les seuils OMS (déjà disponibles dans la table Ref.SeuilsOMS du Data Warehouse).

### Alertes en temps réel dans Metabase

Metabase permet de configurer des alertes email directement depuis un graphique. Si l'AQI prédit dépasse un seuil défini, Metabase peut envoyer une notification indépendamment du pipeline Airflow. Cela offre une double couche d'alerting.

### Accès multi-utilisateurs

Créer des comptes distincts dans Metabase pour les chercheurs, les directeurs et les équipes BI avec des droits d'accès différenciés. Les chercheurs voient toutes les données, les directeurs voient uniquement les KPIs et les alertes.
