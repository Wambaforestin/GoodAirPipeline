# Benchmark des Solutions Techniques — GoodAir Pipeline

Ce document présente les comparatifs réalisés pour chaque composant technique du projet. Chaque choix est justifié par rapport aux contraintes du cahier des charges : MVP, infrastructure locale, budget zéro, 11 villes, fréquence horaire, données accessibles aux chercheurs.

---

## 1. Orchestrateur

| Critère                     | Apache Airflow 3                         | Prefect                             | Dagster               | Cron + Scripts   |
| --------------------------- | ---------------------------------------- | ----------------------------------- | --------------------- | ---------------- |
| Interface web               | Oui (DAGs, logs, retries visuels)        | Oui                                 | Oui                   | Non              |
| Gestion des retries         | Natif (configurable par task)            | Natif                               | Natif                 | Manuel (à coder) |
| Scheduling horaire          | Natif                                    | Natif                               | Natif                 | Natif            |
| Injection de logical_date   | Natif (Time Bucketing)                   | Possible mais moins standard        | Possible              | Non              |
| Communauté et documentation | Très large, standard industrie           | Plus récent, communauté plus petite | Plus récent           | Universel        |
| Déploiement Docker          | Image officielle maintenue               | Image officielle                    | Image officielle      | Pas applicable   |
| Providers SQL Server        | apache-airflow-providers-microsoft-mssql | Via connecteur                      | Via connecteur        | Non              |
| Coût                        | Gratuit (open source)                    | Gratuit (open source)               | Gratuit (open source) | Gratuit          |

**Choix : Airflow 3** — standard de l'industrie pour l'orchestration de pipelines data. La majorité des offres d'emploi Data Engineer mentionnent Airflow. L'injection du logical_date est native et parfaitement adaptée au Time Bucketing. L'interface web permet au jury de voir les runs, les logs et les retries sans accéder au code.

---

## 2. Data Lake (Stockage objet S3-compatible)

| Critère                      | MinIO                     | Amazon S3           | Azure Blob Storage   | Stockage local (dossiers) |
| ---------------------------- | ------------------------- | ------------------- | -------------------- | ------------------------- |
| S3-compatible                | Oui (100%)                | Natif               | Non (API différente) | Non                       |
| Tourne en local (Docker)     | Oui                       | Non (cloud)         | Non (cloud)          | Oui                       |
| Console web d'administration | Oui (port 9001)           | Oui (AWS Console)   | Oui (Azure Portal)   | Non                       |
| Coût                         | Gratuit                   | Payant              | Payant               | Gratuit                   |
| Migration cloud future       | Transparent (même API S3) | -                   | Changement de SDK    | Refonte complète          |
| Partitionnement Hive style   | Supporté                  | Supporté            | Supporté             | Manuel                    |
| RGPD (données en France)     | Oui (machine locale)      | Dépend de la région | Dépend de la région  | Oui                       |

**Choix : MinIO** — seule solution qui combine S3-compatible, gratuit et local. Si demain le projet migre vers AWS, on change l'endpoint dans le .env et le code Python reste identique (même SDK boto3/minio). Le stockage local garantit la conformité RGPD sans dépendre d'un fournisseur cloud.

---

## 3. Data Warehouse (Base relationnelle analytique)

