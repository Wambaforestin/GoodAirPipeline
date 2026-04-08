# Vérifications de Qualité des Données: GoodAir Pipeline

Ce document décrit comment la qualité des données est assurée à chaque étape du pipeline. Chaque vérification est justifiée par un enjeu métier concret et illustrée avec le code qui l'implémente.

---

## Le contexte : nous ne contrôlons pas la source

C'est le point de départ de toute notre stratégie DQ. Les données viennent de deux APIs publiques (OpenWeatherMap et AQICN) sur lesquelles nous n'avons aucun contrôle :

- Nous ne choisissons pas le format de la réponse JSON
- Nous ne choisissons pas quels polluants sont mesurés par chaque station
- Nous ne contrôlons pas la disponibilité des serveurs
- Nous ne contrôlons pas les changements de structure de l'API (breaking changes)

Conséquence : le pipeline doit être **défensif** par nature. On ne fait pas confiance aux données entrantes, on les vérifie systématiquement avant de les stocker dans le Data Warehouse.

---

## Principe directeur : vérifier ce qui compte, pas tout vérifier

Une erreur courante en Data Quality est de multiplier les vérifications sur toutes les colonnes. Ça produit deux effets négatifs :

1. **Alert fatigue** — trop d'alertes tue l'alerte. Si le pipeline signale 50 anomalies par heure, personne ne les lit
2. **Faux positifs** — vérifier que l'O3 n'est jamais NULL alors que certaines stations ne le mesurent pas produit des alertes permanentes sans action possible

Notre approche : concentrer les vérifications sur ce qui a un **impact métier réel** et ce sur quoi on peut **agir**.

---

## Étape 1 : Validation à l'extraction (Bronze)

**Fichier :** `src/extract/extract_apis.py`

### 1.1 Vérification du statut HTTP

**Enjeu métier :** si l'API renvoie une erreur serveur, les données sont corrompues ou inexistantes. Les stocker en Bronze contaminerait tout le pipeline en aval.

```python
response = requests.get(url, params=params, timeout=30)
response.raise_for_status()  # 429, 500, 503 → Fail Fast
```

**Pourquoi raise_for_status et pas un try/except :** on veut que Airflow voie l'erreur et gère le retry. Un `try/except` qui avale l'erreur empêcherait Airflow de savoir que quelque chose a échoué.

### 1.2 Vérification du statut applicatif (AQICN)

**Enjeu métier :** AQICN peut renvoyer un HTTP 200 (succès technique) mais avec `"status": "error"` dans le JSON (échec applicatif). Sans cette vérification, on stockerait un JSON d'erreur en Bronze.

```python
data = response.json()
if data.get("status") != "ok":
    logger.warning(f"AQICN - Réponse non-ok pour {city} : {data.get('status')}")
    return None
```

### 1.3 Gestion des villes introuvables (OpenWeatherMap)

**Enjeu métier :** si une ville est mal orthographiée dans le fichier config, l'API renvoie un 404. On ne veut pas que le pipeline plante pour toutes les villes à cause d'une seule erreur de config.

```python
if response.status_code == 404:
    logger.warning(f"OpenWeatherMap - Ville introuvable : {city},{country}")
    return None  # Skip cette ville, continue avec les autres
```

### 1.4 Timeout réseau

**Enjeu métier :** une API qui ne répond pas doit être détectée rapidement pour ne pas bloquer le pipeline entier.

```python
response = requests.get(url, params=params, timeout=30)  # 30 secondes max
```

---

## Étape 2 : Nettoyage et validation à la transformation (Silver)

**Fichier :** `src/transform/transform_silver.py`

C'est l'étape la plus critique en termes de qualité des données. C'est ici que la donnée brute devient exploitable.

### 2.1 Cohérence du NomVille entre les sources

**Enjeu métier :** si le NomVille diffère entre OpenWeatherMap ("Paris") et AQICN ("Paris, Champs-Élysées"), le merge échoue et on perd la fusion des données météo + air pour cette ville.

**Solution :** le NomVille ne vient jamais de l'API. Il vient du fichier config, qui est la source unique de vérité.

```python
def flatten_openweathermap(raw, city_name, run_date):
    row = {
        "NomVille": city_name,  # Du config, pas de raw.get("name")
        ...
    }
```

**Pourquoi c'est important :** sans cette vérification, on se retrouverait avec des lignes non fusionnées — les données météo et air pour la même ville à la même heure apparaîtraient comme deux lignes séparées avec des NULL de chaque côté.

