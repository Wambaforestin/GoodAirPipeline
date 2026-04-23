# Stratégie du Data Warehouse — SQL Server 2022

Ce document décrit comment le Data Warehouse GoodAirDW est conçu, organisé et alimenté. Chaque décision est justifiée par notre cas d'utilisation : historiser des données météo et qualité de l'air pour 11 villes françaises, avec une granularité horaire, destinées à des chercheurs et analystes.

---

## Pourquoi un Data Warehouse séparé du Data Lake

Le Data Lake (MinIO) et le Data Warehouse (SQL Server) ont des rôles complémentaires mais distincts :

|                   | Data Lake (MinIO)                            | Data Warehouse (SQL Server)              |
| ----------------- | -------------------------------------------- | ---------------------------------------- |
| **Rôle**          | Stocker les données brutes et intermédiaires | Servir les données prêtes pour l'analyse |
| **Format**        | JSON, Parquet (fichiers)                     | Tables relationnelles (SQL)              |
| **Consommateurs** | Pipeline ETL (lecture/écriture)              | Chercheurs, Power BI, Tableau            |
| **Requêtage**     | Pas de requêtage direct (pas de SQL)         | SQL natif, jointures, agrégations        |
| **Historique**    | Conserve tout (append-only)                  | Conserve la version consolidée           |

Les chercheurs ne vont jamais lire des fichiers Parquet dans MinIO. Ils se connectent à SQL Server via Power BI ou SSMS et font des requêtes SQL. Le Data Warehouse est optimisé pour ça.

---

## Modélisation : le schéma en étoile (Star Schema)

### Le choix et sa justification

Le Data Warehouse utilise un schéma en étoile (modèle Kimball) avec une table de faits centrale et deux tables de dimensions :

```
            DimTemps
               │
               │ FK (IDTemps)
               │
FactMesures ───┤
               │
               │ FK (IDLieu)
               │
            DimLieux
```

**Pourquoi un star schema et pas une table plate :**

Une table unique sans dimensions fonctionnerait techniquement. Mais elle répéterait "Paris, FR, 48.853400, 2.348800" à chaque ligne horaire. Avec 11 villes × 24h × 365 jours = 96 360 lignes/an, on stockerait 96 360 fois les coordonnées GPS de Paris. Le star schema stocke ces infos une seule fois dans DimLieux.

**Pourquoi une seule table de faits (pas une pour météo et une pour air) :**

Les données météo et qualité de l'air partagent le même grain : 1 ville × 1 heure. Les séparer obligerait les chercheurs à faire des jointures pour chaque analyse comparant température et pollution. Avec une seule table, la requête est directe :

```sql
-- Impact de l'humidité sur la pollution : requête simple grâce à la table unique
SELECT l.NomVille, f.Humidite, f.PM25
FROM Gold.FactMesures f
INNER JOIN Gold.DimLieux l ON f.IDLieu = l.IDLieu
WHERE f.Humidite IS NOT NULL AND f.PM25 IS NOT NULL;
```

Avec deux tables séparées, cette même requête nécessiterait une jointure supplémentaire entre FactMeteo et FactAir.

### Le grain : 1 ligne = 1 ville × 1 heure

Le grain est la décision la plus importante de la modélisation dimensionnelle. Il détermine ce que représente chaque ligne de la table de faits.

Notre grain : **chaque ligne de FactMesures représente l'ensemble des mesures d'une ville pour une heure donnée**.

Ce grain est dicté par :

- La fréquence du pipeline (horaire)
- Le Time Bucketing (1 run Airflow = 1 IDTemps)
- La granularité des APIs (données temps réel, capturées toutes les heures)

La clé primaire composite `(IDLieu, IDTemps)` matérialise ce grain dans SQL Server.

---

## Organisation par schémas

La base de données est cloisonnée en 3 schémas fonctionnels plus un schéma technique :

### Gold — le Data Warehouse analytique

C'est le schéma principal. Il contient les tables en étoile prêtes pour l'analyse :

- `Gold.FactMesures` — table de faits centrale (mesures horaires)
- `Gold.DimLieux` — dimension géographique (villes et coordonnées)
- `Gold.DimTemps` — dimension temporelle (calendrier horaire)