| Critère                               | SQL Server 2022                  | PostgreSQL               | MySQL                      | Snowflake              |
| ------------------------------------- | -------------------------------- | ------------------------ | -------------------------- | ---------------------- |
| MERGE (UPSERT natif)                  | Oui (syntaxe MERGE)              | Oui (INSERT ON CONFLICT) | Non natif                  | Oui                    |
| Star schema                           | Supporté                         | Supporté                 | Supporté                   | Optimisé               |
| Schémas logiques (Gold, Ref, Staging) | Oui (CREATE SCHEMA)              | Oui                      | Non (pas de vrais schémas) | Oui                    |
| Rôles et permissions par schéma       | Oui (GRANT/DENY par schéma)      | Oui                      | Limité                     | Oui                    |
| MUST_CHANGE mot de passe              | Oui                              | Non                      | Non                        | Non                    |
| Connexion Python (pyodbc)             | Natif + fast_executemany         | psycopg2                 | mysql-connector            | SDK Snowflake          |
| Conteneur Docker                      | Oui (image officielle Microsoft) | Oui                      | Oui                        | Non (cloud uniquement) |
| Coût                                  | Gratuit (Developer Edition)      | Gratuit                  | Gratuit                    | Payant                 |
| Compatibilité Power BI                | Native (même éditeur Microsoft)  | Via connecteur           | Via connecteur             | Via connecteur         |
| SSMS (interface graphique)            | Natif                            | pgAdmin                  | MySQL Workbench            | Interface web          |
| AT TIME ZONE                          | Oui                              | Oui (syntaxe différente) | Limité                     | Oui                    |

**Choix : SQL Server 2022** — le MERGE natif est idéal pour notre pattern UPSERT. Les schémas logiques (Gold, Ref, Staging) permettent un cloisonnement propre des données par fonction. Les rôles avec GRANT par schéma et MUST_CHANGE répondent aux exigences de sécurité du cahier des charges. La connexion native Power BI facilite la future phase de visualisation. Et fast_executemany optimise les insertions bulk via pyodbc.

---

## 4. Langage de programmation

| Critère                     | Python                 | Scala/Java            | SQL pur (procédures stockées) |
| --------------------------- | ---------------------- | --------------------- | ----------------------------- |
| Appels API REST             | Natif (requests)       | Possible mais verbeux | Impossible                    |
| Manipulation de données     | Pandas (DataFrames)    | Spark (DataFrames)    | T-SQL uniquement              |
| Écriture Parquet            | PyArrow (natif)        | Natif avec Spark      | Impossible                    |
| Client MinIO/S3             | minio SDK              | AWS SDK               | Impossible                    |
| Intégration Airflow         | PythonOperator (natif) | SparkSubmitOperator   | MsSqlOperator                 |
| Courbe d'apprentissage      | Faible                 | Élevée                | Moyenne                       |
| Communauté Data Engineering | Très large             | Large (Big Data)      | Large (DBA)                   |

**Choix : Python** — seul langage qui couvre de bout en bout les 3 étapes du pipeline (appels API, transformation DataFrame, insertion SQL). L'écosystème pandas + pyarrow + SQLAlchemy + minio est mature et parfaitement intégré. L'alternative Scala/Spark serait surdimensionnée pour 11 lignes par batch.

---

## 5. Manipulation de données (DataFrames)

| Critère                           | Pandas                            | Polars                        | PySpark                     |
| --------------------------------- | --------------------------------- | ----------------------------- | --------------------------- |
| Compatibilité SQLAlchemy + pyodbc | Native (to_sql, fast_executemany) | Limitée (pas de to_sql natif) | Via JDBC                    |
| Compatibilité PyArrow (Parquet)   | Native                            | Native                        | Native                      |
| Performance (< 1M lignes)         | Suffisante                        | Plus rapide (3-5x)            | Overkill (overhead cluster) |
| Mémoire                           | En mémoire (single node)          | En mémoire (single node)      | Distribué                   |
| Communauté et documentation       | Très mature                       | En croissance rapide          | Très mature                 |
| merge/join                        | pd.merge (simple)                 | join (simple)                 | join (simple)               |
| Courbe d'apprentissage            | Faible                            | Moyenne (API différente)      | Élevée                      |

**Choix : Pandas** — la compatibilité native avec SQLAlchemy et pyodbc (notamment fast_executemany) est le facteur décisif. Polars est plus performant mais n'a pas de `to_sql` intégré — il faudrait écrire un connecteur custom. Pour notre volume (11 lignes par batch), la différence de performance est invisible. Polars est envisagé en V2 si les volumes dépassent le million de lignes.

---