### 2.2 Garantie de toutes les colonnes attendues

**Enjeu métier :** si OpenWeatherMap est en panne, les colonnes météo (Temperature, Humidite, etc.) n'existent pas dans le DataFrame. Sans cette vérification, toute opération sur ces colonnes crasherait avec un KeyError.

```python
ALL_EXPECTED_COLUMNS = [
    "NomVille", "CodePays", "Latitude", "Longitude", "IDTemps",
    "Temperature", "Humidite", "Pression", "VitesseVent",
    "AqiGlobal", "PM25", "PM10", "NO2", "O3"
]

def ensure_all_columns(df):
    for col in ALL_EXPECTED_COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA
    return df
```

**Pourquoi pd.NA et pas 0 :** remplacer par 0 fausserait les moyennes (0°C est une vraie température, pas une absence de mesure). Les fonctions SQL d'agrégation (`AVG`, `SUM`) ignorent naturellement les NULL.

### 2.3 Typage strict

**Enjeu métier :** les APIs peuvent renvoyer des chaînes de caractères au lieu de nombres (ex: "Erreur Capteur" au lieu de 15.3). Si ces valeurs atteignent SQL Server, les requêtes BI planteraient.

```python
numeric_cols = ["Temperature", "Humidite", "Pression", "VitesseVent",
                "AqiGlobal", "PM25", "PM10", "NO2", "O3"]
for col in numeric_cols:
    df[col] = pd.to_numeric(df[col], errors="coerce")  # "abc" → NULL
```

`errors="coerce"` convertit silencieusement les valeurs non numériques en NULL plutôt que de crasher. Ce n'est pas un `try/except` qui cache une erreur — c'est une transformation explicite et traçable.

### 2.4 Gestion des valeurs manquantes (règles métier)

**Enjeu métier :** chaque type de NULL a une signification différente et une action différente.

| Donnée manquante     | Action            | Justification métier                                                                                     |
| -------------------- | ----------------- | -------------------------------------------------------------------------------------------------------- |
| CodePays             | Remplacé par 'ND' | Le nom de la ville suffit pour l'identification. On ne rejette pas la ligne pour un code pays manquant   |
| Latitude / Longitude | NULL maintenu     | Empêche la carte, mais les graphiques temporels restent exploitables                                     |
| Temperature          | NULL maintenu     | 0°C est une vraie valeur. Imputer fausserait les moyennes                                                |
| PM2.5, O3            | NULL maintenu     | Toutes les stations ne mesurent pas tous les polluants. C'est un comportement IoT normal, pas une erreur |
| Pluie, Neige         | Remplacé par 0    | L'absence de la clé dans l'API signifie "il ne pleut pas". Le 0 est statistiquement correct ici          |

```python
# CodePays manquant → 'ND'
df["CodePays"] = df["CodePays"].fillna("ND")
```

**Pourquoi pas de remplacement pour les métriques :** c'est la règle la plus importante. Un chercheur qui calcule la moyenne de température à Lyon ne doit pas voir sa moyenne faussée par des zéros qui représentent des pannes de capteurs.

### 2.5 Statuts de source (MeteoStatus / AirStatus)

**Enjeu métier :** les chercheurs doivent savoir immédiatement si une mesure est complète ou partielle. Un tableau de bord qui affiche une température sans indiquer que la pollution est manquante est trompeur.

```python
meteo_cols = ["Temperature", "Humidite", "Pression", "VitesseVent"]
air_cols = ["AqiGlobal", "PM25", "PM10", "NO2", "O3"]
df["MeteoStatus"] = np.where(df[meteo_cols].isna().all(axis=1), "FAILED", "OK")
df["AirStatus"] = np.where(df[air_cols].isna().all(axis=1), "FAILED", "OK")
```

**Pourquoi "toutes les colonnes NULL" et pas "une seule colonne NULL" :** si on marquait FAILED dès qu'un seul polluant manque, Lyon serait en permanence FAILED (PM2.5 et O3 ne sont jamais mesurés par sa station). Le statut perdrait toute utilité — c'est exactement le problème d'alert fatigue.

FAILED signifie : "l'API n'a renvoyé aucune donnée exploitable pour cette source". C'est actionnable : ça indique une panne réelle, pas un capteur manquant.

### 2.6 Détection de lignes mortes

**Enjeu métier :** une ligne où TOUTES les métriques des deux sources sont NULL n'a aucune valeur analytique. La stocker dans le Data Warehouse gaspille de l'espace et fausse les comptages.

