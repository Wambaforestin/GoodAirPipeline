USE GoodAirDW;
GO

-- Dimensions et Faits
SELECT * FROM Gold.DimLieux;
SELECT * FROM Gold.DimTemps;
SELECT * FROM Gold.FactMesures;

-- Runs manuels vs schedulés (exemples de lignes)
SELECT * FROM Gold.FactMesures WHERE IDBatch LIKE 'manual%';
SELECT * FROM Gold.FactMesures WHERE IDBatch LIKE 'scheduled%';

-- Seuils OMS de référence
SELECT * FROM Ref.SeuilsOMS;

-- Pays de référence
SELECT * FROM Ref.Pays;

-- Data Catalog : toutes les colonnes du DW
SELECT * FROM Ref.DataCatalog ORDER BY NomSchema, NomTable, IDCatalog;

-- Data Catalog : colonnes d'une table spécifique
SELECT NomColonne, TypeSQL, SourceAPI, CheminJSON, Description
FROM Ref.DataCatalog
WHERE NomTable = 'FactMesures'
ORDER BY IDCatalog;

-- Data Catalog : provenance par API
SELECT NomTable, NomColonne, CheminJSON, Description
FROM Ref.DataCatalog
WHERE SourceAPI = 'AQICN';

SELECT NomTable, NomColonne, CheminJSON, Description
FROM Ref.DataCatalog
WHERE SourceAPI = 'OpenWeatherMap';

-- Nombre total de mesures collectées
SELECT COUNT(*) AS [Nombre total de mesures] FROM Gold.FactMesures;

-- Nombre de créneaux horaires couverts
SELECT COUNT(DISTINCT IDTemps) AS [Nombre de créneaux horaires] FROM Gold.FactMesures;

-- Nombre de villes suivies
SELECT COUNT(*) AS [Nombre de villes suivies] FROM Gold.DimLieux;