## 6. Format de stockage Silver

| Critère                       | Parquet                    | CSV                         | JSON    | Avro                |
| ----------------------------- | -------------------------- | --------------------------- | ------- | ------------------- |
| Compression                   | Oui (snappy, gzip)         | Non                         | Non     | Oui                 |
| Préservation des types        | Oui (INT, DECIMAL, BIGINT) | Non (tout est string)       | Partiel | Oui                 |
| Lecture sélective de colonnes | Oui (orienté colonne)      | Non (lecture ligne entière) | Non     | Non (orienté ligne) |
| Compatibilité Spark/Trino     | Native                     | Native                      | Native  | Native              |
| Taille fichier (11 villes)    | ~5 Ko                      | ~20 Ko                      | ~15 Ko  | ~4 Ko               |
| Lisible par un humain         | Non                        | Oui                         | Oui     | Non                 |

**Choix : Parquet** — le format standard du Data Lake moderne. La compression réduit le stockage de 4x par rapport au CSV. La préservation des types évite les bugs de conversion (un "0" CSV peut être interprété comme string ou int). La lecture sélective de colonnes sera critique si les chercheurs interrogent directement le Silver en V2.

---

## 7. Gestionnaire de paquets Python

| Critère                   | uv                         | pip                    | Poetry            | conda                 |
| ------------------------- | -------------------------- | ---------------------- | ----------------- | --------------------- |
| Vitesse d'installation    | Ultra-rapide (10-100x pip) | Lent                   | Moyen             | Lent                  |
| Résolution de dépendances | Oui (déterministe)         | Basique                | Oui               | Oui                   |
| pyproject.toml            | Oui                        | Non (requirements.txt) | Oui               | Non (environment.yml) |
| Lock file                 | Oui (uv.lock)              | Non                    | Oui (poetry.lock) | Non                   |
| Compatibilité pip         | 100%                       | Natif                  | 100%              | Partielle             |

**Choix : uv** — ultra-rapide, compatible pip, et utilise le standard pyproject.toml. Résout les dépendances de manière déterministe (même versions sur toutes les machines). Remplace pip, pip-tools et virtualenv en un seul outil.

---

## 8. Infrastructure (conteneurisation)

| Critère                   | Docker Compose                 | Kubernetes                | Installation native    | VM                     |
| ------------------------- | ------------------------------ | ------------------------- | ---------------------- | ---------------------- |
| Simplicité de déploiement | 1 commande (docker compose up) | Complexe (manifests YAML) | Manuel par service     | Manuel + hyperviseur   |
| Reproductibilité          | Totale (même image partout)    | Totale                    | Dépend de l'OS         | Dépend de l'image VM   |
| Réseau entre services     | Automatique (nom de service)   | Via Services K8s          | Configuration manuelle | Configuration manuelle |
| Volumes persistants       | Natif                          | Natif (PVC)               | Natif (disque)         | Natif (disque virtuel) |
| Scalabilité               | Limitée (single node)          | Illimitée (multi-node)    | Limitée                | Limitée                |
| Coût                      | Gratuit                        | Gratuit mais complexe     | Gratuit                | Licence OS potentielle |

**Choix : Docker Compose** — un seul fichier YAML décrit toute l'infrastructure (6 conteneurs). Un nouveau membre de l'équipe fait `docker compose up` et a l'environnement complet en 5 minutes. Kubernetes serait pertinent pour une mise en production multi-serveur, pas pour un MVP local.

---

## 9. Licences d'utilisation

La politique de licences est un critère de gouvernance des données. Chaque outil utilisé dans le projet a été vérifié pour sa compatibilité avec un usage professionnel et académique.