```python
dead_rows = df[meteo_cols + air_cols].isna().all(axis=1)
df_rejects = df[dead_rows].copy()
df_valid = df[~dead_rows].copy()
```

**Ce qu'on fait des lignes mortes :** elles ne sont pas supprimées. Elles sont sauvegardées dans `silver/rejects/` pour permettre aux Data Engineers d'analyser le "pourquoi" plus tard.

### 2.7 Validation des clés logiques

**Enjeu métier :** une mesure sans ville ou sans heure ne peut pas être rattachée à quoi que ce soit dans le Data Warehouse. Les FK échoueraient de toute façon.

```python
no_keys = df_valid["NomVille"].isna() | df_valid["IDTemps"].isna()
df_rejects = pd.concat([df_rejects, df_valid[no_keys]])
df_valid = df_valid[~no_keys].copy()
```

### 2.8 Dédoublonnage

**Enjeu métier :** si une API renvoie deux fois la même ville dans le même batch (bug API ou double appel), on ne doit garder qu'une seule ligne par (NomVille, IDTemps).

```python
df_valid = df_valid.drop_duplicates(subset=["NomVille", "IDTemps"], keep="last")
```

`keep="last"` conserve la donnée la plus récente si doublon.

### 2.9 DQ Flags (indicateurs de qualité)

**Enjeu métier :** au lieu de rejeter une ligne dont la température est suspecte, on la marque. Le chercheur décide ensuite s'il veut l'inclure dans son analyse ou pas.

```python
df["is_temp_valid"] = df["Temperature"].isna() | (
    (df["Temperature"] >= -50) & (df["Temperature"] <= 60)
)
```

**Pourquoi des flags et pas des rejets :** une température de -45°C est extrême mais possible (record français : -36.7°C). Rejeter automatiquement supprimerait potentiellement des données valides. Le flag laisse le choix au consommateur de la donnée.

---

## Étape 3 : Validation au chargement (Gold)

**Fichier :** `src/load/load_gold.py`

### 3.1 Data Contract (contrat de schéma)

**Enjeu métier :** si le schéma du Parquet Silver ne correspond pas aux colonnes attendues par SQL Server, l'insertion planterait avec un message d'erreur obscur. Le data contract donne un message clair et empêche toute interaction avec la base.

```python
expected_cols = [
    "NomVille", "IDTemps", "Temperature", "Humidite", "Pression",
    "VitesseVent", "AqiGlobal", "PM25", "PM10", "NO2", "O3",
    "MeteoStatus", "AirStatus"
]
assert all(col in df.columns for col in expected_cols), \
    f"Colonnes manquantes. Attendu: {expected_cols}, Reçu: {list(df.columns)}"
```

**Pourquoi un assert et pas un if :** l'assert crashe le script immédiatement (Fail Fast). Un `if` avec un `return` pourrait être manqué dans les logs. L'assert est explicite : "ce contrat DOIT être respecté, sinon rien ne se passe".

### 3.2 TRUNCATE avant insertion staging

**Enjeu métier :** garantir que le staging ne contient que les données du batch courant. Sans le TRUNCATE, les données de l'heure précédente seraient mélangées avec celles de l'heure courante.

```python
def truncate_staging(engine):
    with engine.connect() as conn:
        conn.execute(text("TRUNCATE TABLE Staging.FactMesures_Temp"))
        conn.execute(text("TRUNCATE TABLE Staging.DimLieux_Temp"))
        conn.execute(text("TRUNCATE TABLE Staging.DimTemps_Temp"))
        conn.commit()
```

### 3.3 MERGE avec UPSERT

**Enjeu métier :** le MERGE garantit qu'on ne crée pas de doublons dans Gold tout en mettant à jour les données si elles existent déjà (idempotence).

```sql
MERGE Gold.FactMesures AS target
USING (...) AS source
ON target.IDLieu = source.IDLieu AND target.IDTemps = source.IDTemps
WHEN MATCHED THEN UPDATE SET ...
WHEN NOT MATCHED THEN INSERT ...
```

---

## Étape 4 : Contraintes SQL Server (dernière ligne de défense)

**Fichier :** `src/sql/01_init_goodair_dw.sql`

Même si le code Python fait toutes les vérifications, SQL Server a ses propres contraintes qui empêchent les données invalides d'être insérées. C'est la défense en profondeur.

### 4.1 Clé primaire composite

