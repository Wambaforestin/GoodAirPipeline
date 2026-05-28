# Audit des Sources de Données — GoodAir Pipeline

## Phase 1 : Audit et Compréhension des Sources de Données

Avant d'écrire la moindre ligne de code, nous avons réalisé un audit des sources de données disponibles. Cette phase nous a permis de comprendre les caractéristiques de nos sources (du JSON fortement imbriqué) et de réaliser que **nous n'avions aucun contrôle sur ces sources**.

Voici les questions fondamentales que nous nous sommes posées, et nos réponses :

* **Quelles sont les caractéristiques les plus essentielles de notre source de données ?**
  *Réponse :* Du JSON issu de deux APIs distinctes.
* **Comment les données sont-elles stockées dans le système source ?**
  *Réponse :* Les APIs tierces fournissent du temps réel. L'historique gratuit n'est pas disponible de manière illimitée. Nous devons donc capturer la donnée sur le moment.
* **C'est quoi le niveau de consistance et la fréquence des erreurs ?**
  *Réponse :* Les erreurs de type "donnée corrompue" sont rares. En revanche, les erreurs de type "réseau" (Timeout HTTP 408, Service Indisponible 503, Quotas 429) peuvent survenir quotidiennement.
* **Quel est le schéma des données ingérées ? Devrons-nous joindre plusieurs systèmes ?**
  *Réponse :* Le schéma source est fortement dénormalisé et imbriqué (ex: `main.temp`, `iaqi.pm25.v`). Un gros effort de modélisation est requis. Nous devrons aplatir (*Flatten*) ces JSON et croiser deux systèmes distincts (Météo et Pollution) au sein d'une seule table de faits.
* **Si le schéma change (Schema Drift), comment allons-nous gérer cela ?**
  *Réponse :* À l'ingestion (Python), nous extrayons le JSON complet sans filtrage pour garantir que tout nouveau champ soit sauvegardé dans notre Data Lake (zone Bronze). À la transformation, notre code agit comme une douane stricte (Data Contract) : il extrait uniquement ce qui est attendu par SQL Server et crashe proprement si un champ critique disparaît. Modifier la structure de la base SQL reste une décision métier, pas un automatisme risqué.
* **À quelle fréquence les données seront extraites ?**
  *Réponse :* Par lots (Batch) avec une fréquence d'une fois par heure.

### Point fort de l'audit

Les données issues des APIs présentent une base solide. Les réponses JSON contiennent les indicateurs essentiels (AQI, PM2.5, PM10, NO₂, O₃, température, humidité, vent). Cet audit nous a aussi permis de revoir notre périmètre : nous sommes passés de 3 villes initiales à 11 villes surveillées pour garantir un volume de données suffisant pour les futurs cas d'usage analytiques.

### Point de vigilance

