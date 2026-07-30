-- Data Catalogue GoodAir Modélisation normalisée (3NF)
-- Schéma : Ref
-- Tables : Schema, Table, Colonne, Source, ColonneSource, Utilisateur, Audit

USE GoodAirDW;
GO

-- 1. Ref.CatalogSchema: Les schémas de la base de données
CREATE TABLE Ref.CatalogSchema (
    IDSchema    INT           NOT NULL IDENTITY(1,1),
    NomSchema   NVARCHAR(100) NOT NULL,
    Description NVARCHAR(500)     NULL,
    DateCreation DATETIME2    NOT NULL DEFAULT GETDATE(),
    CONSTRAINT PK_CatalogSchema PRIMARY KEY (IDSchema),
    CONSTRAINT UQ_CatalogSchema_Nom UNIQUE (NomSchema)
);
GO

-- 2. Ref.CatalogTable: Les tables par schéma
CREATE TABLE Ref.CatalogTable (
    IDTable      INT           NOT NULL IDENTITY(1,1),
    IDSchema     INT           NOT NULL,
    NomTable     NVARCHAR(200) NOT NULL,
    Description  NVARCHAR(1000)    NULL,
    NbColonnes   INT               NULL,
    DateCreation DATETIME2     NOT NULL DEFAULT GETDATE(),
    CONSTRAINT PK_CatalogTable PRIMARY KEY (IDTable),
    CONSTRAINT FK_CatalogTable_Schema
        FOREIGN KEY (IDSchema) REFERENCES Ref.CatalogSchema(IDSchema),
    CONSTRAINT UQ_CatalogTable_Nom UNIQUE (IDSchema, NomTable)
);
GO

-- 3. Ref.CatalogColonne: Les colonnes par table
CREATE TABLE Ref.CatalogColonne (
    IDColonne    INT           NOT NULL IDENTITY(1,1),
    IDTable      INT           NOT NULL,
    NomColonne   NVARCHAR(200) NOT NULL,
    TypeSQL      NVARCHAR(100) NOT NULL,
    Description  NVARCHAR(1000)    NULL,
    IsNullable   BIT           NOT NULL DEFAULT 1,
    ValeurExemple NVARCHAR(500)    NULL,
    Ordre        INT           NOT NULL DEFAULT 0,
    CONSTRAINT PK_CatalogColonne PRIMARY KEY (IDColonne),
    CONSTRAINT FK_CatalogColonne_Table
        FOREIGN KEY (IDTable) REFERENCES Ref.CatalogTable(IDTable),
    CONSTRAINT UQ_CatalogColonne_Nom UNIQUE (IDTable, NomColonne)
);
GO

-- 4. Ref.CatalogSource: Les sources de données
CREATE TABLE Ref.CatalogSource (
    IDSource        INT           NOT NULL IDENTITY(1,1),
    NomSource       NVARCHAR(200) NOT NULL,
    TypeSource      NVARCHAR(100) NOT NULL,  -- API | Pipeline | Modèle
    URLSource      NVARCHAR(500)      NULL,  -- URL de l API ou endpoint
    CheminDataLake  NVARCHAR(500)     NULL,
    Description     NVARCHAR(1000)    NULL,
    IsActive        BIT           NOT NULL DEFAULT 1,
    CONSTRAINT PK_CatalogSource PRIMARY KEY (IDSource),
    CONSTRAINT UQ_CatalogSource_Nom UNIQUE (NomSource),
    CONSTRAINT CHK_CatalogSource_TypeSource
    CHECK (TypeSource IN ('API', 'Pipeline', 'Modele'))
);
GO

-- 5. Ref.CatalogColonneSource: Liaison Colonne ↔ Source (many to many)
CREATE TABLE Ref.CatalogColonneSource (
    IDColonne INT NOT NULL,
    IDSource  INT NOT NULL,
    CheminSource NVARCHAR(500) NULL,  -- ex: main.humidity, data.iaqi.pm25.v
    CONSTRAINT PK_CatalogColonneSource PRIMARY KEY (IDColonne, IDSource),
    CONSTRAINT FK_ColonneSource_Colonne
        FOREIGN KEY (IDColonne) REFERENCES Ref.CatalogColonne(IDColonne),
    CONSTRAINT FK_ColonneSource_Source
        FOREIGN KEY (IDSource)  REFERENCES Ref.CatalogSource(IDSource)
);
GO

-- 6. Ref.CatalogUtilisateur: Les utilisateurs et leurs rôles
CREATE TABLE Ref.CatalogUtilisateur (
    IDUtilisateur INT           NOT NULL IDENTITY(1,1),
    Nom           NVARCHAR(200) NOT NULL,
    Email         NVARCHAR(200) NOT NULL,
    Role          NVARCHAR(50)  NOT NULL,  -- DataEngineer | ExpertMetier | Chercheur
    DateCreation  DATETIME2     NOT NULL DEFAULT GETDATE(),
    CONSTRAINT PK_CatalogUtilisateur PRIMARY KEY (IDUtilisateur),
    CONSTRAINT UQ_CatalogUtilisateur_Email UNIQUE (Email),
    CONSTRAINT CHK_CatalogUtilisateur_Role
        CHECK (Role IN ('DataEngineer', 'ExpertMetier', 'Chercheur'))
);
GO

