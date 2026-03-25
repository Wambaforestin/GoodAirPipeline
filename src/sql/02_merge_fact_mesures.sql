-- MERGE : Staging → Gold
-- Exécuté par Python après le chargement des 3 tables staging
-- @IDBatch est injecté par Python (= Airflow Run ID)

USE GoodAirDW;
GO

-- 1. Insérer les nouvelles villes dans DimLieux
INSERT INTO Gold.DimLieux (NomVille, CodePays, Latitude, Longitude)
SELECT s.NomVille, s.CodePays, s.Latitude, s.Longitude
FROM Staging.DimLieux_Temp s
WHERE NOT EXISTS (
    SELECT 1 FROM Gold.DimLieux d WHERE d.NomVille = s.NomVille
);

-- 2. Insérer les nouvelles heures dans DimTemps
INSERT INTO Gold.DimTemps (IDTemps, DateHeure, Annee, Mois, Jour, Heure)
SELECT s.IDTemps, s.DateHeure, s.Annee, s.Mois, s.Jour, s.Heure
FROM Staging.DimTemps_Temp s
WHERE NOT EXISTS (
    SELECT 1 FROM Gold.DimTemps d WHERE d.IDTemps = s.IDTemps
);

-- 3. MERGE FactMesures (résout IDLieu via DimLieux)
MERGE Gold.FactMesures AS target
USING (
    SELECT d.IDLieu, s.IDTemps, s.Temperature, s.Humidite, s.Pression,
           s.VitesseVent, s.AqiGlobal, s.PM25, s.PM10, s.NO2, s.O3,
           s.MeteoStatus, s.AirStatus
    FROM Staging.FactMesures_Temp s
    INNER JOIN Gold.DimLieux d ON d.NomVille = s.NomVille
) AS source
ON target.IDLieu = source.IDLieu AND target.IDTemps = source.IDTemps

WHEN MATCHED THEN UPDATE SET
    target.Temperature = source.Temperature,
    target.Humidite = source.Humidite,
    target.Pression = source.Pression,
    target.VitesseVent = source.VitesseVent,
    target.AqiGlobal = source.AqiGlobal,
    target.PM25 = source.PM25,
    target.PM10 = source.PM10,
    target.NO2 = source.NO2,
    target.O3 = source.O3,
    target.MeteoStatus = source.MeteoStatus,
    target.AirStatus = source.AirStatus,
    target.DateModification = GETDATE()

WHEN NOT MATCHED THEN INSERT (
    IDLieu, IDTemps, Temperature, Humidite, Pression, VitesseVent,
    AqiGlobal, PM25, PM10, NO2, O3,
    MeteoStatus, AirStatus, DateInsertion, DateModification, IDBatch
)
VALUES (
    source.IDLieu, source.IDTemps, source.Temperature, source.Humidite,
    source.Pression, source.VitesseVent, source.AqiGlobal, source.PM25,
    source.PM10, source.NO2, source.O3,
    source.MeteoStatus, source.AirStatus, GETDATE(), GETDATE(), @IDBatch
);