**Qui y accède :** les chercheurs (SELECT), le directeur (SELECT), le pipeline (INSERT/UPDATE via MERGE).

### Ref — le référentiel statique

Contient les données de référence qui ne changent presque jamais :

- `Ref.Pays` — codes ISO et noms des pays
- `Ref.SeuilsOMS` — seuils de pollution de l'Organisation Mondiale de la Santé
- `Ref.DataCatalog` — documentation de chaque colonne du DW

**Pourquoi un schéma séparé :** ces tables ont un cycle de vie différent des données analytiques. Elles sont mises à jour manuellement (ex: l'OMS révise ses seuils une fois par an), pas par le pipeline. Les séparer dans un schéma dédié permet d'appliquer des permissions différentes si nécessaire.

### Staging — la zone de transit

Contient les tables temporaires utilisées par le pipeline pour préparer les données avant le MERGE :

- `Staging.DimLieux_Temp`
- `Staging.DimTemps_Temp`
- `Staging.FactMesures_Temp`

**Caractéristiques des tables staging :**

- Aucun index (pas besoin, les données sont lues une seule fois par le MERGE)
- Aucune contrainte (PK, FK, CHECK) — les validations sont faites en Python avant l'insertion
- Vidées par TRUNCATE à chaque run

**Pourquoi passer par le staging au lieu d'insérer directement dans Gold :** le staging isole le processus de chargement. Si l'insertion en staging réussit mais le MERGE échoue, les données de Gold restent intactes. C'est une zone tampon qui protège l'intégrité du Data Warehouse.

### Staging vs Gold : la différence clé

La table `Staging.FactMesures_Temp` utilise `NomVille` (texte) comme identifiant de ville. La table `Gold.FactMesures` utilise `IDLieu` (entier auto-généré). C'est le MERGE qui fait la traduction via une jointure sur DimLieux :

```sql
MERGE Gold.FactMesures AS target
USING (
    SELECT d.IDLieu, s.IDTemps, s.Temperature, ...
    FROM Staging.FactMesures_Temp s
    INNER JOIN Gold.DimLieux d ON d.NomVille = s.NomVille
) AS source
ON target.IDLieu = source.IDLieu AND target.IDTemps = source.IDTemps
```

Le code Python n'a jamais besoin de connaître l'IDLieu. Il travaille avec des noms de villes, SQL Server résout les clés techniques.

---

## Les tables en détail

### Gold.DimLieux — la dimension géographique

```sql
CREATE TABLE Gold.DimLieux (
    IDLieu INT IDENTITY(1,1) NOT NULL,    -- Clé technique auto-générée
    NomVille NVARCHAR(100) NOT NULL,       -- Nom de la ville (du config)
    CodePays CHAR(2) NULL,                 -- Code ISO (de l'API OWM)
    Latitude DECIMAL(9,6) NULL,            -- GPS (de l'API OWM)
    Longitude DECIMAL(9,6) NULL,           -- GPS (de l'API OWM)
    CONSTRAINT PK_Gold_DimLieux PRIMARY KEY CLUSTERED (IDLieu)
);
```

**Pourquoi IDENTITY et pas le nom de ville comme PK :** le nom de ville est une clé naturelle (il identifie la ville dans le monde réel) mais c'est un texte. Les jointures sur des entiers sont plus rapides que sur des chaînes de caractères. Dans un DW avec des millions de lignes dans la table de faits, cette différence compte.

**Pourquoi Latitude et Longitude sont nullable :** si OpenWeatherMap ne renvoie pas les coordonnées pour une ville, on ne rejette pas la ligne. Les mesures (température, pollution) restent valides sans coordonnées GPS. Les graphiques temporels fonctionnent, seule la carte serait impactée.

### Gold.DimTemps — la dimension temporelle

```sql
CREATE TABLE Gold.DimTemps (
    IDTemps BIGINT NOT NULL,              -- Clé : YYYYMMDDHH (ex: 2026033015)
    DateHeure DATETIME NOT NULL,           -- Horodatage complet
    Annee INT NULL,                        -- Pour filtrer par année
    Mois INT NULL,                         -- Pour filtrer par mois
    Jour INT NULL,                         -- Pour filtrer par jour
    Heure INT NULL,                        -- Pour filtrer par heure
    CONSTRAINT PK_Gold_DimTemps PRIMARY KEY CLUSTERED (IDTemps)
);
```

**Pourquoi décomposer la date en colonnes séparées :** un chercheur qui veut la moyenne de pollution par mois n'a pas à utiliser `DATEPART(MONTH, DateHeure)`. Il filtre directement sur `WHERE Mois = 3`. Les outils BI (Power BI, Tableau) exploitent mieux ces colonnes pré-calculées pour les axes de graphiques.

**Pourquoi IDTemps en BIGINT et pas en DATETIME :** l'IDTemps `2026033015` est un entier lisible par un humain (30 mars 2026 à 15h). C'est aussi plus performant comme clé de jointure qu'un DATETIME. Et c'est déterministe : pour une date donnée, le calcul `int(run_date.strftime("%Y%m%d%H"))` produit toujours la même valeur.

### Gold.FactMesures — la table de faits

```sql
CREATE TABLE Gold.FactMesures (
    -- Clés (le grain)
    IDLieu INT NOT NULL,                   -- FK vers DimLieux
    IDTemps BIGINT NOT NULL,               -- FK vers DimTemps

    -- Métriques météo (OpenWeatherMap)
    Temperature DECIMAL(5,2) NULL,         -- °C
    Humidite INT NULL,                     -- % (0-100)
    Pression INT NULL,                     -- hPa
    VitesseVent DECIMAL(5,2) NULL,         -- m/s

    -- Métriques qualité de l'air (AQICN)
    AqiGlobal INT NULL,                    -- Indice AQI (0-500)
    PM25 DECIMAL(6,2) NULL,                -- Indice AQI PM2.5
    PM10 DECIMAL(6,2) NULL,                -- Indice AQI PM10
    NO2 DECIMAL(6,2) NULL,                 -- Indice AQI NO2
    O3 DECIMAL(6,2) NULL,                  -- Indice AQI O3

    -- Audit et traçabilité
    MeteoStatus VARCHAR(20) NOT NULL,      -- OK ou FAILED
    AirStatus VARCHAR(20) NOT NULL,        -- OK ou FAILED
    DateInsertion DATETIME2 NOT NULL,      -- Première insertion
    DateModification DATETIME2 NOT NULL,   -- Dernière mise à jour
    IDBatch VARCHAR(100) NOT NULL,         -- Run ID Airflow

    CONSTRAINT PK_Gold_FactMesures PRIMARY KEY CLUSTERED (IDLieu, IDTemps),
    CONSTRAINT FK_FactMesures_DimLieux FOREIGN KEY (IDLieu) REFERENCES Gold.DimLieux(IDLieu),
    CONSTRAINT FK_FactMesures_DimTemps FOREIGN KEY (IDTemps) REFERENCES Gold.DimTemps(IDTemps),
    CONSTRAINT CK_FactMesures_Humidite CHECK (Humidite BETWEEN 0 AND 100)
);
```

**Pourquoi toutes les métriques sont nullable :** une source peut être en panne sans que l'autre le soit. Forcer un NOT NULL sur Temperature rejetterait la ligne même si PM25 est valide. Le NULL préserve la donnée exploitable.

**Pourquoi les colonnes d'audit :** elles répondent à trois questions critiques :

- "D'où vient cette donnée ?" → MeteoStatus, AirStatus
- "Quand a-t-elle été chargée ?" → DateInsertion, DateModification
- "Quel run l'a produite ?" → IDBatch (pour rollback ciblé)

---

## Le pattern MERGE (UPSERT)

Le chargement dans Gold suit un pattern en 3 temps, dans un ordre strict :

### Étape 1 : Alimenter les dimensions

```sql
-- DimLieux : insérer seulement si la ville n'existe pas encore
INSERT INTO Gold.DimLieux (NomVille, CodePays, Latitude, Longitude)
SELECT s.NomVille, s.CodePays, s.Latitude, s.Longitude
FROM Staging.DimLieux_Temp s
WHERE NOT EXISTS (
    SELECT 1 FROM Gold.DimLieux d WHERE d.NomVille = s.NomVille
);
```

**Pourquoi avant les faits :** la table FactMesures a une FK vers DimLieux. Si on essaie d'insérer un fait pour Franconville avant que Franconville existe dans DimLieux, la FK échoue.

### Étape 2 : Alimenter la dimension temps

```sql
INSERT INTO Gold.DimTemps (IDTemps, DateHeure, Annee, Mois, Jour, Heure)
SELECT s.IDTemps, s.DateHeure, s.Annee, s.Mois, s.Jour, s.Heure
FROM Staging.DimTemps_Temp s
WHERE NOT EXISTS (
    SELECT 1 FROM Gold.DimTemps d WHERE d.IDTemps = s.IDTemps
);
```

Même logique : la FK vers DimTemps doit être satisfaite avant l'insertion des faits.

### Étape 3 : MERGE des faits

```sql
MERGE Gold.FactMesures AS target
USING (...) AS source
ON target.IDLieu = source.IDLieu AND target.IDTemps = source.IDTemps

WHEN MATCHED THEN UPDATE SET
    target.Temperature = source.Temperature,
    ...
    target.DateModification = GETDATE() AT TIME ZONE 'UTC' AT TIME ZONE 'Romance Standard Time',
    target.IDBatch = :batch_id

WHEN NOT MATCHED THEN INSERT (...) VALUES (...);
```

**WHEN MATCHED (UPDATE)** — la ligne existe déjà pour cette ville à cette heure. On met à jour les métriques avec les valeurs les plus récentes. DateModification et IDBatch sont mis à jour pour tracer quel run a modifié la donnée en dernier.

**WHEN NOT MATCHED (INSERT)** — première fois qu'on voit cette ville à cette heure. On insère une nouvelle ligne avec DateInsertion = maintenant.

**Pourquoi MERGE et pas DELETE/INSERT :** le MERGE est atomique (une seule transaction) et préserve DateInsertion sur les lignes existantes. Un DELETE/INSERT écraserait DateInsertion à chaque run, on perdrait l'information de quand la donnée a été vue pour la première fois.

---

## Intégrité des données

### Clé primaire composite

```sql
PRIMARY KEY CLUSTERED (IDLieu, IDTemps)
```

Garantit physiquement qu'il ne peut pas exister deux lignes pour la même ville à la même heure. C'est la matérialisation SQL du grain "1 ville × 1 heure". Le CLUSTERED signifie que les données sont triées physiquement sur le disque par cette clé, ce qui accélère les requêtes qui filtrent par ville et/ou par heure.

### Clés étrangères

```sql
FOREIGN KEY (IDLieu) REFERENCES Gold.DimLieux(IDLieu)
FOREIGN KEY (IDTemps) REFERENCES Gold.DimTemps(IDTemps)
```

Empêchent d'insérer une mesure pour une ville ou une heure qui n'existe pas dans les dimensions. C'est la dernière ligne de défense après les vérifications Python.

**Pourquoi pas de ON DELETE CASCADE :** dans un Data Warehouse, on ne supprime jamais de dimensions. Supprimer Paris dans DimLieux ne devrait jamais effacer des mois de mesures dans FactMesures. L'absence de CASCADE protège contre les suppressions accidentelles.

### Contraintes CHECK

```sql
CHECK (Humidite BETWEEN 0 AND 100)
CHECK (Mois BETWEEN 1 AND 12)
CHECK (Heure BETWEEN 0 AND 23)
```

Protection contre les valeurs physiquement impossibles. Même si le code Python a un bug, SQL Server refuse les données invalides.

---

## Performances

### Indexation actuelle

Chaque table a un seul index : le clustered index sur la clé primaire. C'est suffisant pour notre volume actuel (quelques milliers de lignes).

### Quand ajouter des index supplémentaires

Si les requêtes deviennent lentes (temps de réponse > 1 seconde), les candidats pour des non-clustered index seraient :

```sql
-- Si les chercheurs filtrent souvent par heure sans ville
CREATE NONCLUSTERED INDEX IX_FactMesures_IDTemps ON Gold.FactMesures(IDTemps);

-- Si les requêtes filtrent souvent par statut
CREATE NONCLUSTERED INDEX IX_FactMesures_Status ON Gold.FactMesures(MeteoStatus, AirStatus);
```

**Pourquoi pas maintenant :** chaque index supplémentaire ralentit les insertions (le MERGE doit mettre à jour l'index). Avec un volume faible, le gain en lecture ne compense pas le coût en écriture.

### fast_executemany

L'insertion en staging utilise `fast_executemany=True` via pyodbc :

```python
engine = create_engine(
    f"mssql+pyodbc:///?odbc_connect={params}",
    connect_args={"fast_executemany": True}
)
```

Cette option envoie toutes les lignes en un seul aller-retour réseau au lieu d'une ligne à la fois. Pour 11 lignes la différence est négligeable, mais pour 500 villes ce serait significatif.

---

## Sécurité

### Accès par rôles

Les permissions sont définies par schéma, pas par table. C'est plus simple à maintenir et plus sécurisé (une nouvelle table dans Gold hérite automatiquement des permissions du schéma) :

| Rôle               | Gold           | Ref            | Staging        |
| ------------------ | -------------- | -------------- | -------------- |
| sa (Data Engineer) | Contrôle total | Contrôle total | Contrôle total |
| Role_Chercheur     | SELECT         | SELECT         | Aucun accès    |
| Role_Directeur     | SELECT         | SELECT         | Aucun accès    |
| Role_RSSI          | Aucun accès    | Aucun accès    | Aucun accès    |

Le RSSI n'accède à aucune donnée métier. Il gère les accès via le rôle serveur `securityadmin`.

### Changement de mot de passe obligatoire

Chaque utilisateur créé a `MUST_CHANGE = ON`. SQL Server force le changement de mot de passe à la première connexion. Les mots de passe initiaux dans les specs ne sont pas les mots de passe définitifs.

---

## Projection et évolutivité

### Volume attendu sur 1 an

Avec 11 villes et un run horaire :

- DimLieux : 11 lignes (stable)
- DimTemps : ~8 760 lignes (24h × 365j)
- FactMesures : ~96 360 lignes (11 villes × 8 760 heures)

C'est un volume très faible pour SQL Server. Les performances ne seront jamais un problème à cette échelle.

### Ce qui changerait avec 500 villes

- FactMesures : ~4.38 millions de lignes/an
- Les non-clustered index deviennent nécessaires
- Le partitionnement de table SQL Server (par mois ou par année) pourrait être envisagé
- Le `fast_executemany` deviendrait critique pour les temps de chargement

### Migration vers le cloud

Le schéma en étoile est compatible avec tous les moteurs cloud :

- Azure Synapse Analytics (successeur cloud de SQL Server)
- Amazon Redshift
- Google BigQuery

La migration consisterait à exporter les tables Gold et recréer les mêmes schémas. Le code Python n'aurait qu'à changer la chaîne de connexion dans `connections.py`.

---

## Résumé des décisions

| Décision                  | Choix                            | Justification                                                 |
| ------------------------- | -------------------------------- | ------------------------------------------------------------- |
| Modèle                    | Star schema (Kimball)            | Optimisé pour les requêtes BI, simple pour les chercheurs     |
| Nombre de tables de faits | 1 (FactMesures)                  | Même grain météo/air, évite les jointures inutiles            |
| Grain                     | 1 ville × 1 heure                | Correspond au rythme du pipeline et à la granularité des APIs |
| Clé technique             | IDENTITY INT                     | Jointures rapides, indépendant des données source             |
| Clé temporelle            | BIGINT YYYYMMDDHH                | Lisible, déterministe, performant                             |
| Schémas                   | Gold, Ref, Staging               | Séparation par fonction et cycle de vie                       |
| Staging                   | Tables sans index ni contraintes | Zone tampon jetable, protège Gold                             |
| Chargement                | MERGE (UPSERT)                   | Idempotent, atomique, préserve DateInsertion                  |
| Index                     | Clustered sur PK uniquement      | Suffisant pour le volume MVP                                  |
| Sécurité                  | Rôles par schéma                 | Simple, héritable, conforme aux specs                         |
| Cascade                   | Non                              | Protection contre les suppressions accidentelles              |
