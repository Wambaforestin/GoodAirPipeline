USE GoodAirDW;
GO

-- Dimensions et Faits
SELECT * FROM Gold.DimLieux;
SELECT * FROM Gold.DimTemps;
SELECT * FROM Gold.FactMesures;

-- Nombre total de lignes dans FactMesures
SELECT COUNT(*) AS NbLignes FROM Gold.FactMesures;

-- Nombre de villes par créneau horaire
SELECT IDTemps, COUNT(*) AS NbVilles
FROM Gold.FactMesures
GROUP BY IDTemps
ORDER BY IDTemps;

-- Runs manuels vs schedulés
SELECT * FROM Gold.FactMesures WHERE IDBatch LIKE 'manual%';
SELECT * FROM Gold.FactMesures WHERE IDBatch LIKE 'scheduled%';

-- Dernières données insérées
SELECT TOP 10 f.IDTemps, l.NomVille, f.Temperature, f.AqiGlobal, f.MeteoStatus, f.AirStatus, f.DateInsertion
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

-- Température moyenne par ville
SELECT l.NomVille, AVG(f.Temperature) AS TempMoyenne, COUNT(*) AS NbMesures
FROM Gold.FactMesures f
INNER JOIN Gold.DimLieux l ON f.IDLieu = l.IDLieu
WHERE f.Temperature IS NOT NULL
GROUP BY l.NomVille
ORDER BY TempMoyenne DESC;

-- Qualité de l'air moyenne par ville (PM2.5)
SELECT l.NomVille, AVG(f.PM25) AS PM25Moyen, AVG(f.AqiGlobal) AS AqiMoyen
FROM Gold.FactMesures f
INNER JOIN Gold.DimLieux l ON f.IDLieu = l.IDLieu
WHERE f.PM25 IS NOT NULL
GROUP BY l.NomVille
ORDER BY PM25Moyen DESC;

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

-- Data Catalog : tout ce qui vient d'AQICN
SELECT NomTable, NomColonne, CheminJSON, Description
FROM Ref.DataCatalog
WHERE SourceAPI = 'AQICN';

-- Data Catalog : tout ce qui vient d'OpenWeatherMap
SELECT NomTable, NomColonne, CheminJSON, Description
FROM Ref.DataCatalog
WHERE SourceAPI = 'OpenWeatherMap';

-- Taux de disponibilité par ville (pourcentage de runs avec données complètes)
SELECT l.NomVille,
    COUNT(*) AS TotalRuns,
    SUM(CASE WHEN f.MeteoStatus = 'OK' AND f.AirStatus = 'OK' THEN 1 ELSE 0 END) AS RunsComplets,
    CAST(SUM(CASE WHEN f.MeteoStatus = 'OK' AND f.AirStatus = 'OK' THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS DECIMAL(5,1)) AS PctDisponibilite
FROM Gold.FactMesures f
INNER JOIN Gold.DimLieux l ON f.IDLieu = l.IDLieu
GROUP BY l.NomVille
ORDER BY PctDisponibilite;

-- Dernier batch exécuté
SELECT TOP 1 IDBatch, DateModification
FROM Gold.FactMesures
ORDER BY DateModification DESC;