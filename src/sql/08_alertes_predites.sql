-- DDL : Table Gold.AlertesPredites
-- Stocke les prédictions AQI générées par le modèle ML à chaque run horaire
-- Grain : 1 ligne = 1 ville × 1 heure (identique à Gold.FactMesures)
USE GoodAirDW;
GO

CREATE TABLE Gold.AlertesPredites (
    IDLieu         INT NOT NULL,
    IDTemps        BIGINT NOT NULL,
    AQI_Predit     DECIMAL(6,2) NOT NULL,
    Alerte         VARCHAR(20) NOT NULL,       -- 'OK' ou 'ALERTE'
    DatePrediction DATETIME2 NOT NULL DEFAULT
                   GETDATE() AT TIME ZONE 'UTC'
                   AT TIME ZONE 'Romance Standard Time',
    IDBatch        VARCHAR(100) NOT NULL,
    CONSTRAINT PK_Gold_AlertesPredites
        PRIMARY KEY CLUSTERED (IDLieu, IDTemps),
    CONSTRAINT FK_Alertes_DimLieux
        FOREIGN KEY (IDLieu) REFERENCES Gold.DimLieux(IDLieu),
    CONSTRAINT FK_Alertes_DimTemps
        FOREIGN KEY (IDTemps) REFERENCES Gold.DimTemps(IDTemps)
);
GO
