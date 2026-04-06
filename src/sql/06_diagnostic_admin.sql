-- Diagnostic et Administration - GoodAir Data Warehouse
USE GoodAirDW;
GO

-- ESPACE ET STOCKAGE

-- Taille globale de la base
EXEC sp_spaceused;
GO

-- Taille par table (données + index)
SELECT 
    s.name + '.' + t.name AS NomTable,
    SUM(p.rows) AS NbLignes,
    CAST(SUM(a.total_pages) * 8.0 / 1024 AS DECIMAL(10,2)) AS TailleTotaleMB,
    CAST(SUM(a.used_pages) * 8.0 / 1024 AS DECIMAL(10,2)) AS TailleUtiliseeMB
FROM sys.tables t
INNER JOIN sys.schemas s ON t.schema_id = s.schema_id
INNER JOIN sys.partitions p ON t.object_id = p.object_id
INNER JOIN sys.allocation_units a ON p.partition_id = a.container_id
WHERE p.index_id IN (0, 1)
GROUP BY s.name, t.name
ORDER BY TailleTotaleMB DESC;
GO

-- INDEX

-- Liste de tous les index
SELECT 
    s.name + '.' + t.name AS NomTable,
    i.name AS NomIndex,
    i.type_desc AS TypeIndex,
    COL_NAME(ic.object_id, ic.column_id) AS Colonne
FROM sys.indexes i
INNER JOIN sys.tables t ON i.object_id = t.object_id
INNER JOIN sys.schemas s ON t.schema_id = s.schema_id
INNER JOIN sys.index_columns ic ON i.object_id = ic.object_id AND i.index_id = ic.index_id
WHERE i.name IS NOT NULL
ORDER BY s.name, t.name, i.index_id, ic.key_ordinal;
GO

-- SCHEMAS ET TABLES

-- Liste de toutes les tables par schéma
SELECT s.name AS NomSchema, t.name AS NomTable, t.create_date AS DateCreation
FROM sys.tables t
INNER JOIN sys.schemas s ON t.schema_id = s.schema_id
ORDER BY s.name, t.name;
GO

-- Colonnes de toutes les tables
SELECT 
    TABLE_SCHEMA AS NomSchema,
    TABLE_NAME AS NomTable,
    COLUMN_NAME AS NomColonne,
    DATA_TYPE AS TypeDonnee,
    IS_NULLABLE AS Nullable,
    COLUMN_DEFAULT AS ValeurDefaut
FROM INFORMATION_SCHEMA.COLUMNS
ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION;
GO

-- Contraintes (PK, FK, CHECK)
SELECT 
    s.name + '.' + t.name AS NomTable,
    c.name AS NomContrainte,
    c.type_desc AS TypeContrainte
FROM sys.key_constraints c
INNER JOIN sys.tables t ON c.parent_object_id = t.object_id
INNER JOIN sys.schemas s ON t.schema_id = s.schema_id
UNION ALL
SELECT 
    s.name + '.' + t.name,
    fk.name,
    'FOREIGN_KEY'
FROM sys.foreign_keys fk
INNER JOIN sys.tables t ON fk.parent_object_id = t.object_id
INNER JOIN sys.schemas s ON t.schema_id = s.schema_id
UNION ALL
SELECT 
    s.name + '.' + t.name,
    cc.name,
    'CHECK_CONSTRAINT'
FROM sys.check_constraints cc
INNER JOIN sys.tables t ON cc.parent_object_id = t.object_id
INNER JOIN sys.schemas s ON t.schema_id = s.schema_id
ORDER BY NomTable, TypeContrainte;
GO

-- SECURITE

-- Tous les logins serveur
SELECT name AS NomLogin, type_desc AS TypeLogin, create_date AS DateCreation, is_disabled AS Desactive
FROM sys.server_principals
WHERE type IN ('S', 'U')
ORDER BY name;
GO

