-- Script DDL complet - GoodAir Data Warehouse
-- SGBD : SQL Server 2022

-- Création de la base de données
IF NOT EXISTS (SELECT * FROM sys.databases WHERE name = 'GoodAirDW')
BEGIN
    CREATE DATABASE GoodAirDW;
END
GO
USE GoodAirDW;
GO

-- Création des schémas
IF NOT EXISTS (SELECT * FROM sys.schemas WHERE name = 'Gold')
    EXEC('CREATE SCHEMA Gold');
GO
IF NOT EXISTS (SELECT * FROM sys.schemas WHERE name = 'Ref')
    EXEC('CREATE SCHEMA Ref');
GO
IF NOT EXISTS (SELECT * FROM sys.schemas WHERE name = 'Staging')
    EXEC('CREATE SCHEMA Staging');
GO

-- Table de référence : Pays (codes ISO)
CREATE TABLE Ref.Pays (
    CodePays CHAR(2) NOT NULL,
    NomPays NVARCHAR(100) NOT NULL,
    CONSTRAINT PK_Ref_Pays PRIMARY KEY CLUSTERED (CodePays)
);
GO

INSERT INTO Ref.Pays (CodePays, NomPays)
VALUES ('FR', N'France');
GO

-- Table de référence : Seuils OMS

CREATE TABLE Ref.SeuilsOMS (
    IDSeuil INT IDENTITY(1,1) NOT NULL,
    Polluant VARCHAR(20) NOT NULL,
    PeriodeReference VARCHAR(50) NOT NULL,
    SeuilLimite DECIMAL(6,2) NOT NULL,
    UniteMesure VARCHAR(20) NOT NULL,
    NiveauDanger NVARCHAR(50) NOT NULL,
    Description NVARCHAR(255) NULL,
    DateInsertion DATE NOT NULL DEFAULT CAST(GETDATE() AS DATE),
    DateMiseAJour DATE NOT NULL DEFAULT CAST(GETDATE() AS DATE),
    CONSTRAINT PK_Ref_SeuilsOMS PRIMARY KEY CLUSTERED (IDSeuil)
);
GO

INSERT INTO Ref.SeuilsOMS (Polluant, PeriodeReference, SeuilLimite, UniteMesure, NiveauDanger, Description)
VALUES
    ('PM2.5', 'Moyenne 24h', 15.00, N'µg/m³', N'Limite OMS', N'Au-delà, risque accru de maladies cardiovasculaires et respiratoires.'),
    ('PM2.5', 'Moyenne 24h', 25.00, N'µg/m³', N'Danger', N'Seuil critique, impact sanitaire immédiat.'),
    ('PM10', 'Moyenne 24h', 45.00, N'µg/m³', N'Limite OMS', N'Irritation des voies respiratoires.'),
    ('NO2', 'Moyenne 24h', 25.00, N'µg/m³', N'Limite OMS', N'Toxique. Principalement lié au trafic routier.'),
    ('O3', 'Moyenne 8h', 100.00, N'µg/m³', N'Limite OMS', N'Ozone troposphérique, déclenche des crises d''asthme.');
GO

-- Dimension : Lieux
CREATE TABLE Gold.DimLieux (
    IDLieu INT IDENTITY(1,1) NOT NULL,
    NomVille NVARCHAR(100) NOT NULL,
    CodePays CHAR(2) NULL,
    Latitude DECIMAL(9,6) NULL,
    Longitude DECIMAL(9,6) NULL,
    CONSTRAINT PK_Gold_DimLieux PRIMARY KEY CLUSTERED (IDLieu)
);
GO

-- Dimension : Temps (calendrier horaire)
CREATE TABLE Gold.DimTemps (
    IDTemps BIGINT NOT NULL,
    DateHeure DATETIME NOT NULL,
    Annee INT NULL,
    Mois INT NULL,
    Jour INT NULL,
    Heure INT NULL,
    CONSTRAINT PK_Gold_DimTemps PRIMARY KEY CLUSTERED (IDTemps),
    CONSTRAINT CK_Gold_DimTemps_Mois CHECK (Mois BETWEEN 1 AND 12),
    CONSTRAINT CK_Gold_DimTemps_Heure CHECK (Heure BETWEEN 0 AND 23)
);
GO

-- Faits : Mesures (table centrale du star schema)
CREATE TABLE Gold.FactMesures (
    IDLieu INT NOT NULL,
    IDTemps BIGINT NOT NULL,
    Temperature DECIMAL(5,2) NULL,
    Humidite INT NULL,
    Pression INT NULL,
    VitesseVent DECIMAL(5,2) NULL,
    AqiGlobal INT NULL,
    PM25 DECIMAL(6,2) NULL,
    PM10 DECIMAL(6,2) NULL,
    NO2 DECIMAL(6,2) NULL,
    O3 DECIMAL(6,2) NULL,
    CONSTRAINT PK_Gold_FactMesures PRIMARY KEY CLUSTERED (IDLieu, IDTemps),
    CONSTRAINT FK_FactMesures_DimLieux FOREIGN KEY (IDLieu) REFERENCES Gold.DimLieux(IDLieu),
    CONSTRAINT FK_FactMesures_DimTemps FOREIGN KEY (IDTemps) REFERENCES Gold.DimTemps(IDTemps),
    CONSTRAINT CK_FactMesures_Humidite CHECK (Humidite BETWEEN 0 AND 100)
);
GO

-- Colonnes d'audit et statuts sur FactMesures
ALTER TABLE Gold.FactMesures ADD
    MeteoStatus VARCHAR(20) NOT NULL DEFAULT 'OK',
    AirStatus VARCHAR(20) NOT NULL DEFAULT 'OK',
    DateInsertion DATETIME2 NOT NULL DEFAULT GETDATE(),
    DateModification DATETIME2 NOT NULL DEFAULT GETDATE(),
    IDBatch VARCHAR(100) NOT NULL DEFAULT 'MANUAL_LOAD';
GO

-- Staging : tables temporaires sans index pour l'UPSERT
CREATE TABLE Staging.DimLieux_Temp (
    NomVille NVARCHAR(100),
    CodePays CHAR(2),
    Latitude DECIMAL(9,6),
    Longitude DECIMAL(9,6)
);
GO

CREATE TABLE Staging.DimTemps_Temp (
    IDTemps BIGINT,
    DateHeure DATETIME,
    Annee INT,
    Mois INT,
    Jour INT,
    Heure INT
);
GO

CREATE TABLE Staging.FactMesures_Temp (
    NomVille NVARCHAR(100),
    IDTemps BIGINT,
    Temperature DECIMAL(5,2),
    Humidite INT,
    Pression INT,
    VitesseVent DECIMAL(5,2),
    AqiGlobal INT,
    PM25 DECIMAL(6,2),
    PM10 DECIMAL(6,2),
    NO2 DECIMAL(6,2),
    O3 DECIMAL(6,2),
    MeteoStatus VARCHAR(20),
    AirStatus VARCHAR(20)
);
GO