-- Nombre de runs schedulés vs manuels (comptage d'exécutions)
SELECT 
    CASE WHEN IDBatch LIKE 'scheduled%' THEN N'Schedulé' ELSE N'Manuel' END AS [Type de run],
    COUNT(DISTINCT IDBatch) AS [Nombre d''exécutions]
FROM Gold.FactMesures
GROUP BY CASE WHEN IDBatch LIKE 'scheduled%' THEN N'Schedulé' ELSE N'Manuel' END;

-- Taux de disponibilité global (les deux APIs ont répondu)
SELECT 
    CAST(SUM(CASE WHEN MeteoStatus = 'OK' AND AirStatus = 'OK' THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS DECIMAL(5,1)) AS [Taux de disponibilité global (%)]
FROM Gold.FactMesures;

-- Plage temporelle couverte
SELECT 
    MIN(DateHeure) AS [Première mesure],
    MAX(DateHeure) AS [Dernière mesure],
    DATEDIFF(DAY, MIN(DateHeure), MAX(DateHeure)) AS [Nombre de jours de collecte],
    DATEDIFF(HOUR, MIN(DateHeure), MAX(DateHeure)) AS [Nombre d''heures de collecte]
FROM Gold.DimTemps;

-- Taille de la base de données
EXEC sp_spaceused;

-- Taux de disponibilité par ville (pourcentage de runs avec données complètes)
SELECT l.NomVille,
    COUNT(*) AS TotalRuns,
    SUM(CASE WHEN f.MeteoStatus = 'OK' AND f.AirStatus = 'OK' THEN 1 ELSE 0 END) AS RunsComplets,
    CAST(SUM(CASE WHEN f.MeteoStatus = 'OK' AND f.AirStatus = 'OK' THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS DECIMAL(5,1)) AS PctDisponibilite
FROM Gold.FactMesures f
INNER JOIN Gold.DimLieux l ON f.IDLieu = l.IDLieu
GROUP BY l.NomVille
ORDER BY PctDisponibilite;

-- Température moyenne par ville (min/max/moy)
SELECT 
    l.NomVille AS [Ville],
    CAST(AVG(f.Temperature) AS DECIMAL(5,2)) AS [Température moyenne (°C)],
    CAST(MIN(f.Temperature) AS DECIMAL(5,2)) AS [Température min (°C)],
    CAST(MAX(f.Temperature) AS DECIMAL(5,2)) AS [Température max (°C)]
FROM Gold.FactMesures f
INNER JOIN Gold.DimLieux l ON f.IDLieu = l.IDLieu
WHERE f.Temperature IS NOT NULL
GROUP BY l.NomVille
ORDER BY [Température moyenne (°C)] DESC;

-- Qualité de l'air moyenne par ville
SELECT 
    l.NomVille AS [Ville],
    CAST(AVG(f.AqiGlobal) AS INT) AS [AQI moyen],
    CAST(AVG(f.PM25) AS DECIMAL(6,2)) AS [PM2.5 moyen],
    CASE 
        WHEN AVG(f.AqiGlobal) <= 50 THEN N'Bon'
        WHEN AVG(f.AqiGlobal) <= 100 THEN N'Modéré'
        WHEN AVG(f.AqiGlobal) <= 150 THEN N'Mauvais pour groupes sensibles'
        ELSE N'Mauvais'
    END AS [Qualité de l''air]
FROM Gold.FactMesures f
INNER JOIN Gold.DimLieux l ON f.IDLieu = l.IDLieu
WHERE f.AqiGlobal IS NOT NULL
GROUP BY l.NomVille
ORDER BY [AQI moyen] DESC;

-- Nombre de villes par créneau horaire (vérification de complétude)
SELECT 
    IDTemps AS [Créneau horaire],
    COUNT(*) AS [Nombre de villes]
FROM Gold.FactMesures
GROUP BY IDTemps
ORDER BY IDTemps DESC;

-- Les 22 dernières mesures (2 derniers créneaux)
SELECT TOP 22 
    f.IDTemps AS [Créneau],
    l.NomVille AS [Ville],
    f.Temperature AS [Temp (°C)],
    f.Humidite AS [Humidité (%)],
    f.AqiGlobal AS [AQI],
    f.MeteoStatus AS [Statut Météo],
    f.AirStatus AS [Statut Air],
    f.DateInsertion AS [Date d''insertion]
FROM Gold.FactMesures f
INNER JOIN Gold.DimLieux l ON f.IDLieu = l.IDLieu
ORDER BY f.IDTemps DESC;

-- Pannes partielles : lignes où une des deux API n'a pas répondu
SELECT l.NomVille, t.DateHeure, f.MeteoStatus, f.AirStatus
FROM Gold.FactMesures f
INNER JOIN Gold.DimLieux l ON f.IDLieu = l.IDLieu
INNER JOIN Gold.DimTemps t ON f.IDTemps = t.IDTemps
WHERE f.MeteoStatus = 'FAILED' OR f.AirStatus = 'FAILED'
ORDER BY t.DateHeure DESC;

-- Comparer les mesures aux seuils OMS (PM2.5)
SELECT l.NomVille, t.DateHeure, f.PM25, s.SeuilLimite, s.NiveauDanger,
    CASE WHEN f.PM25 > s.SeuilLimite THEN 'DEPASSEMENT' ELSE 'OK' END AS StatutOMS
FROM Gold.FactMesures f
INNER JOIN Gold.DimLieux l ON f.IDLieu = l.IDLieu
INNER JOIN Gold.DimTemps t ON f.IDTemps = t.IDTemps
CROSS JOIN Ref.SeuilsOMS s
WHERE s.Polluant = 'PM2.5' AND s.NiveauDanger = 'Limite OMS'
    AND f.PM25 IS NOT NULL
ORDER BY t.DateHeure DESC;

-- Villes en dépassement OMS (au moins une fois)
SELECT l.NomVille, COUNT(*) AS NbDepassements
FROM Gold.FactMesures f
INNER JOIN Gold.DimLieux l ON f.IDLieu = l.IDLieu
CROSS JOIN Ref.SeuilsOMS s
WHERE s.Polluant = 'PM2.5' AND s.NiveauDanger = 'Limite OMS'
    AND f.PM25 > s.SeuilLimite
GROUP BY l.NomVille
ORDER BY NbDepassements DESC;

-- Nombre de créneaux manquants (trous dans la collecte)
SELECT COUNT(*) AS [Nombre de trous dans les données]
FROM Gold.DimTemps t1
INNER JOIN Gold.DimTemps t2 ON t2.IDTemps = (
    SELECT MIN(IDTemps) FROM Gold.DimTemps WHERE IDTemps > t1.IDTemps
)
WHERE t2.IDTemps - t1.IDTemps > 1;

-- Dernier run exécuté
SELECT TOP 1 
    IDBatch AS [Dernier batch],
    DateModification AS [Dernière modification]
FROM Gold.FactMesures
ORDER BY DateModification DESC;


-- Toutes les prédictions actuelles
SELECT 
    l.NomVille,
    a.DateHeurePredite,
    a.AQI_Predit,
    a.Alerte,
    a.DatePrediction,
    a.IDBatch
FROM Gold.AlertesPredites a
INNER JOIN Gold.DimLieux l ON a.IDLieu = l.IDLieu
ORDER BY a.DateHeurePredite, l.NomVille;

-- Prédictions par ville pour les prochaines heures
SELECT 
    l.NomVille,
    a.DateHeurePredite,
    a.AQI_Predit,
    a.Alerte
FROM Gold.AlertesPredites a
INNER JOIN Gold.DimLieux l ON a.IDLieu = l.IDLieu
WHERE a.DateHeurePredite >= GETDATE()
ORDER BY l.NomVille, a.DateHeurePredite;

-- Alertes uniquement
SELECT 
    l.NomVille,
    a.DateHeurePredite,
    a.AQI_Predit,
    a.DatePrediction
FROM Gold.AlertesPredites a
INNER JOIN Gold.DimLieux l ON a.IDLieu = l.IDLieu
WHERE a.Alerte = 'ALERTE'
ORDER BY a.DateHeurePredite;

-- AQI moyen prédit par ville
SELECT 
    l.NomVille,
    ROUND(AVG(a.AQI_Predit), 2) AS AQI_Moyen_Predit,
    COUNT(*) AS NbPredictions
FROM Gold.AlertesPredites a
INNER JOIN Gold.DimLieux l ON a.IDLieu = l.IDLieu
GROUP BY l.NomVille
ORDER BY AQI_Moyen_Predit DESC;

-- Dernière prédiction par ville
SELECT 
    l.NomVille,
    MAX(a.DateHeurePredite) AS DernierHoraire,
    MAX(a.DatePrediction)   AS DernierRun
FROM Gold.AlertesPredites a
INNER JOIN Gold.DimLieux l ON a.IDLieu = l.IDLieu
GROUP BY l.NomVille
ORDER BY l.NomVille;