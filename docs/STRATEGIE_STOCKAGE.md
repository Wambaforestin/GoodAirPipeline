# Stratégie de Stockage: Data Lake MinIO (S3-compatible)

Ce document décrit comment les données sont organisées, partitionnées et sécurisées dans MinIO, notre Data Lake S3-compatible. Chaque décision est justifiée par notre cas d'utilisation : un pipeline horaire collectant des données météo et qualité de l'air pour 11 villes françaises.

---

## Architecture par zones

Le Data Lake est segmenté en deux zones, matérialisées par deux buckets MinIO distincts. Chaque zone a un rôle précis et un format de données adapté.

```
MinIO
├── bronze/          → Données brutes (JSON)
└── silver/          → Données nettoyées (Parquet)
```

### Zone Bronze (bucket `bronze`)

**Rôle :** figer l'histoire. Les réponses API sont stockées telles quelles, sans aucune transformation. C'est la source de vérité absolue du Data Lake.

**Format :** JSON brut. On conserve exactement ce que l'API renvoie, y compris les champs qu'on n'utilise pas aujourd'hui (forecast, weather description, visibility). Ces champs pourront être exploités dans les phases futures sans avoir à re-collecter les données.

**Règle d'écriture :** overwrite (écrasement). Si le pipeline est relancé pour la même heure, le fichier JSON est écrasé. On ne crée pas de doublons. C'est ce qui garantit l'idempotence au niveau du Data Lake.

**Qui y accède :** uniquement le pipeline (écriture par Extract, lecture par Transform). Aucun utilisateur final n'accède directement au Bronze.

### Zone Silver (bucket `silver`)

**Rôle :** structurer, nettoyer et consolider. Les données des deux APIs sont fusionnées, typées, nettoyées et stockées en format optimisé pour la lecture.

**Format :** Apache Parquet. Ce format orienté colonne offre trois avantages par rapport au JSON ou au CSV :

- Compression native (un Parquet de 10 villes fait ~5 Ko contre ~20 Ko en JSON)
- Préservation des types (les DECIMAL, INT, BIGINT sont conservés, pas convertis en chaînes)
- Lecture sélective (on peut lire uniquement les colonnes nécessaires sans charger tout le fichier)

**Sous-zones :**

- `silver/mesures/` — les données validées, prêtes pour le chargement en SQL Server
- `silver/rejects/` — les lignes rejetées (lignes mortes, clés manquantes), archivées pour analyse

**Qui y accède :** le pipeline (écriture par Transform, lecture par Load). En V2, des data scientists pourraient lire directement le Silver pour des analyses exploratoires sans passer par SQL Server.

---

## Structure de dossiers et clé de partition

### Le partitionnement par date

Chaque fichier est stocké dans une hiérarchie de dossiers basée sur la date et l'heure du run :

```
bronze/
├── openweathermap/
│   └── year=2026/
│       └── month=03/
│           └── day=30/
│               └── hour=15/
│                   ├── Paris.json
│                   ├── Lyon.json
│                   ├── Lille.json
│                   ├── Bordeaux.json
│                   ├── Marseille.json
│                   ├── Toulouse.json
│                   ├── Nantes.json
│                   ├── Strasbourg.json
│                   ├── Nice.json
│                   ├── Rennes.json
│                   └── Franconville.json
├── aqicn/
│   └── year=2026/
│       └── month=03/
│           └── day=30/
│               └── hour=15/
│                   ├── Paris.json
│                   └── ...

silver/
├── mesures/
│   └── year=2026/
│       └── month=03/
│           └── day=30/
│               └── hour=15/
│                   └── mesures.parquet
└── rejects/
    └── year=2026/
        └── month=03/
            └── day=30/
                └── hour=15/
                    └── rejects.parquet
```

### Pourquoi cette clé de partition

La clé de partition `year/month/day/hour` est choisie parce qu'elle correspond exactement au grain de notre pipeline : **1 exécution = 1 heure**. C'est le niveau de granularité le plus fin dont on a besoin.

**Avantages de cette clé :**

1. **Accès ciblé** — pour relire les données du 15 mars à 14h, on accède directement à `year=2026/month=03/day=15/hour=14/` sans scanner les autres dossiers. Sur un Data Lake qui accumule des mois de données, ça fait une différence significative.

2. **Idempotence naturelle** — le chemin est déterministe. Pour une date donnée, le chemin est toujours le même. Écraser le contenu du dossier de 14h ne crée jamais de doublons.

3. **Purge sélective** — si on veut supprimer les données de janvier 2026, on supprime `year=2026/month=01/` sans toucher au reste. Pas besoin de scanner chaque fichier.

4. **Compatibilité Hive** — la convention `key=value` (year=2026, month=03) est le standard de partitionnement Hive/Spark. Si on migre vers un moteur de requête (Trino, Spark, Athena), les partitions sont reconnues automatiquement.

### Pourquoi pas d'autres clés de partition

| Alternative                        | Pourquoi pas                                                                                                                                                                     |
| ---------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Par ville (`city=Paris/`)          | Nos requêtes filtrent toujours par date d'abord, pas par ville. Le partitionnement par ville obligerait à scanner tous les dossiers de villes pour reconstituer une heure donnée |
| Par source API (`source=owm/`)     | C'est déjà le premier niveau de notre structure Bronze (`openweathermap/`, `aqicn/`). C'est un préfixe, pas une partition au sens Hive                                           |
| Par date seule (`day=2026-03-30/`) | Trop grossier. Avec 24 runs par jour × 11 villes × 2 APIs, un seul dossier par jour contiendrait 528 fichiers. Le partitionnement horaire les répartit en groupes de 11          |

