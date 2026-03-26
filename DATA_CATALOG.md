# Data Catalog — GoodAir Data Warehouse

## Vue d'ensemble

Le Data Warehouse GoodAirDW collecte des données météorologiques et de qualité de l'air pour les principales villes de France. Les données sont alimentées toutes les heures par un pipeline ETL orchestré par Apache Airflow.

**Sources :**
- OpenWeatherMap (météo) : température, humidité, pression, vent
- AQICN (qualité de l'air) : AQI, PM2.5, PM10, NO2, O3

**Schémas :**
- `Gold` : tables finales du star schema (dimensions + faits)
- `Ref` : données de référence statiques (pays, seuils OMS)
- `Staging` : tables temporaires pour le chargement (vidées à chaque run)

---

## Gold.DimLieux

Référentiel des villes surveillées par GoodAir.

| Colonne | Type | Source | Chemin JSON | Description | Nullable |
|---------|------|--------|-------------|-------------|----------|
| IDLieu | INT IDENTITY | Système | - | Clé primaire auto-incrémentée | Non |
| NomVille | NVARCHAR(100) | OpenWeatherMap | `name` | Nom de la ville | Non |
| CodePays | CHAR(2) | OpenWeatherMap | `sys.country` | Code ISO du pays. 'ND' si absent | Oui |
| Latitude | DECIMAL(9,6) | OpenWeatherMap | `coord.lat` | Latitude GPS | Oui |
| Longitude | DECIMAL(9,6) | OpenWeatherMap | `coord.lon` | Longitude GPS | Oui |

---

## Gold.DimTemps

Calendrier horaire pour l'historisation des mesures.

| Colonne | Type | Source | Description | Nullable |
|---------|------|--------|-------------|----------|
| IDTemps | BIGINT | Pipeline | Clé temporelle YYYYMMDDHH (Time Bucketing) | Non |
| DateHeure | DATETIME | Pipeline | Horodatage complet | Non |
| Annee | INT | Calculé | Année (ex: 2026) | Oui |
| Mois | INT | Calculé | Mois 1-12 | Oui |
| Jour | INT | Calculé | Jour 1-31 | Oui |
| Heure | INT | Calculé | Heure 0-23 | Oui |

---

## Gold.FactMesures

Table de faits centrale. Chaque ligne = 1 ville × 1 heure.

| Colonne | Type | Source | Chemin JSON | Description | Nullable |
|---------|------|--------|-------------|-------------|----------|
| IDLieu | INT | Système | FK DimLieux | Clé étrangère vers DimLieux | Non |
| IDTemps | BIGINT | Système | FK DimTemps | Clé étrangère vers DimTemps | Non |
| Temperature | DECIMAL(5,2) | OpenWeatherMap | `main.temp` | Température en °C | Oui |
| Humidite | INT | OpenWeatherMap | `main.humidity` | Humidité relative (0-100%) | Oui |
| Pression | INT | OpenWeatherMap | `main.pressure` | Pression atmosphérique (hPa) | Oui |
| VitesseVent | DECIMAL(5,2) | OpenWeatherMap | `wind.speed` | Vitesse du vent (m/s) | Oui |
| AqiGlobal | INT | AQICN | `data.aqi` | Indice global qualité de l'air | Oui |
| PM25 | DECIMAL(6,2) | AQICN | `data.iaqi.pm25.v` | Particules fines PM2.5 | Oui |
| PM10 | DECIMAL(6,2) | AQICN | `data.iaqi.pm10.v` | Particules PM10 | Oui |
| NO2 | DECIMAL(6,2) | AQICN | `data.iaqi.no2.v` | Dioxyde d'azote | Oui |
| O3 | DECIMAL(6,2) | AQICN | `data.iaqi.o3.v` | Ozone troposphérique | Oui |
| MeteoStatus | VARCHAR(20) | Pipeline | Calculé | OK si au moins une métrique météo reçue, FAILED sinon | Non |
| AirStatus | VARCHAR(20) | Pipeline | Calculé | OK si au moins une métrique air reçue, FAILED sinon | Non |
| DateInsertion | DATETIME2 | Pipeline | GETDATE() | Date de première insertion | Non |
| DateModification | DATETIME2 | Pipeline | GETDATE() | Date de dernière mise à jour | Non |
| IDBatch | VARCHAR(100) | Airflow | run_id | Identifiant du run pour lignage et rollback | Non |

**Clé primaire composite :** (IDLieu, IDTemps)

**Grain :** 1 ligne = 1 ville × 1 heure

---

## Ref.Pays

Référentiel des pays (codes ISO).

| Colonne | Type | Description | Nullable |
|---------|------|-------------|----------|
| CodePays | CHAR(2) | Code ISO 3166-1 alpha-2 (PK) | Non |
| NomPays | NVARCHAR(100) | Nom complet du pays | Non |

---

## Ref.SeuilsOMS

Seuils de pollution définis par l'Organisation Mondiale de la Santé.

| Colonne | Type | Description | Nullable |
|---------|------|-------------|----------|
| IDSeuil | INT IDENTITY | Clé primaire | Non |
| Polluant | VARCHAR(20) | Nom du polluant (PM2.5, PM10, NO2, O3) | Non |
| PeriodeReference | VARCHAR(50) | Période de mesure OMS (ex: Moyenne 24h) | Non |
| SeuilLimite | DECIMAL(6,2) | Valeur seuil | Non |
| UniteMesure | VARCHAR(20) | Unité (µg/m³) | Non |
| NiveauDanger | NVARCHAR(50) | Niveau de dangerosité | Non |
| Description | NVARCHAR(255) | Description de l'impact sanitaire | Oui |

---

## Règles de gestion des NULL

| Scénario | Action | Justification |
|----------|--------|---------------|
| Ville ou heure manquante | Rejet | Clés logiques obligatoires |
| CodePays manquant | Remplacé par 'ND' | La ville suffit pour l'identification |
| Coordonnées GPS manquantes | NULL maintenu | Les mesures restent exploitables |
| Une métrique météo manquante | NULL maintenu | Les autres métriques sont valides |
| Une métrique air manquante | NULL maintenu | Toutes les stations ne mesurent pas tout |
| Toutes les métriques NULL | Rejet (ligne morte) | Aucune valeur analytique |