* **Données manquantes** : Certaines villes ne fournissent pas tous les indicateurs (ex: Franconville ne mesure pas l'O₃). Nous devons gérer ces absences de manière intelligente (garder les nulls légitimes, éviter les imputations hasardeuses).
* **Les APIs fournissent des formats de date différents** (ex: `dt` en timestamp Unix pour la météo, `time.s` en string ISO pour la pollution).
* **Dépendance à une source tierce** : Nous n'avons aucun contrôle sur la disponibilité ou la structure des données. En cas de non disponibilité d'une API pendant une période prolongée, nous devrons envisager des sources alternatives (ex: France Météo) ou des stratégies de fallback.
* **Quota des APIs** : Dans le cahier des charges, il est précisé que nous devons respecter les limites de la formule gratuite des APIs.

---

## Détail des sources

### OpenWeatherMap — API Météo

| Caractéristique  | Détail                                                                 |
| ---------------- | ---------------------------------------------------------------------- |
| URL              | `https://api.openweathermap.org/data/2.5/weather`                      |
| Format           | JSON imbriqué                                                          |
| Authentification | Clé API (paramètre `appid`)                                            |
| Plan             | Gratuit (1 000 appels/jour)                                            |
| Latence          | ~200ms par appel                                                       |
| Données fournies | Température, humidité, pression, vent, coordonnées GPS, code pays      |
| Imbrication      | `main.temp`, `main.humidity`, `wind.speed`, `sys.country`, `coord.lat` |
| Historique       | Non disponible sur le plan gratuit (temps réel uniquement)             |

**Payload complet :**

```json
{
  "coord": {"lon": 2.3488, "lat": 48.8534},
  "weather": [
    {
      "id": 800,
      "main": "Clear",
      "description": "clear sky",
      "icon": "01d"
    }
  ],
  "base": "stations",
  "main": {
    "temp": 15.32,
    "feels_like": 14.5,
    "temp_min": 14.0,
    "temp_max": 16.5,
    "pressure": 1012,
    "humidity": 56,
    "sea_level": 1012,
    "grnd_level": 1005
  },
  "visibility": 10000,
  "wind": {
    "speed": 4.1,
    "deg": 210,
    "gust": 6.2
  },
  "clouds": {"all": 0},
  "dt": 1770811200,
  "sys": {
    "type": 2,
    "id": 2041230,
    "country": "FR",
    "sunrise": 1770790800,
    "sunset": 1770828000
  },
  "timezone": 3600,
  "id": 2988507,
  "name": "Paris",
  "cod": 200
}
```

**Champs utilisés dans le pipeline :**

| Chemin JSON     | Colonne DW                             | Usage                                     |
| --------------- | -------------------------------------- | ----------------------------------------- |
| `coord.lat`     | Latitude                               | Position GPS                              |
| `coord.lon`     | Longitude                              | Position GPS                              |
| `main.temp`     | Temperature                            | Mesure météo principale                   |
| `main.humidity` | Humidite                               | Mesure météo                              |
| `main.pressure` | Pression                               | Mesure météo                              |
| `wind.speed`    | VitesseVent                            | Mesure météo                              |
| `sys.country`   | CodePays                               | Référentiel lieu                          |
| `name`          | Non utilisé (NomVille vient du config) | Évité pour garantir la cohérence du merge |

**Champs non utilisés (mais conservés dans Bronze) :**

| Chemin JSON                          | Pourquoi non utilisé                        | Potentiel V2                                       |
| ------------------------------------ | ------------------------------------------- | -------------------------------------------------- |
| `weather[0].main`                    | Description textuelle ("Clear", "Rain")     | Catégorisation météo pour les chercheurs           |
| `weather[0].description`             | Description détaillée ("clear sky")         | Idem                                               |
| `main.feels_like`                    | Température ressentie, pas une mesure brute | Analyse confort thermique                          |
| `main.temp_min` / `main.temp_max`    | Min/Max sur une zone, pas un point précis   | Amplitude thermique instantanée                    |
| `main.sea_level` / `main.grnd_level` | Pression au niveau mer / sol                | Analyse météo avancée                              |
| `visibility`                         | Visibilité en mètres                        | Corrélation visibilité/pollution                   |
| `wind.deg`                           | Direction du vent en degrés                 | Analyse de la provenance des polluants             |
| `wind.gust`                          | Rafales de vent                             | Alertes tempête                                    |
| `clouds.all`                         | Couverture nuageuse (%)                     | Corrélation ensoleillement/ozone                   |
| `dt`                                 | Timestamp Unix de la mesure                 | Non utilisé : on préfère le Time Bucketing Airflow |
| `sys.sunrise` / `sys.sunset`         | Heures de lever/coucher du soleil           | Analyse jour/nuit sur la pollution                 |
| `timezone`                           | Décalage UTC en secondes                    | Non nécessaire (on gère le timezone dans le code)  |
| `id`                                 | ID interne OpenWeatherMap de la ville       | Pas pertinent pour notre modèle                    |
| `cod`                                | Code HTTP de la réponse                     | Vérifié via `raise_for_status()`, pas stocké       |
| `base`                               | Source de la station ("stations")           | Métadonnée interne OWM                             |

### AQICN — API Qualité de l'Air

| Caractéristique  | Détail                                                              |
| ---------------- | ------------------------------------------------------------------- |
| URL              | `https://api.waqi.info/feed/{city}/`                                |
| Format           | JSON doublement imbriqué                                            |
| Authentification | Token (paramètre `token`)                                           |
| Plan             | Gratuit (pas de limite stricte documentée)                          |
| Latence          | ~300ms par appel                                                    |
| Données fournies | AQI global, PM2.5, PM10, NO2, O3 (en indices AQI, pas en µg/m³)     |
| Imbrication      | `data.aqi`, `data.iaqi.pm25.v`, `data.iaqi.no2.v`, `data.city.name` |
| Historique       | Non disponible sur le plan gratuit                                  |

**Payload complet :**

```json
{
  "status": "ok",
  "data": {
    "aqi": 85,
    "idx": 4512,
    "attributions": [
      {
        "url": "https://www.atmo-nouvelleaquitaine.org/",
        "name": "Atmo Nouvelle-Aquitaine"
      }
    ],
    "city": {
      "geo": [44.8378, -0.5792],
      "name": "Bordeaux",
      "url": "https://aqicn.org/city/bordeaux"
    },
    "dominentpol": "pm25",
    "iaqi": {
      "co": {"v": 8.2},
      "no2": {"v": 40.5},
      "pm10": {"v": 55},
      "pm25": {"v": 85},
      "so2": {"v": 15.6},
      "t": {"v": 14.2},
      "p": {"v": 1015},
      "h": {"v": 60}
    },
    "time": {
      "s": "2026-02-11 12:00:00",
      "tz": "+01:00",
      "v": 1770811200,
      "iso": "2026-02-11T12:00:00+01:00"
    },
    "forecast": {
      "daily": {
        "pm25": [
          {"avg": 80, "day": "2026-02-11", "max": 95, "min": 40},
          {"avg": 45, "day": "2026-02-12", "max": 60, "min": 20}
        ]
      }
    },
    "debug": {"sync": "2026-02-11T12:15:00+01:00"}
  }
}
```

**Champs utilisés dans le pipeline :**

| Chemin JSON        | Colonne DW                             | Usage                                                             |
| ------------------ | -------------------------------------- | ----------------------------------------------------------------- |
| `data.aqi`         | AqiGlobal                              | Indice global de qualité de l'air                                 |
| `data.iaqi.pm25.v` | PM25                                   | Indice AQI particules fines                                       |
| `data.iaqi.pm10.v` | PM10                                   | Indice AQI particules                                             |
| `data.iaqi.no2.v`  | NO2                                    | Indice AQI dioxyde d'azote                                        |
| `data.iaqi.o3.v`   | O3                                     | Indice AQI ozone                                                  |
| `data.city.name`   | Non utilisé (NomVille vient du config) | Évité car le nom peut varier ("Paris" vs "Paris, Champs-Élysées") |

**Champs non utilisés (mais conservés dans Bronze) :**

| Chemin JSON           | Pourquoi non utilisé                       | Potentiel V2                                         |
| --------------------- | ------------------------------------------ | ---------------------------------------------------- |
| `data.idx`            | ID interne de la station AQICN             | Identification fine des stations                     |
| `data.attributions`   | Crédits de la source locale                | Affichage légal dans un dashboard public             |
| `data.city.geo`       | Coordonnées GPS                            | Déjà fournies par OpenWeatherMap via `coord.lat/lon` |
| `data.city.url`       | URL de la page AQICN de la ville           | Lien dans un dashboard                               |
| `data.dominentpol`    | Polluant dominant ("pm25")                 | Alerte automatique sur le polluant principal         |
| `data.iaqi.co.v`      | Monoxyde de carbone                        | Analyse de pollution complète                        |
| `data.iaqi.so2.v`     | Dioxyde de soufre                          | Analyse de pollution industrielle                    |
| `data.iaqi.t.v`       | Température (mesurée par la station AQICN) | Comparaison croisée avec OpenWeatherMap              |
| `data.iaqi.p.v`       | Pression (mesurée par la station AQICN)    | Comparaison croisée avec OpenWeatherMap              |
| `data.iaqi.h.v`       | Humidité (mesurée par la station AQICN)    | Comparaison croisée avec OpenWeatherMap              |
| `data.time.*`         | Timestamps de la mesure                    | Non utilisé : Time Bucketing Airflow                 |
| `data.forecast.daily` | Prévisions J+1 et J+2                      | Modèle prédictif, comparaison prévision vs réel      |
| `data.debug.sync`     | Horodatage de synchronisation interne      | Diagnostic AQICN                                     |
| `status`              | Statut de la réponse ("ok")                | Vérifié dans le code, pas stocké en colonne          |

---

## Champs communs entre les deux APIs

Les deux APIs fournissent certaines mesures en commun. Nous avons choisi une source principale pour chaque champ afin d'éviter les doublons et les incohérences.

| Mesure          | OpenWeatherMap        | AQICN                        | Source retenue | Justification                                       |
| --------------- | --------------------- | ---------------------------- | -------------- | --------------------------------------------------- |
| Température     | `main.temp` (°C)      | `data.iaqi.t.v` (indice AQI) | OpenWeatherMap | Valeur en °C directement exploitable, pas un indice |
| Humidité        | `main.humidity` (%)   | `data.iaqi.h.v` (indice AQI) | OpenWeatherMap | Valeur en % directement exploitable                 |
| Pression        | `main.pressure` (hPa) | `data.iaqi.p.v` (indice AQI) | OpenWeatherMap | Valeur en hPa directement exploitable               |
| Coordonnées GPS | `coord.lat/lon`       | `data.city.geo`              | OpenWeatherMap | Précision identique, un seul choix suffit           |
| Nom de ville    | `name`                | `data.city.name`             | Aucun des deux | On utilise le fichier config comme source de vérité |
| Timestamp       | `dt` (Unix)           | `data.time.iso` (ISO 8601)   | Aucun des deux | On utilise le logical_date Airflow (Time Bucketing) |

**Point important :** AQICN fournit température, humidité et pression sous forme d'**indices AQI**, pas de valeurs absolues. C'est pourquoi OpenWeatherMap est la source retenue pour ces métriques — les valeurs sont directement en °C, % et hPa.

Les champs communs non retenus (température, humidité, pression AQICN) restent dans le JSON brut en Bronze. Ils pourront servir en V2 pour de la validation croisée : comparer la température OpenWeatherMap avec celle d'AQICN pour détecter des capteurs défaillants.

---

## Mapping Source → Data Warehouse

| Donnée DW   | Source         | Chemin JSON          | Transformation appliquée                     |
| ----------- | -------------- | -------------------- | -------------------------------------------- |
| NomVille    | Config         | `cities_config.json` | Aucune (source de vérité, pas l'API)         |
| CodePays    | OpenWeatherMap | `sys.country`        | Remplacé par 'ND' si absent                  |
| Latitude    | OpenWeatherMap | `coord.lat`          | NULL si absent                               |
| Longitude   | OpenWeatherMap | `coord.lon`          | NULL si absent                               |
| IDTemps     | Airflow        | `logical_date`       | Time Bucketing : `int(strftime("%Y%m%d%H"))` |
| Temperature | OpenWeatherMap | `main.temp`          | Cast DECIMAL, coerce si non numérique        |
| Humidite    | OpenWeatherMap | `main.humidity`      | Cast INT, CHECK 0-100 en SQL                 |
| Pression    | OpenWeatherMap | `main.pressure`      | Cast INT                                     |
| VitesseVent | OpenWeatherMap | `wind.speed`         | Cast DECIMAL                                 |
| AqiGlobal   | AQICN          | `data.aqi`           | Cast INT                                     |
| PM25        | AQICN          | `data.iaqi.pm25.v`   | Cast DECIMAL, NULL si clé absente            |
| PM10        | AQICN          | `data.iaqi.pm10.v`   | Cast DECIMAL, NULL si clé absente            |
| NO2         | AQICN          | `data.iaqi.no2.v`    | Cast DECIMAL, NULL si clé absente            |
| O3          | AQICN          | `data.iaqi.o3.v`     | Cast DECIMAL, NULL si clé absente            |
| MeteoStatus | Pipeline       | Calculé              | FAILED si toutes métriques météo NULL        |
| AirStatus   | Pipeline       | Calculé              | FAILED si toutes métriques air NULL          |

---

## Calcul du budget d'appels API

| Paramètre                       | Valeur                |
| ------------------------------- | --------------------- |
| Nombre de villes                | 11                    |
| Nombre d'APIs                   | 2                     |
| Fréquence                       | 1 fois par heure      |
| Appels par heure                | 11 × 2 = 22           |
| Appels par jour                 | 22 × 24 = 528         |
| Limite OpenWeatherMap (gratuit) | 1 000 appels/jour     |
| Marge restante                  | 472 appels/jour (47%) |

Notre consommation utilise 53% du quota gratuit. On pourrait monter à ~20 villes avant d'atteindre la limite.
