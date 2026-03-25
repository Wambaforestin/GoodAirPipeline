# GoodAir Pipeline

Pipeline ETL horaire pour le laboratoire GoodAir (TotalGreen).  
Collecte des données météorologiques (OpenWeatherMap) et de qualité de l'air (AQICN) pour les principales villes de France.

## Architecture

- **Orchestration** : Apache Airflow 3 (LocalExecutor)
- **Data Lake** : MinIO (couches Bronze / Silver)
- **Data Warehouse** : SQL Server 2022 (star schema — Gold)
- **Langage** : Python (pandas, pyarrow, SQLAlchemy, pyodbc)
- **Infra** : Docker Compose

## Structure du Projet

```
GoodAirPipeline/
├── dags/                  # DAGs Airflow
├── src/                   # Code source modulaire
│   ├── extract/           # Appels API → Bronze
│   ├── transform/         # Nettoyage & DQ → Silver
│   ├── load/              # Insertion SQL → Gold
│   ├── utils/             # Fonctions utilitaires
│   └── sql/               # Scripts .sql (MERGE, DDL)
├── tests/                 # Tests unitaires (Pytest)
├── config/
│   ├── cities_config.json
│   └── pipeline_config.yaml
├── .env.example           # Template des variables d'environnement
├── docker-compose.yml
├── Dockerfile             # Image Airflow custom (ODBC + dépendances)
├── pyproject.toml         # Dépendances (uv)
└── README.md
```

## Diagramme d'architecture de l'MVP

![Architecture MVP Good Air](images/ArchirectueMVPGoodAir.png)

## Schéma en étoile

![Schéma en étoile](images/SchemaEtoileGoodAir.png)

## Diagramme de Sequence du pipeline

![Diagramme de Sequence du pipeline](images/DiagrammeSequencePGoodAir.png)

## Architecture d'Airflow utilisée

![Architecture d'airflow](images/ArchitectureAiflow.png)

## Prérequis

- Docker Desktop installé et lancé (allouer au moins 4 Go de RAM)
- Git Bash (ou terminal VS Code)
- uv (gestionnaire de paquets Python)

## Démarrage Rapide

```bash
# 1. Copier et configurer les variables d'environnement
cp .env.example .env
# Remplir les clés API et mots de passe dans .env

# 2. Initialiser Airflow (attendre le message de fin)
docker compose up airflow-init

# 3. Lancer tous les services en arrière-plan
docker compose up -d

# 4. Vérifier que tout est healthy
docker compose ps
```

## Accès aux services

| Service | URL | Identifiants |
|---------|-----|-------------|
| Airflow | http://localhost:8081 | airflow / airflow |
| MinIO Console | http://localhost:9001 | admin / (voir .env) |
| SQL Server | localhost:1433 | sa / (voir .env) |

> Le port d'Airflow est configuré sur 8081 pour éviter les conflits avec d'autres services locaux.

## Maintenance

```bash
# Arrêter les services
docker compose down

# Arrêter et supprimer toutes les données (reset complet)
docker compose down --volumes --remove-orphans
```

## Sources de Données

| Source | API | Données |
|--------|-----|---------|
| OpenWeatherMap | `/data/2.5/weather` | Température, Humidité, Pression, Vent |
| AQICN | `/feed/{city}/` | AQI, PM2.5, PM10, NO2, O3 |

## Équipe

Projet MSPR — EPSI (Bloc 3 RNCP36921)
