# Audit de la Source Open-Meteo - GoodAir Pipeline

## Contexte

Open-Meteo est la troisième source de données intégrée dans notre le pipeline pour la prochaine phase du projet GoodAir. Contrairement à OpenWeatherMap et AQICN qui fournissent des mesures issues de capteurs physiques en temps réel, Open-Meteo est un **modèle numérique météorologique**. Des super-ordinateurs résolent des équations physiques de l'atmosphère pour calculer des prévisions. C'est la même technologie qu'utilise Météo-France, mais exposée via une API gratuite et sans clé d'authentification.

C'est la différence majeure : Open-Meteo ne mesure pas ce qui se passe maintenant. **elle prédit ce qui va se passer dans les prochaines heures**. C'est précisément pour cette raison qu'elle a été intégrée dans la phase ML du projet pour fournir les variables météo futures nécessaires à la prédiction de l'AQI à horizon 6h.

---

## Caractéristiques de la Source

| Caractéristique      | Détail                                                                              |
| -------------------- | ----------------------------------------------------------------------------------- |
| URL                  | `https://api.open-meteo.com/v1/forecast`                                            |
| Format               | JSON structuré (tableaux parallèles)                                                |
| Authentification     | Aucune (API gratuite sans clé)                                                      |
| Plan                 | Gratuit. sans quota (usage raisonnable)                                             |
| Latence              | ~100ms par appel                                                                    |
| Type de donnée       | Prévisions numériques (modèle météo)                                                |
| Horizon de prévision | Configurable. nous utilisons 10 heures                                              |
| Timezone             | Configurable. nous utilisons `Europe/Paris`                                         |
| Historique           | Disponible via `archive-api.open-meteo.com` (utilisé pour l'entraînement du modèle) |

---

## Différence Fondamentale avec OWM et AQICN

| Aspect             | OpenWeatherMap / AQICN         | Open-Meteo                       |
| ------------------ | ------------------------------ | -------------------------------- |
| Nature             | Capteurs physiques terrain     | Modèle numérique                 |
| Type               | Mesure temps réel              | Prévision future                 |
| Disponibilité      | Dépend des capteurs locaux     | Toujours disponible              |
| Valeurs NULL       | Possibles (capteur en panne)   | Aucune (modèle calcule toujours) |
| Usage dans GoodAir | ETL horaire → Gold.FactMesures | ML -> Silver/features-ml/        |

---

## Questions Fondamentales

**Quelles sont les caractéristiques les plus essentielles de cette source ?**
Un JSON structuré avec deux objets : `hourly_units` (les unités de chaque variable) et `hourly` (les tableaux de valeurs parallèles indexés par `time`). Le format est simple et cohérent. aucun imbrication complexe comparé à OWM et AQICN.

**Comment les données sont-elles stockées dans le système source ?**
le modèle calcule les prévisions à la demande. L'API Forecast retourne les N prochaines heures depuis l'instant de l'appel. L'API Archive retourne l'historique reconstitué par le modèle pour n'importe quelle période passée.

**Quel est le niveau de consistance et la fréquence des erreurs ?**
Très élevé. Le modèle calcule toujours une valeur. il n'y a pas de valeur NULL liée à un capteur en panne. Les erreurs sont exclusivement des erreurs réseau ou de surcharge serveur (503). Dans notre pipeline. ces erreurs sont gérées par le mécanisme de retry Airflow (`retries=2`).

**Si le schéma change (Schema Drift). comment allons-nous gérer cela ?**
Pour le moment, on sauvegarde le JSON complet en Bronze sans filtrage. Le code de `feature_engineering.py` agit comme un data contract strict sur les clés attendues.

**À quelle fréquence les données sont extraites ?**
Une fois par heure. en même temps que OWM et AQICN. dans la même task `extract_bronze`.

---

## Payload Complet (exemple Paris)

```json
{
    "latitude": 48.86,
    "longitude": 2.3399997,
    "generationtime_ms": 0.085,
    "utc_offset_seconds": 7200,
    "timezone": "Europe/Paris",
    "timezone_abbreviation": "GMT+2",
    "elevation": 43.0,
    "hourly_units": {
        "time": "iso8601",
        "wind_direction_10m": "°",
        "cloud_cover": "%",
        "precipitation": "mm"
    },
    "hourly": {
        "time": [
            "2026-07-04T00:00",
            "2026-07-04T01:00",
            "2026-07-04T02:00",
            "2026-07-04T03:00",
            "2026-07-04T04:00",
            "2026-07-04T05:00"
        ],
        "wind_direction_10m": [336, 349, 336, 332, 321, 302],
        "cloud_cover": [0, 0, 0, 0, 0, 0],
        "precipitation": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    }
}
```

**Structure des tableaux `hourly` :** les tableaux `time`. `wind_direction_10m`. `cloud_cover` et `precipitation` sont parallèles et indexés ensemble. `hourly["time"][i]` correspond à `hourly["wind_direction_10m"][i]`.

---

## Champs Utilisés dans le Pipeline

| Chemin JSON                    | Variable Silver      | Usage                                |
| ------------------------------ | -------------------- | ------------------------------------ |
| `hourly.time[i]`               | `DateHeure`          | Horodatage de la prévision           |
| `hourly.wind_direction_10m[i]` | `wind_direction_10m` | Direction du vent en degrés (0-360°) |
| `hourly.cloud_cover[i]`        | `cloud_cover`        | Couverture nuageuse (0-100%)         |
| `hourly.precipitation[i]`      | `precipitation`      | Précipitations en mm                 |

---

## Champs Non Utilisés (mais conservés en Bronze)

| Chemin JSON                          | Pourquoi non utilisé                | Potentiel V2                   |
| ------------------------------------ | ----------------------------------- | ------------------------------ |
| `latitude` / `longitude`             | Déjà dans `cities_config.json`      | Vérification de cohérence      |
| `generationtime_ms`                  | Métadonnée interne du modèle        | Monitoring performance API     |
| `utc_offset_seconds`                 | On gère le timezone dans le code    | Audit timezone                 |
| `timezone` / `timezone_abbreviation` | Forcé à `Europe/Paris` à l'appel    | Contrôle                       |
| `elevation`                          | Altitude du point de calcul         | Corrélation altitude/pollution |
| `hourly_units`                       | Unités documentées. pas des données | Documentation automatique      |

---

## Mapping Source → Couche Silver

| Variable Silver      | Source     | Chemin JSON                    | Transformation appliquée                                        |
| -------------------- | ---------- | ------------------------------ | --------------------------------------------------------------- |
| `DateHeure`          | Open-Meteo | `hourly.time[i]`               | `pd.to_datetime(t)`  - naive datetime. déjà en heure Paris      |
| `NomVille`           | Config     | `cities_config.json`           | Injecté par le code. pas dans le JSON                           |
| `wind_direction_10m` | Open-Meteo | `hourly.wind_direction_10m[i]` | Cast int. variable circulaire -> sin/cos en feature engineering |
| `cloud_cover`        | Open-Meteo | `hourly.cloud_cover[i]`        | Cast int. 0-100%                                                |
| `precipitation`      | Open-Meteo | `hourly.precipitation[i]`      | Cast float. binarisé en 0/1 en feature engineering              |

---

## Point Fort de la Source

Open-Meteo est la seule source du pipeline qui ne dépend pas de capteurs physiques. Elle est donc **toujours disponible** et **sans valeurs NULL**. C'est ce qui en fait une source complémentaire idéale pour le ML : là où GoodAir a des trous temporels (PC en veille). Open-Meteo Archive nous a fourni un historique complet et cohérent pour l'entraînement du modèle.

L'API Forecast étant gratuite et sans quota documenté. elle ne présente aucun risque de dépassement de limite.

---

## Points de Vigilance

**Timezone :** Les timestamps retournés par l'API sont en heure locale (`Europe/Paris`) grâce au paramètre `timezone=Europe/Paris`. Ils doivent être traités comme des `naive datetime` sans conversion UTC pour éviter tout décalage. Ce point a causé un bug en production (voir historique des corrections).

**Point important sur le naive datetime :**
Un `naive datetime` c'est une date et heure qui ne sait pas dans quel fuseau horaire elle se trouve.
Exemple concret:

```bash
le naive datetime   : 2026-07-05 18:00:00
                   → "il est 18h" mais on ne sait pas si c'est Paris. Londres ou New York

le aware datetime   : 2026-07-05 18:00:00+02:00
                   → "il est 18h à Paris (UTC+2)"
```

Dans notre cas. Open-Meteo retourne "2026-07-05T18:00" sans indication de fuseau. C'est donc un naive datetime. On sait qu'il est en heure Paris car on a passé timezone=Europe/Paris dans l'appel API. mais le timestamp lui-même ne le dit pas explicitement.
On le garde naïf volontairement pour éviter les conversions automatiques de Python qui pourraient décaler les heures

**forecast_hours vs heure d'appel :** Open-Meteo calcule les `forecast_hours` depuis l'heure UTC de l'appel API. pas depuis l'heure Paris. Avec un décalage UTC+2. J'avais documenté ce problème [ici](/docs/CHANGEMENT_FUSEAU_HORAIRE.md). les 6 premières heures retournées peuvent ne pas correspondre aux 6 heures futures souhaitées. Solution : utiliser `forecast_hours=10` et sélectionner dynamiquement les 6 premiers créneaux disponibles après le `run_date`.

**Schema Drift :** L'API est stable mais Open-Meteo peut ajouter ou modifier des variables. La clé de robustesse est la sauvegarde intégrale du JSON en Bronze. Si une variable disparaît. `feature_engineering.py` lèvera une erreur explicite via le data contract.

**Erreurs 503 :** Des surcharges serveur ponctuelles peuvent survenir. Elles sont gérées par le principe **Fail Fast**,  on laisse la task échouer et Airflow retente automatiquement (`retries=2`).

---

## Budget d'Appels API

| Paramètre                   | Valeur                   |
| --------------------------- | ------------------------ |
| Nombre de villes            | 11                       |
| Fréquence                   | 1 fois par heure         |
| Appels par heure            | 11                       |
| Appels par jour             | 11 × 24 = 264            |
| Limite Open-Meteo (gratuit) | Aucune limite documentée |
| Authentification requise    | Non                      |
| Coût                        | 0€                       |

Open-Meteo précise dans sa documentation que l'API est gratuite pour un usage raisonnable. 264 appels par jour est très largement dans cette limite.