| Outil            | Licence                      | Type                   | Contraintes                                                                                                                               | Usage commercial                                                       |
| ---------------- | ---------------------------- | ---------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| Apache Airflow 3 | Apache 2.0                   | Open source permissive | Aucune. Libre d'utiliser, modifier, distribuer                                                                                            | Oui, sans restriction                                                  |
| MinIO            | GNU AGPL v3                  | Open source copyleft   | Si on modifie MinIO lui-même, le code modifié doit être publié. L'utilisation comme service (notre cas) ne déclenche pas cette obligation | Oui, attention si modification du code source                          |
| SQL Server 2022  | Developer Edition (gratuite) | Propriétaire Microsoft | Utilisable uniquement pour le développement et les tests. Interdit en production                                                          | Non. Production nécessite une licence Standard ou Enterprise (payante) |
| Python           | PSF License                  | Open source permissive | Aucune                                                                                                                                    | Oui, sans restriction                                                  |
| Pandas           | BSD 3-Clause                 | Open source permissive | Aucune                                                                                                                                    | Oui, sans restriction                                                  |
| PyArrow          | Apache 2.0                   | Open source permissive | Aucune                                                                                                                                    | Oui, sans restriction                                                  |
| SQLAlchemy       | MIT                          | Open source permissive | Aucune                                                                                                                                    | Oui, sans restriction                                                  |
| Docker           | Apache 2.0 (Engine)          | Open source            | Docker Desktop gratuit pour les entreprises < 250 employés et < 10M$ de CA                                                                | Vérifier si l'entreprise dépasse les seuils                            |
| Redis            | SSPL (depuis v7.4)           | Source available       | N'est plus open source au sens strict. Usage autorisé sauf en tant que service managé concurrent                                          | Oui pour usage interne. Interdit de le revendre comme service Redis    |
| PostgreSQL       | PostgreSQL License           | Open source permissive | Aucune                                                                                                                                    | Oui, sans restriction                                                  |

### Impact sur notre projet

**Tous les outils utilisés sont gratuits et légaux pour notre contexte** (développement + projet académique). Les points de vigilance pour une mise en production réelle seraient :

- **SQL Server** : la Developer Edition est interdite en production. Il faudrait acheter une licence Standard (~3 600$/an) ou Enterprise, ou migrer vers PostgreSQL (gratuit) en adaptant la syntaxe MERGE
- **MinIO AGPL** : tant qu'on utilise MinIO tel quel (sans modifier son code source), l'AGPL ne pose aucun problème. Si on modifiait le code de MinIO, il faudrait publier les modifications
- **Docker Desktop** : gratuit pour les petites entreprises. TotalGreen devrait vérifier si elle dépasse les seuils (250 employés / 10M$ CA)

### Pourquoi c'est important

La grille d'évaluation mentionne "la politique des licences liées à la data gouvernance". Un Data Engineer doit s'assurer que les outils utilisés sont conformes aux politiques de l'entreprise. Choisir un outil open source ne signifie pas "gratuit sans condition" — certaines licences (AGPL, SSPL) imposent des obligations si on modifie ou redistribue le logiciel.

---

## Résumé des choix

| Composant      | Choix           | Licence                 | Raison principale                                               |
| -------------- | --------------- | ----------------------- | --------------------------------------------------------------- |
| Orchestrateur  | Airflow 3       | Apache 2.0              | Standard industrie, logical_date natif, interface web           |
| Data Lake      | MinIO           | AGPL v3                 | S3-compatible, local, gratuit, migration cloud transparente     |
| Data Warehouse | SQL Server 2022 | Developer (gratuit dev) | MERGE natif, schémas logiques, rôles par schéma, Power BI natif |
| Langage        | Python          | PSF License             | Couvre E, T, L de bout en bout, écosystème mature               |
| DataFrames     | Pandas          | BSD 3-Clause            | Compatibilité SQLAlchemy + pyodbc, volume MVP faible            |
| Format Silver  | Parquet         | Apache 2.0              | Compression, typage, lecture sélective                          |
| Paquets        | uv              | MIT                     | Ultra-rapide, pyproject.toml, déterministe                      |
| Infrastructure | Docker Compose  | Apache 2.0              | Reproductible, 1 commande, réseau automatique                   |