-- 7. Ref.CatalogAudit: Historique des modifications
CREATE TABLE Ref.CatalogAudit (
    IDAudit         INT            NOT NULL IDENTITY(1,1),
    IDUtilisateur   INT            NOT NULL,
    TypeEntite      NVARCHAR(50)   NOT NULL,  -- Schema | Table | Colonne | Source
    IDEntite        INT            NOT NULL,
    ChampModifie    NVARCHAR(200)  NOT NULL,
    AncienneValeur  NVARCHAR(1000)     NULL,
    NouvelleValeur  NVARCHAR(1000)     NULL,
    DateModification DATETIME2     NOT NULL DEFAULT GETDATE(),
    CONSTRAINT PK_CatalogAudit PRIMARY KEY (IDAudit),
    CONSTRAINT FK_CatalogAudit_Utilisateur
        FOREIGN KEY (IDUtilisateur) REFERENCES Ref.CatalogUtilisateur(IDUtilisateur),
    CONSTRAINT CHK_CatalogAudit_TypeEntite
        CHECK (TypeEntite IN ('Schema', 'Table', 'Colonne', 'Source'))
);
GO

-- DONNÉES INITIALES : Schémas GoodAir
INSERT INTO Ref.CatalogSchema (NomSchema, Description) VALUES
('Gold',    'Couche Gold : entrepôt de données final. Tables de faits et dimensions consommables par les équipes métier et les outils BI.'),
('Silver',  'Couche Silver : Données nettoyées et structurées. Parquet partitionné dans MinIO. Intermédiaire entre la coucheBronze et Gold.'),
('Bronze',  'Couche Bronze : Données brutes en JSON collectées depuis les APIs. Stockées dans MinIO. Partitionnées par source/année/mois/jour/heure. NB: Cette couche est notre source de vérité car elle contient les données originales, non modifiées.'),
('Ref',     'Schéma de référence : Tables de paramétrage, référentiels métier, Data Catalogue et seuils OMS.'),
('Staging', 'Schéma de staging : Tables temporaires utilisées lors du chargement MERGE vers Gold. Vidées à chaque run.');
GO

-- Données initiales : Sources de données
INSERT INTO Ref.CatalogSource (NomSource, TypeSource, URLSource, CheminDataLake, Description, IsActive) VALUES
('OpenWeatherMap',
 'API',
 'https://api.openweathermap.org/data/2.5/weather',
 'bronze/openweathermap/year=/month=/day=/hour=/{ville}.json',
 'API météo temps réel. Fournit température, humidité, pression et vitesse du vent pour chaque ville.',
 1),
('AQICN',
 'API',
 'https://api.waqi.info/feed/{ville}/',
 'bronze/aqicn/year=/month=/day=/hour=/{ville}.json',
 'API qualité de l air. Fournit l indice AQI global et les polluants PM25, PM10, NO2, O3 par station.',
 1),
('Open-Meteo',
 'API',
 'https://api.open-meteo.com/v1/forecast',
 'bronze/open-meteo/year=/month=/day=/hour=/{ville}.json',
 'API prévisions météo. Fournit direction du vent, couverture nuageuse et précipitations pour les 10 prochaines heures.',
 1),
('Pipeline',
 'Pipeline',
 NULL,
 NULL,
 'Variables calculées par le pipeline ETL. IDTemps, MeteoStatus, AirStatus, DateInsertion.',
 1),
('Modèle ML',
 'Modele',
 NULL,
 'silver/features-ml/year=/month=/day=/hour=/features.parquet',
 'Modèle Random Forest entraîné sur les données historiques. Génère les prédictions AQI à 6 heures.',
 1);
GO
 

-- Données initiales : Utilisateurs
INSERT INTO Ref.CatalogUtilisateur (Nom, Email, Role) VALUES
('Admin GoodAir',    'admin@goodair.fr',        'DataEngineer'),
('Chercheur GoodAir','chercheur@goodair.fr',     'Chercheur'),
('Expert Métier',    'expert@goodair.fr',        'ExpertMetier');
GO

-- Vérification du nombre de lignes dans chaque table du catalogue
SELECT 'CatalogSchema'       AS NomTable, COUNT(*) AS NbLignes FROM Ref.CatalogSchema
UNION ALL
SELECT 'CatalogTable',        COUNT(*) FROM Ref.CatalogTable
UNION ALL
SELECT 'CatalogColonne',      COUNT(*) FROM Ref.CatalogColonne
UNION ALL
SELECT 'CatalogSource',       COUNT(*) FROM Ref.CatalogSource
UNION ALL
SELECT 'CatalogColonneSource',COUNT(*) FROM Ref.CatalogColonneSource
UNION ALL
SELECT 'CatalogUtilisateur',  COUNT(*) FROM Ref.CatalogUtilisateur
UNION ALL
SELECT 'CatalogAudit',        COUNT(*) FROM Ref.CatalogAudit;
GO