### Le code qui génère les chemins

La fonction `get_partition_path` dans `connections.py` produit le chemin de manière déterministe à partir de la date du run :

```python
def get_partition_path(api_name, run_date):
    return (
        f"{api_name}/"
        f"year={run_date.strftime('%Y')}/"
        f"month={run_date.strftime('%m')}/"
        f"day={run_date.strftime('%d')}/"
        f"hour={run_date.strftime('%H')}/"
    )
```

Exemple : pour un run le 30 mars 2026 à 15h, l'appel `get_partition_path("openweathermap", run_date)` produit :

```
openweathermap/year=2026/month=03/day=30/hour=15/
```

Cette fonction est utilisée partout : dans l'Extract (écriture Bronze), le Transform (lecture Bronze + écriture Silver), et le Load (lecture Silver).

---

## Nommage des fichiers

### Bronze

Chaque fichier JSON est nommé par la ville : `Paris.json`, `Lyon.json`, etc. Ce nom vient du fichier `cities_config.json`, pas de l'API.

**Pourquoi le nom de ville comme nom de fichier :** c'est le deuxième niveau de granularité après l'heure. Dans le dossier `hour=15/`, on a un fichier par ville. Pour relire les données de Paris à 15h, le chemin complet est :

```
bronze/openweathermap/year=2026/month=03/day=30/hour=15/Paris.json
```

C'est lisible par un humain et adressable directement sans listing du dossier.

### Silver

Le Parquet est nommé `mesures.parquet` (ou `rejects.parquet` pour les rejets). Il n'y a qu'un seul fichier par heure car les données des 11 villes sont fusionnées en un seul DataFrame.

**Pourquoi un seul fichier et pas un par ville :** à notre volume (11 lignes par heure), créer 11 fichiers Parquet de 1 ligne chacun serait inefficace. Le format Parquet est optimisé pour des batches, pas pour des fichiers unitaires. Un seul fichier de 11 lignes est plus performant à lire et à écrire.

---

## Gestion de la taille des fichiers

### Volume actuel

Nos fichiers sont très petits :

- Un JSON Bronze : ~1 Ko
- Un Parquet Silver (11 villes) : ~5 Ko
- Total mensuel estimé : ~18 Mo (Bronze + Silver)

### Projection à 1 an

Avec 11 villes, 2 APIs, 24h/jour, 365 jours :

- Bronze : 11 villes × 2 APIs × 1 Ko × 24h × 365j = **~188 Mo/an**
- Silver : 5 Ko × 24h × 365j = **~43 Mo/an**
- Total : **~230 Mo/an**

L'espace disque n'est pas un problème à cette échelle.

### Quand la taille deviendrait un sujet

Si on passait à 500 villes avec des données toutes les 15 minutes (au lieu d'1 heure), les volumes augmenteraient significativement. Les stratégies à mettre en place en V2 seraient :

- **Compaction** : fusionner les petits fichiers Parquet d'une journée en un seul fichier quotidien pour réduire le nombre d'objets
- **Rétention** : définir une politique de suppression automatique du Bronze après N mois (les données sont déjà dans Gold)
- **Lifecycle policy** : MinIO supporte les politiques de cycle de vie pour archiver ou supprimer automatiquement les objets anciens

---

## Sécurité de l'accès

### Authentification

L'accès à MinIO est protégé par des credentials définis dans le `.env` :

```
MINIO_ROOT_USER=admin
MINIO_ROOT_PASSWORD=GoodAir***
```

Ces credentials sont injectés dans le docker-compose et utilisés par le client Python :

```python
client = Minio(
    endpoint=os.getenv("MINIO_ENDPOINT"),
    access_key=os.getenv("MINIO_ROOT_USER"),
    secret_key=os.getenv("MINIO_ROOT_PASSWORD"),
    secure=False
)
```

### Réseau

MinIO n'est accessible que via le réseau Docker interne (port 9000 pour l'API S3) et via `localhost` pour la console web (port 9001). Il n'est pas exposé sur Internet.

### Ce qui est prévu en V2

Pour une mise en production réelle, on ajouterait :

- **Bucket policies** : restreindre l'accès en lecture seule sur Bronze pour les data scientists, écriture uniquement pour le pipeline
- **Utilisateurs IAM MinIO** : créer des comptes séparés pour le pipeline (read/write) et les analystes (read only)
- **Chiffrement au repos** : MinIO supporte le chiffrement SSE-S3 pour protéger les données sur disque
- **HTTPS** : passer `secure=True` dans le client Python avec un certificat TLS

---

## Résumé des décisions

| Décision                | Choix                            | Justification                                       |
| ----------------------- | -------------------------------- | --------------------------------------------------- |
| Nombre de buckets       | 2 (bronze, silver)               | Séparation claire des zones par niveau de qualité   |
| Format Bronze           | JSON brut                        | Conservation exacte de la réponse API               |
| Format Silver           | Parquet                          | Compression, typage, lecture sélective              |
| Clé de partition        | year/month/day/hour              | Correspond au grain du pipeline (1 run = 1 heure)   |
| Convention de nommage   | Hive style (key=value)           | Compatible Spark/Trino/Athena pour migration future |
| Nommage fichiers Bronze | {Ville}.json                     | Lisible et adressable directement                   |
| Nommage fichiers Silver | mesures.parquet                  | Un seul fichier par heure (volume faible)           |
| Stratégie d'écriture    | Overwrite                        | Idempotence garantie                                |
| Rejets                  | silver/rejects/                  | Archivage pour analyse, pas de suppression          |
| Sécurité                | Credentials .env + réseau Docker | Suffisant pour le MVP local                         |
