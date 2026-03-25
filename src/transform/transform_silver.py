import os
import json
from io import BytesIO

import pandas as pd
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from minio.error import S3Error

from src.utils.connections import (
    get_minio_client,
    load_cities_config,
    get_partition_path,
    logger,
)

# Colonnes attendues après la fusion des deux sources
ALL_EXPECTED_COLUMNS = [
    "NomVille",
    "CodePays",
    "Latitude",
    "Longitude",
    "IDTemps",
    "Temperature",
    "Humidite",
    "Pression",
    "VitesseVent",
    "AqiGlobal",
    "PM25",
    "PM10",
    "NO2",
    "O3",
]


def read_bronze_json(minio_client, bucket, object_path):
    """Lit un fichier JSON depuis MinIO Bronze."""
    response = minio_client.get_object(bucket, object_path)
    data = json.loads(response.read().decode("utf-8"))
    response.close()
    response.release_conn()
    return data


def flatten_openweathermap(raw, city_name, run_date):
    """Aplatit le JSON OpenWeatherMap en une ligne de DataFrame.
    city_name vient du config, pas de l'API (garantit la cohérence du merge).
    """
    run_hour = int(run_date.strftime("%Y%m%d%H"))

    row = {
        "NomVille": city_name,
        "CodePays": raw.get("sys", {}).get("country"),
        "Latitude": raw.get("coord", {}).get("lat"),
        "Longitude": raw.get("coord", {}).get("lon"),
        "IDTemps": run_hour,
        "Temperature": raw.get("main", {}).get("temp"),
        "Humidite": raw.get("main", {}).get("humidity"),
        "Pression": raw.get("main", {}).get("pressure"),
        "VitesseVent": raw.get("wind", {}).get("speed"),
    }
    return row


def flatten_aqicn(raw, city_name, run_date):
    """Aplatit le JSON AQICN en une ligne de DataFrame.
    city_name vient du config, pas de l'API (garantit la cohérence du merge).
    """
    run_hour = int(run_date.strftime("%Y%m%d%H"))
    data = raw.get("data", {})
    iaqi = data.get("iaqi", {})

    row = {
        "NomVille": city_name,
        "IDTemps": run_hour,
        "AqiGlobal": data.get("aqi"),
        "PM25": iaqi.get("pm25", {}).get("v"),
        "PM10": iaqi.get("pm10", {}).get("v"),
        "NO2": iaqi.get("no2", {}).get("v"),
        "O3": iaqi.get("o3", {}).get("v"),
    }
    return row


def ensure_all_columns(df):
    """Garantit que toutes les colonnes attendues existent dans le DataFrame.
    Si une API n'a pas répondu, ses colonnes sont absentes → on les crée à NULL.
    """
    for col in ALL_EXPECTED_COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA
    return df


