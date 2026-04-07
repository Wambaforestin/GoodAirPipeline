# Principes de Développement: GoodAir Pipeline

Ce document décrit les principes d'ingénierie appliqués pour rendre le pipeline robuste, maintenable et résilient. Pour chaque principe, on explique comment il est appliqué dans notre contexte MVP et ce qui est prévu pour les prochaines itérations.

---

## 1. Fail Fast (Crash tôt, crash fort)

**Principe :** ne pas cacher les erreurs. Si quelque chose ne va pas, le pipeline doit s'arrêter immédiatement avec un message clair plutôt que de continuer avec des données corrompues.

**Comment on l'applique :**

Dans l'extraction, si une API renvoie une erreur serveur (429, 500), on ne la rattrape pas — on laisse Python crasher :

```python
# extract_apis.py
response = requests.get(url, params=params, timeout=30)
response.raise_for_status()  # Crash immédiat si erreur HTTP
```

Avant l'insertion en base, le data contract vérifie que toutes les colonnes attendues sont présentes. Si le schéma de sortie est incorrect, le pipeline plante avant de toucher SQL Server :

```python
# load_gold.py
expected_cols = ["NomVille", "IDTemps", "Temperature", ...]
assert all(col in df.columns for col in expected_cols), \
    f"Colonnes manquantes. Attendu: {expected_cols}, Reçu: {list(df.columns)}"
```

**Ce qu'on ne fait pas :** des blocs `try/except Exception: pass` qui avalent les erreurs silencieusement. C'est strictement interdit dans nos specs. Le seul `try/except` autorisé est pour des erreurs d'infrastructure connues (timeout réseau, bucket MinIO déjà existant), jamais pour des erreurs de données.

---

## 2. Design for Failure (Concevez en fonction du pire scénario)

**Principe :** partir du postulat que tout va casser — les APIs, le réseau, la base, le disque. Le système doit y survivre.

**Comment on l'applique :**

Le pipeline gère 4 scénarios de panne :

| Scénario                | Comportement                                                         |
| ----------------------- | -------------------------------------------------------------------- |
| API OpenWeatherMap down | On garde les données AQICN, MeteoStatus = FAILED                     |
| API AQICN down          | On garde les données météo, AirStatus = FAILED                       |
| Les deux APIs down      | La ligne est rejetée (ligne morte), sauvegardée dans silver/rejects/ |
| SQL Server injoignable  | Fail Fast, Airflow retente dans 5 minutes                            |

La fusion des deux sources utilise un outer join pour ne jamais perdre de données même si une seule source répond :

```python
# transform_silver.py
df_merged = pd.merge(df_meteo, df_air, on=["NomVille", "IDTemps"], how="outer")
```