```sql
CONSTRAINT PK_Gold_FactMesures PRIMARY KEY CLUSTERED (IDLieu, IDTemps)
```

Empêche physiquement deux lignes pour la même ville à la même heure. Même si le code Python a un bug, SQL Server refuse le doublon.

### 4.2 Clés étrangères

```sql
CONSTRAINT FK_FactMesures_DimLieux FOREIGN KEY (IDLieu) REFERENCES Gold.DimLieux(IDLieu)
CONSTRAINT FK_FactMesures_DimTemps FOREIGN KEY (IDTemps) REFERENCES Gold.DimTemps(IDTemps)
```

Empêche d'insérer une mesure pour une ville ou une heure qui n'existe pas dans les dimensions. C'est pour ça que le MERGE insère d'abord dans DimLieux et DimTemps avant FactMesures.

### 4.3 Contrainte CHECK

```sql
CONSTRAINT CK_FactMesures_Humidite CHECK (Humidite BETWEEN 0 AND 100)
```

Une humidité de 150% est physiquement impossible. Même si l'API renvoie cette valeur et que le code Python ne la détecte pas, SQL Server la rejette.

### 4.4 Contraintes sur DimTemps

```sql
CONSTRAINT CK_Gold_DimTemps_Mois CHECK (Mois BETWEEN 1 AND 12)
CONSTRAINT CK_Gold_DimTemps_Heure CHECK (Heure BETWEEN 0 AND 23)
```

Un mois 13 ou une heure 25 sont impossibles. Protection contre les bugs de calcul du Time Bucketing.

---

## Vérifications prévues en V2

### Monitoring intelligent (Anti-fatigue)

Au lieu de vérifier chaque colonne à chaque run, on détecte les patterns anormaux qui nécessitent une intervention humaine :

- PM2.5 NULL pour une ville majeure (Paris) pendant 3 heures consécutives → alerte (panne de station prolongée)
- Température identique pour une ville sur 5 heures consécutives → alerte (capteur bloqué)
- 100% des lignes rejetées dans un batch → alerte critique

### Validation croisée entre sources

Comparer les données entre OpenWeatherMap et AQICN quand elles se chevauchent (température, humidité) pour détecter les incohérences.

### Détection de dérive (Data Drift)

Surveiller si la distribution des valeurs change significativement au fil du temps (ex: la moyenne de PM2.5 à Paris double soudainement). Peut indiquer un changement de capteur ou un bug API.

### Tests de non-régression

À chaque modification du code de transformation, exécuter des tests avec des données de référence connues pour vérifier que le résultat ne change pas.

---

## Résumé des vérifications par étape

| Étape      | Vérification                  | Type                    | Fichier                |
| ---------- | ----------------------------- | ----------------------- | ---------------------- |
| Extract    | Statut HTTP                   | Fail Fast               | extract_apis.py        |
| Extract    | Statut applicatif AQICN       | Validation              | extract_apis.py        |
| Extract    | Ville introuvable (404)       | Skip + Log              | extract_apis.py        |
| Extract    | Timeout réseau                | Fail Fast               | extract_apis.py        |
| Transform  | Cohérence NomVille            | Prévention              | transform_silver.py    |
| Transform  | Colonnes manquantes           | Défense                 | transform_silver.py    |
| Transform  | Typage strict                 | Nettoyage               | transform_silver.py    |
| Transform  | Valeurs manquantes            | Règles métier           | transform_silver.py    |
| Transform  | Statuts MeteoStatus/AirStatus | Traçabilité             | transform_silver.py    |
| Transform  | Lignes mortes                 | Rejet + Archive         | transform_silver.py    |
| Transform  | Clés logiques NULL            | Rejet                   | transform_silver.py    |
| Transform  | Dédoublonnage                 | Nettoyage               | transform_silver.py    |
| Transform  | DQ Flags                      | Marquage                | transform_silver.py    |
| Load       | Data Contract                 | Fail Fast               | load_gold.py           |
| Load       | TRUNCATE staging              | Idempotence             | load_gold.py           |
| Load       | MERGE UPSERT                  | Idempotence             | load_gold.py           |
| SQL Server | Clé primaire                  | Anti-doublon            | 01_init_goodair_dw.sql |
| SQL Server | Clés étrangères               | Intégrité référentielle | 01_init_goodair_dw.sql |
| SQL Server | CHECK contraintes             | Bornes physiques        | 01_init_goodair_dw.sql |
