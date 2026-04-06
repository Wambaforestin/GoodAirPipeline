-- Data Catalog - GoodAir Data Warehouse
-- Table de référence décrivant toutes les colonnes du DW

USE GoodAirDW;
GO

CREATE TABLE Ref.DataCatalog (
    IDCatalog INT IDENTITY(1,1) NOT NULL,
    NomSchema VARCHAR(50) NOT NULL,
    NomTable VARCHAR(100) NOT NULL,
    NomColonne VARCHAR(100) NOT NULL,
    TypeSQL VARCHAR(50) NOT NULL,
    SourceAPI VARCHAR(50) NULL,
    CheminJSON VARCHAR(200) NULL,
    Description NVARCHAR(500) NOT NULL,
    Nullable BIT NOT NULL DEFAULT 1,
    CONSTRAINT PK_Ref_DataCatalog PRIMARY KEY CLUSTERED (IDCatalog)
);
GO

-- Gold.DimLieux
INSERT INTO Ref.DataCatalog (NomSchema, NomTable, NomColonne, TypeSQL, SourceAPI, CheminJSON, Description, Nullable)
VALUES
    ('Gold', 'DimLieux', 'IDLieu', 'INT IDENTITY', 'Système', NULL, N'Clé primaire auto-générée', 0),
    ('Gold', 'DimLieux', 'NomVille', 'NVARCHAR(100)', 'OpenWeatherMap', 'name', N'Nom de la ville surveillée', 0),
    ('Gold', 'DimLieux', 'CodePays', 'CHAR(2)', 'OpenWeatherMap', 'sys.country', N'Code ISO du pays (ex: FR)', 1),
    ('Gold', 'DimLieux', 'Latitude', 'DECIMAL(9,6)', 'OpenWeatherMap', 'coord.lat', N'Coordonnée GPS Nord/Sud', 1),
    ('Gold', 'DimLieux', 'Longitude', 'DECIMAL(9,6)', 'OpenWeatherMap', 'coord.lon', N'Coordonnée GPS Est/Ouest', 1);

-- Gold.DimTemps
INSERT INTO Ref.DataCatalog (NomSchema, NomTable, NomColonne, TypeSQL, SourceAPI, CheminJSON, Description, Nullable)
VALUES
    ('Gold', 'DimTemps', 'IDTemps', 'BIGINT', 'Système', NULL, N'Clé temporelle au format YYYYMMDDHH (ex: 2026032514 = 25/03/2026 à 14h)', 0),
    ('Gold', 'DimTemps', 'DateHeure', 'DATETIME', 'Système', NULL, N'Horodatage complet de la mesure', 0),
    ('Gold', 'DimTemps', 'Annee', 'INT', 'Système', NULL, N'Année extraite (ex: 2026)', 1),
    ('Gold', 'DimTemps', 'Mois', 'INT', 'Système', NULL, N'Mois extrait (1-12)', 1),
    ('Gold', 'DimTemps', 'Jour', 'INT', 'Système', NULL, N'Jour du mois (1-31)', 1),
    ('Gold', 'DimTemps', 'Heure', 'INT', 'Système', NULL, N'Heure UTC (0-23)', 1);

-- Gold.FactMesures
INSERT INTO Ref.DataCatalog (NomSchema, NomTable, NomColonne, TypeSQL, SourceAPI, CheminJSON, Description, Nullable)
VALUES
    ('Gold', 'FactMesures', 'IDLieu', 'INT', 'Système', NULL, N'FK vers DimLieux — identifie la ville', 0),
    ('Gold', 'FactMesures', 'IDTemps', 'BIGINT', 'Système', NULL, N'FK vers DimTemps — identifie le créneau horaire', 0),
    ('Gold', 'FactMesures', 'Temperature', 'DECIMAL(5,2)', 'OpenWeatherMap', 'main.temp', N'Température en °C', 1),
    ('Gold', 'FactMesures', 'Humidite', 'INT', 'OpenWeatherMap', 'main.humidity', N'Humidité en % (0-100)', 1),
    ('Gold', 'FactMesures', 'Pression', 'INT', 'OpenWeatherMap', 'main.pressure', N'Pression atmosphérique en hPa', 1),
    ('Gold', 'FactMesures', 'VitesseVent', 'DECIMAL(5,2)', 'OpenWeatherMap', 'wind.speed', N'Vitesse du vent en m/s', 1),
    ('Gold', 'FactMesures', 'AqiGlobal', 'INT', 'AQICN', 'data.aqi', N'Indice global de qualité de l''air', 1),
    ('Gold', 'FactMesures', 'PM25', 'DECIMAL(6,2)', 'AQICN', 'data.iaqi.pm25.v', N'Indice AQI des particules fines PM2.5 (échelle 0-500). Attention : cette valeur est un indice AQI, pas une concentration en µg/m³. La comparaison directe avec les seuils OMS (exprimés en µg/m³) nécessite une conversion.', 1),
    ('Gold', 'FactMesures', 'PM10', 'DECIMAL(6,2)', 'AQICN', 'data.iaqi.pm10.v', N'Indice AQI des particules PM10 (échelle 0-500). Même remarque : valeur AQI, pas µg/m³.', 1),
    ('Gold', 'FactMesures', 'NO2', 'DECIMAL(6,2)', 'AQICN', 'data.iaqi.no2.v', N'Indice AQI du dioxyde d''azote (échelle 0-500). Même remarque : valeur AQI, pas µg/m³.', 1),
    ('Gold', 'FactMesures', 'O3', 'DECIMAL(6,2)', 'AQICN', 'data.iaqi.o3.v', N'Indice AQI de l''ozone troposphérique (échelle 0-500). Même remarque : valeur AQI, pas µg/m³.', 1),
    ('Gold', 'FactMesures', 'MeteoStatus', 'VARCHAR(20)', 'Pipeline', NULL, N'OK si au moins une donnée météo reçue, FAILED si aucune', 0),
    ('Gold', 'FactMesures', 'AirStatus', 'VARCHAR(20)', 'Pipeline', NULL, N'OK si au moins une donnée air reçue, FAILED si aucune', 0),
    ('Gold', 'FactMesures', 'DateInsertion', 'DATETIME2', 'Système', NULL, N'Date de première insertion dans Gold', 0),
    ('Gold', 'FactMesures', 'DateModification', 'DATETIME2', 'Système', NULL, N'Date de dernière mise à jour (MERGE)', 0),
    ('Gold', 'FactMesures', 'IDBatch', 'VARCHAR(100)', 'Airflow', NULL, N'Run ID Airflow pour traçabilité et rollback', 0);

