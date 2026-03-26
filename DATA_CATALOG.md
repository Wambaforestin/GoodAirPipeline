# Data Catalog — GoodAir Data Warehouse

Ce document décrit l'ensemble des tables et colonnes du Data Warehouse GoodAir.
Une version requêtable est également disponible dans `Ref.DataCatalog` sur SQL Server.

## Sources de données

| Source | Type | Endpoint | Fréquence |
|--------|------|----------|-----------|
| OpenWeatherMap | API REST | `/data/2.5/weather` | Horaire |
| AQICN | API REST | `/feed/{city}/` | Horaire |
| Pipeline GoodAir | Calculé | — | Horaire |

## Schéma Gold — Data Warehouse

### Gold.DimLieux

Référentiel des villes surveillées par GoodAir.

| Colonne | Type | Source | Chemin JSON | Description | Nullable |
|---------|------|--------|-------------|-------------|----------|
| IDLieu | INT IDENTITY | Système | — | Clé primaire auto-générée | Non |
| NomVille | NVARCHAR(100) | OpenWeatherMap | `name` | Nom de la ville | Non |
| CodePays | CHAR(2) | OpenWeatherMap | `sys.country` | Code ISO du pays | Oui |
| Latitude | DECIMAL(9,6) | OpenWeatherMap | `coord.lat` | Coordonnée GPS Nord/Sud | Oui |
| Longitude | DECIMAL(9,6) | OpenWeatherMap | `coord.lon` | Coordonnée GPS Est/Ouest | Oui |

### Gold.DimTemps

Calendrier horaire pour l'historisation des mesures.

| Colonne | Type | Source | Description | Nullable |
|---------|------|--------|-------------|----------|
| IDTemps | BIGINT | Système | Clé au format YYYYMMDDHH (ex: 2026032514) | Non |
| DateHeure | DATETIME | Système | Horodatage complet | Non |
| Annee | INT | Système | Année (ex: 2026) | Oui |
| Mois | INT | Système | Mois (1-12) | Oui |
| Jour | INT | Système | Jour du mois (1-31) | Oui |
| Heure | INT | Système | Heure UTC (0-23) | Oui |

### Gold.FactMesures

Table de faits centrale. Une ligne = une ville × une heure.

| Colonne | Type | Source | Chemin JSON | Description | Nullable |
|---------|------|--------|-------------|-------------|----------|
| IDLieu | INT | Système | — | FK vers DimLieux | Non |
| IDTemps | BIGINT | Système | — | FK vers DimTemps | Non |
| Temperature | DECIMAL(5,2) | OpenWeatherMap | `main.temp` | Température en °C | Oui |
| Humidite | INT | OpenWeatherMap | `main.humidity` | Humidité en % (0-100) | Oui |
| Pression | INT | OpenWeatherMap | `main.pressure` | Pression atmosphérique en hPa | Oui |
| VitesseVent | DECIMAL(5,2) | OpenWeatherMap | `wind.speed` | Vitesse du vent en m/s | Oui |
| AqiGlobal | INT | AQICN | `data.aqi` | Indice global de qualité de l'air | Oui |
| PM25 | DECIMAL(6,2) | AQICN | `data.iaqi.pm25.v` | Particules fines PM2.5 | Oui |
| PM10 | DECIMAL(6,2) | AQICN | `data.iaqi.pm10.v` | Particules PM10 | Oui |
| NO2 | DECIMAL(6,2) | AQICN | `data.iaqi.no2.v` | Dioxyde d'azote | Oui |
| O3 | DECIMAL(6,2) | AQICN | `data.iaqi.o3.v` | Ozone troposphérique | Oui |
| MeteoStatus | VARCHAR(20) | Pipeline | — | OK si au moins une donnée météo reçue, FAILED sinon | Non |
| AirStatus | VARCHAR(20) | Pipeline | — | OK si au moins une donnée air reçue, FAILED sinon | Non |
| DateInsertion | DATETIME2 | Système | — | Date de première insertion dans Gold | Non |
| DateModification | DATETIME2 | Système | — | Date de dernière mise à jour (MERGE) | Non |
| IDBatch | VARCHAR(100) | Airflow | — | Run ID Airflow pour traçabilité et rollback | Non |

## Schéma Ref — Référentiel

### Ref.Pays

| Colonne | Type | Description | Nullable |
|---------|------|-------------|----------|
| CodePays | CHAR(2) | Code ISO 3166-1 (ex: FR) | Non |
| NomPays | NVARCHAR(100) | Nom complet (ex: France) | Non |

### Ref.SeuilsOMS

| Colonne | Type | Description | Nullable |
|---------|------|-------------|----------|
| IDSeuil | INT IDENTITY | Clé primaire | Non |
| Polluant | VARCHAR(20) | PM2.5, PM10, NO2, O3 | Non |
| PeriodeReference | VARCHAR(50) | Période de mesure (Moyenne 24h, 8h) | Non |
| SeuilLimite | DECIMAL(6,2) | Valeur seuil en µg/m³ | Non |
| UniteMesure | VARCHAR(20) | Unité (µg/m³) | Non |
| NiveauDanger | NVARCHAR(50) | Limite OMS ou Danger | Non |
| Description | NVARCHAR(255) | Impact sanitaire | Oui |

## Schéma Staging — Tables temporaires

Tables vidées et rechargées à chaque run du pipeline (TRUNCATE + INSERT).

### Staging.DimLieux_Temp / Staging.DimTemps_Temp / Staging.FactMesures_Temp

Miroir des tables Gold sans index ni contraintes. Servent de zone d'atterrissage avant le MERGE vers Gold.

## Règles de qualité

| Règle | Description |
|-------|-------------|
| Ligne morte | Rejetée si TOUTES les métriques (météo + air) sont NULL |
| Clés manquantes | Rejetée si NomVille ou IDTemps est NULL |
| CodePays manquant | Remplacé par 'ND' |
| Coordonnées manquantes | Gardées NULL (pas de rejet) |
| Métriques partielles | Gardées NULL (AVG SQL les ignore) |
| Dédoublonnage | Sur (NomVille, IDTemps), dernière occurrence conservée |