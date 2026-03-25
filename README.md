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

![Architecture MVP Good Air](images/ArchitectueMVPGoodAir.png)

## Schéma en étoile

![Schéma en étoile](images/SchemaEnEtoileGoodAir.png)

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

## Génération de la clé Fernet (sécurité Airflow)

Airflow nécessite une clé Fernet pour chiffrer les connexions et variables. Si la variable `AIRFLOW_FERNET_KEY` n'est pas renseignée dans votre `.env`, vous aurez une erreur du type :

```
Invalid auth token: Signature verification failed. C'est la FERNET_KEY qui est vide dans le docker-compose. Le scheduler n'arrive pas à s'authentifier auprès de l'API server.
```

Pour générer une clé Fernet, exécutez dans Git Bash :

```bash
docker compose exec airflow-apiserver python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Copiez la clé générée, puis ajoutez-la dans votre `.env` :

```
AIRFLOW_FERNET_KEY=la_clé_générée_ici
```

> Note : Dans ce projet, je n'utilise pas la version complet de l'image officielle d'Airflow car cela ajourte beaucoup de dépendances inutiles (celery, redis, etc.) qui alourdissent le build et ne sont pas nécessaires pour un MVP avec LocalExecutor. Certains clés doivent etre générées manuellement pour éviter les erreurs d'authentification entre les composants (scheduler, webserver, API server).

## Sécurité Airflow : clés partagées obligatoires

Airflow 3 utilise des secrets partagés pour sécuriser la communication entre ses services Docker (scheduler, API server, etc.). Deux variables **doivent** être identiques dans le `.env` :

- `AIRFLOW__CORE__FERNET_KEY` :
  - Sert à chiffrer les données sensibles (mots de passe, variables) dans la base PostgreSQL.
  - Si la clé est vide (`''`), chaque conteneur Airflow en génère une différente au démarrage → les services ne peuvent pas déchiffrer les données des autres.
  - **Solution :** générez une clé Fernet et renseignez-la dans le `.env` pour tous les services.

- `AIRFLOW__API_AUTH__JWT_SECRET` :
  - Depuis Airflow 3, le scheduler ne pilote plus les tâches en écrivant directement en base, mais via des appels HTTP REST à l’API server.
  - Ces appels sont authentifiés par des tokens JWT signés avec ce secret.
  - Si le secret n’est pas fixé, chaque service en génère un différent → échec de la validation des tokens (`Invalid auth token: Signature verification failed`).
  - **Solution :** définissez une valeur fixe et identique dans le `.env` pour tous les services.

> Ces deux variables règlent le même type de problème : des services Docker séparés qui doivent partager un secret identique pour communiquer et chiffrer/déchiffrer les données.

**Référence :** [Bug connu Airflow 3.x sur GitHub](https://github.com/apache/airflow/issues/37500)

## Équipe

Projet MSPR — EPSI (Bloc 3 RNCP36921)