def apply_cleaning_rules(df):
    """Applique les règles de nettoyage métier sur le DataFrame fusionné."""

    # Garantir toutes les colonnes présentes
    df = ensure_all_columns(df)

    # Typage strict - les valeurs non convertibles deviennent NULL
    numeric_cols = [
        "Temperature",
        "Humidite",
        "Pression",
        "VitesseVent",
        "AqiGlobal",
        "PM25",
        "PM10",
        "NO2",
        "O3",
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # CodePays manquant → 'ND'
    df["CodePays"] = df["CodePays"].fillna("ND")

    # Statuts de source
    df["MeteoStatus"] = np.where(df["Temperature"].isna(), "FAILED", "OK")
    df["AirStatus"] = np.where(df["PM25"].isna(), "FAILED", "OK")

    # DQ Flags (bornes de validité)
    df["is_temp_valid"] = df["Temperature"].isna() | (
        (df["Temperature"] >= -50) & (df["Temperature"] <= 60)
    )

    # Ligne morte : TOUTES les métriques sont NULL → rejet
    meteo_cols = ["Temperature", "Humidite", "Pression", "VitesseVent"]
    air_cols = ["AqiGlobal", "PM25", "PM10", "NO2", "O3"]
    dead_rows = df[meteo_cols + air_cols].isna().all(axis=1)

    df_rejects = df[dead_rows].copy()
    df_valid = df[~dead_rows].copy()

    # Rejet des lignes sans clés logiques
    no_keys = df_valid["NomVille"].isna() | df_valid["IDTemps"].isna()
    df_rejects = pd.concat([df_rejects, df_valid[no_keys]])
    df_valid = df_valid[~no_keys].copy()

    # Dédoublonnage sur (NomVille, IDTemps)
    df_valid = df_valid.drop_duplicates(subset=["NomVille", "IDTemps"], keep="last")

    return df_valid, df_rejects


def save_to_silver(minio_client, bucket, df, partition_path, filename):
    """Sauvegarde un DataFrame en Parquet dans MinIO (couche Silver)."""
    try:
        if not minio_client.bucket_exists(bucket):
            minio_client.make_bucket(bucket)
            logger.info(f"Bucket créé : {bucket}")
    except S3Error:
        pass

    table = pa.Table.from_pandas(df)
    buffer = BytesIO()
    pq.write_table(table, buffer)
    buffer.seek(0)

    object_path = f"{partition_path}{filename}"
    minio_client.put_object(
        bucket_name=bucket,
        object_name=object_path,
        data=buffer,
        length=buffer.getbuffer().nbytes,
        content_type="application/octet-stream",
    )
    logger.info(f"Silver sauvegardé : {bucket}/{object_path}")


def run_transform(run_date):
    """Point d'entrée de la transformation. Appelé par le DAG Airflow."""
    cities = load_cities_config()
    minio_client = get_minio_client()
    bronze_bucket = os.getenv("MINIO_BUCKET_BRONZE")
    silver_bucket = os.getenv("MINIO_BUCKET_SILVER")

    meteo_rows = []
    air_rows = []

    for city_config in cities:
        city = city_config["city"]

        # Lire les JSON Bronze de l'heure en cours
        owm_path = get_partition_path("openweathermap", run_date) + f"{city}.json"
        aqicn_path = get_partition_path("aqicn", run_date) + f"{city}.json"

        try:
            owm_raw = read_bronze_json(minio_client, bronze_bucket, owm_path)
            meteo_rows.append(flatten_openweathermap(owm_raw, city, run_date))
            logger.info(f"Bronze OWM lu : {city}")
        except Exception as e:
            logger.warning(f"Bronze OWM introuvable pour {city} : {e}")

        try:
            aqicn_raw = read_bronze_json(minio_client, bronze_bucket, aqicn_path)
            air_rows.append(flatten_aqicn(aqicn_raw, city, run_date))
            logger.info(f"Bronze AQICN lu : {city}")
        except Exception as e:
            logger.warning(f"Bronze AQICN introuvable pour {city} : {e}")

    # Construction des DataFrames
    df_meteo = pd.DataFrame(meteo_rows) if meteo_rows else pd.DataFrame()
    df_air = pd.DataFrame(air_rows) if air_rows else pd.DataFrame()

    if df_meteo.empty and df_air.empty:
        logger.error("Aucune donnée Bronze disponible. Transformation annulée.")
        return False

    # Fusion météo + air sur NomVille + IDTemps
    if not df_meteo.empty and not df_air.empty:
        df_merged = pd.merge(df_meteo, df_air, on=["NomVille", "IDTemps"], how="outer")
    elif not df_meteo.empty:
        df_merged = df_meteo
    else:
        df_merged = df_air

    # Nettoyage (ensure_all_columns est appelé à l'intérieur)
    df_valid, df_rejects = apply_cleaning_rules(df_merged)

    # Sauvegarde Silver
    partition = get_partition_path("mesures", run_date)
    if not df_valid.empty:
        save_to_silver(
            minio_client, silver_bucket, df_valid, partition, "mesures.parquet"
        )
        logger.info(f"{len(df_valid)} lignes valides sauvegardées en Silver.")
    else:
        logger.warning("Aucune ligne valide après nettoyage.")
        return False

    # Sauvegarde des rejets
    if not df_rejects.empty:
        reject_partition = get_partition_path("rejects", run_date)
        save_to_silver(
            minio_client, silver_bucket, df_rejects, reject_partition, "rejects.parquet"
        )
        logger.warning(f"{len(df_rejects)} lignes rejetées sauvegardées.")

    return True