-- Ref.Pays
INSERT INTO Ref.DataCatalog (NomSchema, NomTable, NomColonne, TypeSQL, SourceAPI, CheminJSON, Description, Nullable)
VALUES
    ('Ref', 'Pays', 'CodePays', 'CHAR(2)', 'Référentiel', NULL, N'Code ISO 3166-1 du pays (ex: FR)', 0),
    ('Ref', 'Pays', 'NomPays', 'NVARCHAR(100)', 'Référentiel', NULL, N'Nom complet du pays (ex: France)', 0);

-- Ref.SeuilsOMS
INSERT INTO Ref.DataCatalog (NomSchema, NomTable, NomColonne, TypeSQL, SourceAPI, CheminJSON, Description, Nullable)
VALUES
    ('Ref', 'SeuilsOMS', 'IDSeuil', 'INT IDENTITY', 'Système', NULL, N'Clé primaire auto-générée', 0),
    ('Ref', 'SeuilsOMS', 'Polluant', 'VARCHAR(20)', 'Référentiel', NULL, N'Nom du polluant (PM2.5, PM10, NO2, O3)', 0),
    ('Ref', 'SeuilsOMS', 'PeriodeReference', 'VARCHAR(50)', 'Référentiel', NULL, N'Période de mesure (Moyenne 24h, Moyenne 8h)', 0),
    ('Ref', 'SeuilsOMS', 'SeuilLimite', 'DECIMAL(6,2)', 'Référentiel', NULL, N'Valeur seuil en µg/m³', 0),
    ('Ref', 'SeuilsOMS', 'UniteMesure', 'VARCHAR(20)', 'Référentiel', NULL, N'Unité de mesure (µg/m³)', 0),
    ('Ref', 'SeuilsOMS', 'NiveauDanger', 'NVARCHAR(50)', 'Référentiel', NULL, N'Classification du seuil (Limite OMS, Danger)', 0),
    ('Ref', 'SeuilsOMS', 'Description', 'NVARCHAR(255)', 'Référentiel', NULL, N'Explication de l''impact sanitaire', 1);
GO

----- Ajout des colonnes d'audit à Ref.DataCatalog
ALTER TABLE Ref.DataCatalog ADD
    DateInsertion DATE NOT NULL DEFAULT '2026-03-29',
    DateMiseAJour DATE NOT NULL DEFAULT CAST(GETDATE() AS DATE);
GO

-- Insertion des métadonnées d'audit pour les tables et colonnes existantes
INSERT INTO Ref.DataCatalog (NomSchema, NomTable, NomColonne, TypeSQL, SourceAPI, CheminJSON, Description, Nullable)
VALUES
    ('Ref', 'SeuilsOMS', 'DateInsertion', 'DATE', N'Système', NULL, N'Date d''insertion du seuil dans la table', 0),
    ('Ref', 'SeuilsOMS', 'DateMiseAJour', 'DATE', N'Système', NULL, N'Date de dernière modification du seuil', 0),
    ('Ref', 'DataCatalog', 'DateInsertion', 'DATE', N'Système', NULL, N'Date d''insertion de l''entrée dans le catalogue', 0),
    ('Ref', 'DataCatalog', 'DateMiseAJour', 'DATE', N'Système', NULL, N'Date de dernière modification de l''entrée', 0);
GO