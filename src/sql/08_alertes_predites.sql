-- DDL : Table Gold.AlertesPredites
-- Stocke les prédictions AQI générées par le modèle ML à chaque run horaire
-- Grain : 1 ligne = 1 ville × 1 heure (identique à Gold.FactMesures)
USE GoodAirDW;
GO

CREATE TABLE Gold.AlertesPredites (
    NomVille          NVARCHAR(100) NOT NULL,
    IDTemps           BIGINT NOT NULL,
    DateHeurePredite  DATETIME2 NOT NULL,
    AQI_Predit        DECIMAL(6,2) NOT NULL,
    Alerte            VARCHAR(20) NOT NULL,
    DatePrediction    DATETIME2 NOT NULL DEFAULT
                      GETDATE() AT TIME ZONE 'UTC'
                      AT TIME ZONE 'Romance Standard Time',
    IDBatch           VARCHAR(100) NOT NULL,
    CONSTRAINT PK_Gold_AlertesPredites
        PRIMARY KEY CLUSTERED (NomVille, IDTemps)
);
GO