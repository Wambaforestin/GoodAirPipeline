import os
from io import BytesIO

import pandas as pd
import pyarrow.parquet as pq
from sqlalchemy import text

from src.utils.connections import (
    get_minio_client,
    get_sql_engine,
    get_partition_path,
    logger
)


def read_silver_parquet(minio_client, bucket, object_path):
    """Lit un fichier Parquet depuis MinIO Silver."""
    response = minio_client.get_object(bucket, object_path)
    buffer = BytesIO(response.read())
    response.close()
    response.release_conn()
    table = pq.read_table(buffer)
    return table.to_pandas()


def truncate_staging(engine):
    """Vide les 3 tables staging avant insertion."""
    with engine.connect() as conn:
        conn.execute(text("TRUNCATE TABLE Staging.FactMesures_Temp"))
        conn.execute(text("TRUNCATE TABLE Staging.DimLieux_Temp"))
        conn.execute(text("TRUNCATE TABLE Staging.DimTemps_Temp"))
        conn.commit()
    logger.info("Tables staging vidées.")


def load_to_staging(engine, df, run_date):
    """Insère les données Silver dans les 3 tables staging."""

    # DimLieux_Temp
    df_lieux = df[["NomVille", "CodePays", "Latitude", "Longitude"]].drop_duplicates(subset=["NomVille"])

    # DimTemps_Temp
    run_hour = int(run_date.strftime("%Y%m%d%H"))
    df_temps = pd.DataFrame([{
        "IDTemps": run_hour,
        "DateHeure": run_date.strftime("%Y-%m-%d %H:00:00"),
        "Annee": run_date.year,
        "Mois": run_date.month,
        "Jour": run_date.day,
        "Heure": run_date.hour
    }])

    # FactMesures_Temp
    fact_cols = [
        "NomVille", "IDTemps", "Temperature", "Humidite", "Pression",
        "VitesseVent", "AqiGlobal", "PM25", "PM10", "NO2", "O3",
        "MeteoStatus", "AirStatus"
    ]
    df_facts = df[fact_cols].copy()

    # Insertion bulk
    df_lieux.to_sql("DimLieux_Temp", engine, schema="Staging",
                    if_exists="append", index=False)
    logger.info(f"{len(df_lieux)} villes insérées dans Staging.DimLieux_Temp")

    df_temps.to_sql("DimTemps_Temp", engine, schema="Staging",
                    if_exists="append", index=False)
    logger.info(f"{len(df_temps)} lignes insérées dans Staging.DimTemps_Temp")

    df_facts.to_sql("FactMesures_Temp", engine, schema="Staging",
                    if_exists="append", index=False)
    logger.info(f"{len(df_facts)} lignes insérées dans Staging.FactMesures_Temp")


def execute_merge(engine, batch_id):
    """Exécute le MERGE en 3 étapes séparées."""

    sql_dim_lieux = text("""
        INSERT INTO Gold.DimLieux (NomVille, CodePays, Latitude, Longitude)
        SELECT s.NomVille, s.CodePays, s.Latitude, s.Longitude
        FROM Staging.DimLieux_Temp s
        WHERE NOT EXISTS (
            SELECT 1 FROM Gold.DimLieux d WHERE d.NomVille = s.NomVille
        )
    """)

    sql_dim_temps = text("""
        INSERT INTO Gold.DimTemps (IDTemps, DateHeure, Annee, Mois, Jour, Heure)
        SELECT s.IDTemps, s.DateHeure, s.Annee, s.Mois, s.Jour, s.Heure
        FROM Staging.DimTemps_Temp s
        WHERE NOT EXISTS (
            SELECT 1 FROM Gold.DimTemps d WHERE d.IDTemps = s.IDTemps
        )
    """)

    sql_merge_facts = text("""
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
            target.DateModification = GETDATE() AT TIME ZONE 'UTC' AT TIME ZONE 'Romance Standard Time',
            target.IDBatch = :batch_id

        WHEN NOT MATCHED THEN INSERT (
            IDLieu, IDTemps, Temperature, Humidite, Pression, VitesseVent,
            AqiGlobal, PM25, PM10, NO2, O3,
            MeteoStatus, AirStatus, DateInsertion, DateModification, IDBatch
        )
        VALUES (
            source.IDLieu, source.IDTemps, source.Temperature, source.Humidite,
            source.Pression, source.VitesseVent, source.AqiGlobal, source.PM25,
            source.PM10, source.NO2, source.O3,
            source.MeteoStatus, source.AirStatus,
            GETDATE() AT TIME ZONE 'UTC' AT TIME ZONE 'Romance Standard Time',
            GETDATE() AT TIME ZONE 'UTC' AT TIME ZONE 'Romance Standard Time',
            :batch_id
        );
    """)

    with engine.connect() as conn:
        conn.execute(sql_dim_lieux)
        logger.info("DimLieux mis à jour.")

        conn.execute(sql_dim_temps)
        logger.info("DimTemps mis à jour.")

        conn.execute(sql_merge_facts, {"batch_id": batch_id})
        logger.info(f"MERGE FactMesures exécuté avec IDBatch = {batch_id}")

        conn.commit()


def run_load(run_date, batch_id):
    """Point d'entrée du chargement. Appelé par le DAG Airflow."""
    minio_client = get_minio_client()
    engine = get_sql_engine()
    silver_bucket = os.getenv("MINIO_BUCKET_SILVER")

    # Lire le Parquet Silver de l'heure en cours
    partition = get_partition_path("mesures", run_date)
    silver_path = f"{partition}mesures.parquet"

    try:
        df = read_silver_parquet(minio_client, silver_bucket, silver_path)
    except Exception as e:
        logger.error(f"Impossible de lire Silver : {e}")
        raise

    if df.empty:
        logger.warning("Silver vide, chargement annulé.")
        return

    # Data contract : vérifier les colonnes avant insertion
    expected_cols = [
        "NomVille", "IDTemps", "Temperature", "Humidite", "Pression",
        "VitesseVent", "AqiGlobal", "PM25", "PM10", "NO2", "O3",
        "MeteoStatus", "AirStatus"
    ]
    assert all(col in df.columns for col in expected_cols), \
        f"Colonnes manquantes. Attendu: {expected_cols}, Reçu: {list(df.columns)}"

    # Staging
    truncate_staging(engine)
    load_to_staging(engine, df, run_date)

    # MERGE vers Gold
    execute_merge(engine, batch_id)

    logger.info(f"Chargement terminé : {len(df)} lignes traitées.")