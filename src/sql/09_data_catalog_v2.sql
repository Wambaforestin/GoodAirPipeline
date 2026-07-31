-- Data Catalogue GoodAir Modélisation normalisée (3NF)
-- Schéma : Ref
-- Tables : Schema, Table, Colonne, Source, ColonneSource, Utilisateur, Audit

USE GoodAirDW;
GO

-- 1. Ref.CatalogSchema: Les schémas de la base de données
CREATE TABLE Ref.CatalogSchema (
    IDSchema INT NOT NULL IDENTITY(100,1),
    NomSchema NVARCHAR(100) NOT NULL,
    Description NVARCHAR(500) NULL,
    DateCreation DATETIME2 NOT NULL DEFAULT GETDATE(),
    CONSTRAINT PK_CatalogSchema PRIMARY KEY (IDSchema),
    CONSTRAINT UQ_CatalogSchema_Nom UNIQUE (NomSchema)
);
GO

-- 2. Ref.CatalogTable: Les tables par schéma
CREATE TABLE Ref.CatalogTable (
    IDTable INT NOT NULL IDENTITY(200,1),
    IDSchema INT NOT NULL,
    NomTable NVARCHAR(200) NOT NULL,
    Description NVARCHAR(1000) NULL,
    NbColonnes INT NULL,
    DateCreation DATETIME2 NOT NULL DEFAULT GETDATE(),
    CONSTRAINT PK_CatalogTable PRIMARY KEY (IDTable),
    CONSTRAINT FK_CatalogTable_Schema FOREIGN KEY (IDSchema) REFERENCES Ref.CatalogSchema(IDSchema),
    CONSTRAINT UQ_CatalogTable_Nom UNIQUE (IDSchema, NomTable)
);
GO

-- 3. Ref.CatalogColonne: Les colonnes par table
CREATE TABLE Ref.CatalogColonne (
    IDColonne INT NOT NULL IDENTITY(500,1),
    IDTable INT NOT NULL,
    NomColonne NVARCHAR(200) NOT NULL,
    TypeSQL NVARCHAR(100) NOT NULL,
    Description NVARCHAR(1000) NULL,
    IsNullable BIT NOT NULL DEFAULT 1,
    ValeurExemple NVARCHAR(500) NULL,
    Ordre INT NOT NULL DEFAULT 0,
    CONSTRAINT PK_CatalogColonne PRIMARY KEY (IDColonne),
    CONSTRAINT FK_CatalogColonne_Table FOREIGN KEY (IDTable) REFERENCES Ref.CatalogTable(IDTable),
    CONSTRAINT UQ_CatalogColonne_Nom UNIQUE (IDTable, NomColonne)
);
GO

-- 4. Ref.CatalogSource: Les sources de données
CREATE TABLE Ref.CatalogSource (
    IDSource INT NOT NULL IDENTITY(100,5),
    NomSource NVARCHAR(200) NOT NULL,
    TypeSource NVARCHAR(100) NOT NULL,  -- API | Pipeline | Modèle
    URLSource  NVARCHAR(500) NULL,  -- URL de l API ou endpoint
    CheminDataLake NVARCHAR(500) NULL,
    Description NVARCHAR(1000) NULL,
    IsActive BIT NOT NULL DEFAULT 1,
    CONSTRAINT PK_CatalogSource PRIMARY KEY (IDSource),
    CONSTRAINT UQ_CatalogSource_Nom UNIQUE (NomSource),
    CONSTRAINT CHK_CatalogSource_TypeSource CHECK (TypeSource IN ('API', 'Pipeline', 'Modele'))
);
GO

-- 5. Ref.CatalogColonneSource: Liaison entre la table Colonne et Source (many to many)
CREATE TABLE Ref.CatalogColonneSource (
    IDColonne INT NOT NULL,
    IDSource INT NOT NULL,
    CheminSourceDetail NVARCHAR(500) NULL,  -- ex: main.humidity, data.iaqi.pm25.v
    CONSTRAINT PK_CatalogColonneSource PRIMARY KEY (IDColonne, IDSource),
    CONSTRAINT FK_ColonneSource_Colonne FOREIGN KEY (IDColonne) REFERENCES Ref.CatalogColonne(IDColonne) ON DELETE CASCADE,
    CONSTRAINT FK_ColonneSource_Source FOREIGN KEY (IDSource)  REFERENCES Ref.CatalogSource(IDSource) ON DELETE CASCADE
);
GO

-- 6. Ref.CatalogUtilisateur: Les utilisateurs et leurs rôles
CREATE TABLE Ref.CatalogUtilisateur (
    IDUtilisateur INT NOT NULL IDENTITY(100,5),
    Nom NVARCHAR(200) NOT NULL,
    Email NVARCHAR(200) NOT NULL,
    Role NVARCHAR(50) NOT NULL,  -- DataEngineer | ExpertMetier | Chercheur
    DateCreation DATETIME2 NOT NULL DEFAULT GETDATE(),
    IsActif BIT NOT NULL DEFAULT 1,
    CONSTRAINT PK_CatalogUtilisateur PRIMARY KEY (IDUtilisateur),
    CONSTRAINT UQ_CatalogUtilisateur_Email UNIQUE (Email),
    CONSTRAINT CHK_CatalogUtilisateur_Role CHECK (Role IN ('DataEngineer', 'ExpertMetier', 'Chercheur'))
);
GO

-- 7. Ref.CatalogAudit: Historique des modifications
CREATE TABLE Ref.CatalogAudit (
    IDAudit INT NOT NULL IDENTITY(1,1),
    IDUtilisateur INT NOT NULL,
    TypeEntite NVARCHAR(50) NOT NULL,  -- Schema | Table | Colonne | Source
    IDEntite INT NOT NULL,
    ChampModifie NVARCHAR(200) NOT NULL,
    AncienneValeur NVARCHAR(1000) NULL,
    NouvelleValeur NVARCHAR(1000) NULL,
    DateModification DATETIME2 NOT NULL DEFAULT GETDATE(),
    CONSTRAINT PK_CatalogAudit PRIMARY KEY (IDAudit),
    CONSTRAINT FK_CatalogAudit_Utilisateur FOREIGN KEY (IDUtilisateur) REFERENCES Ref.CatalogUtilisateur(IDUtilisateur),
    CONSTRAINT CHK_CatalogAudit_TypeEntite CHECK (TypeEntite IN ('Schema', 'Table', 'Colonne', 'Source'))
);
GO