Et si une API ne renvoie pas toutes ses colonnes (ex: Lyon n'a pas PM2.5), on les crée à NULL plutôt que de crasher :

```python
# transform_silver.py
def ensure_all_columns(df):
    for col in ALL_EXPECTED_COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA
    return df
```

---

## 3. Idempotence

**Principe :** exécuter le pipeline N fois pour la même heure doit produire exactement le même résultat qu'une seule exécution. Pas de doublons, pas d'effets de bord.

**Comment on l'applique à chaque couche :**

- **Bronze (MinIO)** — `put_object` écrase le fichier existant au même chemin. 10 exécutions = 1 fichier.
- **Silver (MinIO)** — même logique, le Parquet est écrasé.
- **Staging (SQL Server)** — `TRUNCATE TABLE` avant chaque insertion. Les données de l'heure précédente sont vidées.
- **Gold (SQL Server)** — le `MERGE` sur la clé composite `(IDLieu, IDTemps)` fait un UPDATE si la ligne existe, un INSERT sinon :

```sql
MERGE Gold.FactMesures AS target
USING (...) AS source
ON target.IDLieu = source.IDLieu AND target.IDTemps = source.IDTemps
WHEN MATCHED THEN UPDATE SET ...
WHEN NOT MATCHED THEN INSERT ...
```

Résultat : relancer le pipeline 10 fois pour 14h donne toujours exactement 11 lignes (1 par ville), pas 110.

---

## 4. Retry avec délai (Résilience automatique)

**Principe :** quand une erreur transitoire se produit (timeout réseau, rate limit API, base temporairement indisponible), le système retente automatiquement après un délai.

**Comment on l'applique :**

Airflow gère les retries, pas Python. La séparation est claire : Python traite les données et fait Fail Fast. Airflow décide quand retenter.

```python
# goodair_dag.py
default_args = {
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}
```

Si l'extraction plante (ex: erreur 429 Too Many Requests), Airflow attend 5 minutes puis relance. Après 2 échecs consécutifs, la task est marquée comme failed définitivement.

**Ce qui est prévu en V2 :** un backoff exponentiel (5 min, puis 15 min, puis 45 min) pour les cas de pannes prolongées. Airflow le supporte nativement via `retry_exponential_backoff=True`.

---

## 5. Circuit Breaker (Disjoncteur)

**Principe :** si un service externe est en panne prolongée, arrêter de l'appeler pour ne pas gaspiller des ressources et ne pas aggraver la situation.

**Statut : non implémenté dans le MVP.**

Actuellement, si AQICN est down, chaque run horaire essaie quand même d'appeler l'API, échoue, et Airflow retente. Ça marche pour des pannes courtes, mais si AQICN est down pendant 24h, on fait 48 appels inutiles (24h × 2 retries).

**Ce qui est prévu en V2 :** un mécanisme de circuit breaker qui :

- Après 3 échecs consécutifs sur une API → marque l'API comme "ouverte" (désactivée)
- Toutes les 30 minutes → tente un appel de test pour voir si l'API est revenue
- Si l'appel test réussit → referme le circuit et reprend les appels normaux

Cela pourrait être implémenté via une variable Airflow ou un fichier d'état dans MinIO.

---

## 6. Anti-fragilité (Typage et validation)

**Principe :** les données qui entrent dans le pipeline sont imprévisibles (chaînes de caractères au lieu de nombres, NULL inattendus, formats incohérents). Le pipeline ne doit pas juste y résister, il doit les nettoyer activement.

**Comment on l'applique :**

Le typage strict convertit les valeurs non numériques en NULL plutôt que de crasher :

```python
# transform_silver.py
numeric_cols = ["Temperature", "Humidite", "Pression", "VitesseVent",
                "AqiGlobal", "PM25", "PM10", "NO2", "O3"]
for col in numeric_cols:
    df[col] = pd.to_numeric(df[col], errors="coerce")  # "abc" → NULL, pas crash
```

Les codes pays manquants sont remplacés par une valeur par défaut :

```python
df["CodePays"] = df["CodePays"].fillna("ND")
```

Les DQ Flags marquent les anomalies sans rejeter la ligne :

```python
df["is_temp_valid"] = df["Temperature"].isna() | (
    (df["Temperature"] >= -50) & (df["Temperature"] <= 60)
)
```

Le NomVille vient du fichier config, pas de l'API, pour éviter les incohérences entre sources :

```python
# flatten_openweathermap prend city_name du config, pas raw.get("name")
row = {
    "NomVille": city_name,  # du config, pas de l'API
    ...
}
```

---

## 7. Journalisation structurée

**Principe :** les logs doivent permettre de comprendre exactement ce qui s'est passé, où, et pourquoi, sans deviner. Un message "erreur" ne suffit pas. Il faut l'horodatage, le module, et le contexte.

**Comment on l'applique :**

Le logger est configuré avec un format structuré dans `connections.py` :

```python
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("goodair")
```

Chaque étape logge son contexte :

```python
# Extract
logger.info(f"Extraction pour {city}, {country}...")
logger.info(f"Bronze sauvegardé : {bucket}/{object_path}")

# Transform
logger.info(f"{len(df_valid)} lignes valides sauvegardées en Silver.")
logger.warning(f"{len(df_rejects)} lignes rejetées sauvegardées.")

# Load
logger.info(f"{len(df_lieux)} villes insérées dans Staging.DimLieux_Temp")
logger.info(f"MERGE FactMesures exécuté avec IDBatch = {batch_id}")
```

Airflow capture tous ces logs et les rend consultables par task dans l'interface web (onglet Logs).

**Ce qui est prévu en V2 :** des alertes Slack ou Email quand une task échoue ou quand un pattern d'anomalie est détecté (ex: PM2.5 NULL pour Paris pendant 3 heures consécutives). Airflow le supporte nativement via `on_failure_callback`.

---

## 8. Gouvernance des données

**Principe :** savoir d'où vient chaque donnée, qui l'a modifiée, quand, et pourquoi. C'est le lignage (data lineage).

**Comment on l'applique :**

Chaque ligne de `Gold.FactMesures` porte ses métadonnées d'audit :

```sql
MeteoStatus     -- OK ou FAILED : quelle source a répondu
AirStatus       -- OK ou FAILED : quelle source a répondu
DateInsertion   -- quand la ligne a été créée
DateModification -- quand la ligne a été mise à jour pour la dernière fois
IDBatch         -- quel run Airflow a produit cette ligne
```

Le `IDBatch` permet un rollback chirurgical si un run a corrompu des données :

```sql
-- Identifier les données d'un run problématique
SELECT * FROM Gold.FactMesures WHERE IDBatch = 'scheduled__2026-03-30T14:00:00+00:00';

-- Supprimer uniquement les données de ce run
DELETE FROM Gold.FactMesures WHERE IDBatch = 'scheduled__2026-03-30T14:00:00+00:00';
```

Le Data Catalog (`Ref.DataCatalog`) documente chaque colonne avec sa source API, son chemin JSON d'origine, et sa description. Le fichier `DATA_CATALOG.md` fournit la même information dans le repository.

Les données brutes sont conservées indéfiniment dans MinIO Bronze (append-only). Même si Gold est corrompu, on peut reconstruire le DW à partir du Data Lake.

---

## 9. Séparation des responsabilités

**Principe :** chaque composant a un rôle unique et bien défini. Pas de couplage entre orchestration et traitement.

**Comment on l'applique :**

| Composant     | Responsabilité                                             | Ce qu'il ne fait PAS                     |
| ------------- | ---------------------------------------------------------- | ---------------------------------------- |
| Airflow       | Planification, retries, alertes, injection du logical_date | Aucune transformation de données         |
| Python (src/) | Extraction, transformation, chargement                     | Aucune gestion de scheduling ni de retry |
| SQL Server    | Stockage, MERGE, contraintes d'intégrité                   | Aucun appel API ni transformation        |
| MinIO         | Stockage des données brutes et intermédiaires              | Aucune logique métier                    |

Le DAG ne contient que de la glue — il appelle `run_extract`, `run_transform`, `run_load` en leur passant le `run_date`. Toute la logique métier est dans `src/`.

```python
# goodair_dag.py — le DAG ne fait que connecter
def task_extract(**kwargs):
    run_date = to_paris_time(kwargs["logical_date"])
    run_extract(run_date)  # Toute la logique est dans src/extract/
```

---

## 10. Pilotage par configuration

**Principe :** le comportement du pipeline est modifiable sans toucher au code. Ajouter une ville, changer un paramètre, ne nécessite aucun redéploiement.

**Comment on l'applique :**

Les villes à surveiller sont dans un fichier JSON. Ajouter une ville = ajouter une ligne :

```json
[
  {"city": "Paris", "country": "FR"},
  {"city": "Lyon", "country": "FR"},
  {"city": "Bordeaux", "country": "FR"}
]
```

Les paramètres du pipeline (noms de tables, patterns de partitionnement, URLs des APIs) sont dans `pipeline_config.yaml`.

Les secrets et connexions sont dans le `.env`, jamais dans le code.

**Ce qui est prévu en V2 :** migrer le pilotage des villes du fichier JSON vers une table SQL `Ref.VillesCibles`, pour permettre aux opérateurs d'ajouter des villes via SSMS sans accès au repository Git.

---

## 11. Tests automatisés (CI/CD)

**Statut : non implémenté dans le MVP.**

Actuellement, les tests sont manuels : on vérifie les données dans SSMS après chaque run, on consulte les logs Airflow, on compare les températures avec les applis météo.

**Ce qui est prévu en V2 :**

- **Tests unitaires (Pytest)** : valider chaque fonction de transformation isolément (flatten, cleaning rules, ensure_all_columns)
- **Tests d'intégration** : simuler un run complet avec des données mockées
- **Linter (Ruff/Flake8)** : vérifier la qualité du code à chaque commit
- **CI/CD (GitHub Actions)** : à chaque push :
  - Exécuter les tests unitaires → si échec, rejeter le push
  - Vérifier la couverture de code → si elle baisse, avertir
  - Exécuter le linter → si erreur de style, rejeter le push
  - Builder l'image Docker → si échec, rejeter le push

```yaml
# Exemple de workflow GitHub Actions (prévu V2)
name: CI Pipeline
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install pytest ruff
      - run: ruff check src/
      - run: pytest tests/ --cov=src --cov-fail-under=80
```

---

## 12. Observabilité

**Principe :** à tout moment, on doit pouvoir répondre à : "Est-ce que le pipeline fonctionne ? Depuis quand ? Qu'est-ce qui a cassé ?"

**Comment on l'applique :**

- **Airflow UI** : chaque run est visible avec son statut (success, failed, retry), sa durée, et ses logs détaillés
- **MinIO Console** : on voit les fichiers Bronze et Silver, leur taille, leur date de dernière modification
- **SSMS** : les requêtes de diagnostic (`06_diagnostic_admin.sql`) montrent les trous dans les données, les taux de disponibilité, les pannes par source, et l'état des tables staging

Le script de diagnostic détecte les créneaux manquants :

```sql
-- Trous dans les données
SELECT t1.IDTemps AS DernierCreneau, t2.IDTemps AS ProchainCreneau,
       t2.IDTemps - t1.IDTemps - 1 AS NbCreneauxManquants
FROM Gold.DimTemps t1
INNER JOIN Gold.DimTemps t2 ON t2.IDTemps = (
    SELECT MIN(IDTemps) FROM Gold.DimTemps WHERE IDTemps > t1.IDTemps
)
WHERE t2.IDTemps - t1.IDTemps > 1;
```

**Ce qui est prévu en V2 :** alertes automatiques Slack/Email via `on_failure_callback` d'Airflow et monitoring dédié (PM2.5 NULL pour Paris pendant 3h consécutives → alerte).

---

## Résumé

| Principe                       | Statut MVP            | Prévu V2                 |
| ------------------------------ | --------------------- | ------------------------ |
| Fail Fast                      | Appliqué              | -                        |
| Design for Failure             | Appliqué              | -                        |
| Idempotence                    | Appliqué              | -                        |
| Retry avec délai               | Appliqué (fixe 5 min) | Backoff exponentiel      |
| Circuit Breaker                | Non implémenté        | Oui                      |
| Anti-fragilité                 | Appliqué              | -                        |
| Journalisation structurée      | Appliqué (basique)    | Alertes Slack/Email      |
| Gouvernance des données        | Appliqué              | -                        |
| Séparation des responsabilités | Appliqué              | -                        |
| Pilotage par configuration     | Appliqué              | Migration vers table SQL |
| Tests automatisés (CI/CD)      | Non implémenté        | GitHub Actions + Pytest  |
| Observabilité                  | Appliqué (manuel)     | Alertes automatiques     |