-- Utilisateurs de la base et leurs rôles
SELECT 
    dp.name AS NomUtilisateur,
    dp.type_desc AS TypeUtilisateur,
    r.name AS Role,
    dp.create_date AS DateCreation
FROM sys.database_principals dp
LEFT JOIN sys.database_role_members drm ON dp.principal_id = drm.member_principal_id
LEFT JOIN sys.database_principals r ON drm.role_principal_id = r.principal_id
WHERE dp.type IN ('S', 'U') AND dp.name NOT IN ('dbo', 'guest', 'INFORMATION_SCHEMA', 'sys')
ORDER BY dp.name;
GO

-- Permissions par schéma
SELECT 
    pr.name AS NomRole,
    pe.permission_name AS Permission,
    pe.state_desc AS Etat,
    s.name AS NomSchema
FROM sys.database_permissions pe
INNER JOIN sys.database_principals pr ON pe.grantee_principal_id = pr.principal_id
INNER JOIN sys.schemas s ON pe.major_id = s.schema_id
WHERE pe.class = 3
ORDER BY pr.name, s.name;
GO

-- MONITORING PIPELINE COTE BASE DE DONNEES

-- Nombre de lignes par créneau horaire
SELECT IDTemps, COUNT(*) AS NbVilles
FROM Gold.FactMesures
GROUP BY IDTemps
ORDER BY IDTemps DESC;
GO

-- Créneaux manquants (trous dans les données)
SELECT 
    t1.IDTemps AS DernierCreneau,
    t2.IDTemps AS ProchainCreneau,
    t2.IDTemps - t1.IDTemps - 1 AS NbCreneauxManquants
FROM Gold.DimTemps t1
INNER JOIN Gold.DimTemps t2 ON t2.IDTemps = (
    SELECT MIN(IDTemps) FROM Gold.DimTemps WHERE IDTemps > t1.IDTemps
)
WHERE t2.IDTemps - t1.IDTemps > 1
ORDER BY t1.IDTemps;
GO

-- Dernière exécution du pipeline
SELECT TOP 1 
    t.DateHeure AS DerniereMesure,
    f.DateInsertion,
    f.IDBatch
FROM Gold.FactMesures f
INNER JOIN Gold.DimTemps t ON f.IDTemps = t.IDTemps
ORDER BY f.DateInsertion DESC;
GO

-- Taux de disponibilité par ville
SELECT 
    l.NomVille,
    COUNT(*) AS TotalRuns,
    SUM(CASE WHEN f.MeteoStatus = 'OK' AND f.AirStatus = 'OK' THEN 1 ELSE 0 END) AS RunsComplets,
    CAST(SUM(CASE WHEN f.MeteoStatus = 'OK' AND f.AirStatus = 'OK' THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS DECIMAL(5,1)) AS PctDisponibilite
FROM Gold.FactMesures f
INNER JOIN Gold.DimLieux l ON f.IDLieu = l.IDLieu
GROUP BY l.NomVille
ORDER BY PctDisponibilite;
GO

-- Pannes par source (MeteoStatus ou AirStatus = FAILED)
SELECT 
    l.NomVille,
    SUM(CASE WHEN f.MeteoStatus = 'FAILED' THEN 1 ELSE 0 END) AS PannesMeteo,
    SUM(CASE WHEN f.AirStatus = 'FAILED' THEN 1 ELSE 0 END) AS PannesAir
FROM Gold.FactMesures f
INNER JOIN Gold.DimLieux l ON f.IDLieu = l.IDLieu
GROUP BY l.NomVille
ORDER BY PannesMeteo + PannesAir DESC;
GO

-- Contenu des tables staging (devrait être vide entre les runs)
SELECT 'DimLieux_Temp' AS TableStaging, COUNT(*) AS NbLignes FROM Staging.DimLieux_Temp
UNION ALL
SELECT 'DimTemps_Temp', COUNT(*) FROM Staging.DimTemps_Temp
UNION ALL
SELECT 'FactMesures_Temp', COUNT(*) FROM Staging.FactMesures_Temp;
GO