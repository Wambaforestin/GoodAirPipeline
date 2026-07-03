
import json
import logging
import numpy as np
import pandas as pd
from io import BytesIO
from zoneinfo import ZoneInfo

from src.utils.connections import (
    get_minio_client,
    get_partition_path,
    load_cities_config,
    to_paris_time,
    logger
)

PARIS_TZ = ZoneInfo("Europe/Paris")

# Colonnes One-Hot attendues par le modèle (ordre du training)
VILLE_COLS = [
    "ville_Bordeaux", "ville_Franconville", "ville_Lille", "ville_Lyon",
    "ville_Marseille", "ville_Nantes", "ville_Nice", "ville_Paris",
    "ville_Rennes", "ville_Strasbourg", "ville_Toulouse"
]

FEATURES = [
    "Temperature", "Humidite", "Pression", "VitesseVent",
    "Heure_sin", "Heure_cos",
    "Mois_sin", "Mois_cos",
    "IsWeekend",
    "wind_dir_sin", "wind_dir_cos",
    "cloud_cover",
    "precipitation_bin",
    "AQI_mean_6h"
] + VILLE_COLS


def load_silver_mesures(minio_client, run_date):
    """Lit le Parquet Silver du créneau courant."""
    partition = get_partition_path("mesures", run_date)
    object_path = f"{partition}mesures.parquet"

    try:
        response = minio_client.get_object("silver", object_path)
        df = pd.read_parquet(BytesIO(response.read()))
        logger.info(f"Silver chargé : {len(df)} lignes depuis silver/{object_path}")
        return df
    except Exception as e:
        logger.error(f"Erreur lecture Silver : {e}")
        raise


def compute_aqi_mean_6h(minio_client, run_date, city_name):
    """
    Calcule AQI_mean_6h depuis les 6 dernières heures disponibles dans Silver.
    Robuste aux trous temporels : min_periods=1.
    """
    aqi_values = []

    for h in range(1, 7):
        past_date = run_date - pd.Timedelta(hours=h)
        partition  = get_partition_path("mesures", past_date)
        object_path = f"{partition}mesures.parquet"

        try:
            response = minio_client.get_object("silver", object_path)
            df_past  = pd.read_parquet(BytesIO(response.read()))
            city_row = df_past[df_past["NomVille"] == city_name]
            if not city_row.empty and not pd.isna(city_row["AqiGlobal"].values[0]):
                aqi_values.append(city_row["AqiGlobal"].values[0])
        except Exception:
            # Trou temporel : on passe à l'heure suivante
            continue

    if aqi_values:
        return np.mean(aqi_values)
    else:
        logger.warning(f"AQI_mean_6h : aucune donnée disponible pour {city_name}")
        return np.nan


def load_open_meteo_forecast(minio_client, run_date, city_name):
    """
    Lit les prévisions Open-Meteo depuis Bronze pour H+1 à H+6.
    Retourne un dict indexé par heure future.
    """
    partition   = get_partition_path("open-meteo", run_date)
    object_path = f"{partition}{city_name}.json"

    try:
        response = minio_client.get_object("bronze", object_path)
        data     = json.loads(response.read())

        hourly    = data["hourly"]
        times     = hourly["time"]
        forecasts = {}

        for i, t in enumerate(times):
            dt = pd.to_datetime(t).tz_localize("UTC").astimezone(PARIS_TZ)
            forecasts[dt] = {
                "wind_direction_10m": hourly["wind_direction_10m"][i],
                "cloud_cover"       : hourly["cloud_cover"][i],
                "precipitation"     : hourly["precipitation"][i]
            }

        logger.info(f"Open-Meteo Forecast chargé pour {city_name} : {len(forecasts)} heures")
        return forecasts

    except Exception as e:
        logger.error(f"Erreur lecture Open-Meteo Bronze pour {city_name} : {e}")
        raise


def apply_transformations(row):
    """
    Applique les mêmes transformations que 04_data_preparation.ipynb.
    - Encodage cyclique Heure. Mois. wind_direction
    - Binarisation precipitation
    - One-Hot NomVille
    """
    heure = row["heure_future"]
    mois  = row["mois"]

    features = {
        # Variables GoodAir brutes
        "Temperature"      : row["Temperature"],
        "Humidite"         : row["Humidite"],
        "Pression"         : row["Pression"],
        "VitesseVent"      : row["VitesseVent"],

        # Encodage cyclique Heure
        "Heure_sin"        : np.sin(2 * np.pi * heure / 24),
        "Heure_cos"        : np.cos(2 * np.pi * heure / 24),

        # Encodage cyclique Mois
        "Mois_sin"         : np.sin(2 * np.pi * mois / 12),
        "Mois_cos"         : np.cos(2 * np.pi * mois / 12),

        # IsWeekend
        "IsWeekend"        : row["IsWeekend"],

        # Encodage cyclique direction du vent (variable circulaire 0-360)
        "wind_dir_sin"     : np.sin(2 * np.pi * row["wind_direction_10m"] / 360),
        "wind_dir_cos"     : np.cos(2 * np.pi * row["wind_direction_10m"] / 360),

        # Couverture nuageuse brute
        "cloud_cover"      : row["cloud_cover"],

        # Binarisation précipitation
        "precipitation_bin": 1 if row["precipitation"] > 0 else 0,

        # Feature temporelle
        "AQI_mean_6h"      : row["AQI_mean_6h"]
    }

    # One-Hot Encoding NomVille
    for col in VILLE_COLS:
        features[col] = 1 if col == f"ville_{row['NomVille']}" else 0

    return features


def build_features(run_date):
    """
    Point d'entrée principal.
    Construit les features pour les 6h suivantes pour chaque ville.
    Écrit le résultat dans Silver/features-ml/.
    """
    minio_client = get_minio_client()
    cities       = load_cities_config()

    # Chargement du Silver courant (données GoodAir de l'heure actuelle)
    df_silver = load_silver_mesures(minio_client, run_date)

    rows = []

    for city in cities:
        city_name = city["city"]
        logger.info(f"Construction des features pour {city_name}...")

        # Données GoodAir de l'heure courante
        city_row = df_silver[df_silver["NomVille"] == city_name]
        if city_row.empty:
            logger.warning(f"Pas de données Silver pour {city_name}. Skip.")
            continue

        gd = city_row.iloc[0]

        # AQI moyen des 6 dernières heures
        aqi_mean_6h = compute_aqi_mean_6h(minio_client, run_date, city_name)

        # Prévisions Open-Meteo H+1 à H+6
        try:
            forecasts = load_open_meteo_forecast(minio_client, run_date, city_name)
        except Exception:
            logger.warning(f"Open-Meteo indisponible pour {city_name}. Skip.")
            continue

        # Itération sur les 6 prochaines heures
        for h in range(1, 7):
            future_date = run_date + pd.Timedelta(hours=h)
            future_dt   = future_date.replace(minute=0, second=0, microsecond=0)

            if future_dt not in forecasts:
                logger.warning(f"Prévision manquante pour {city_name} à {future_dt}. Skip.")
                continue

            forecast = forecasts[future_dt]

            row = {
                "NomVille"          : city_name,
                "DateHeurePredite"  : future_dt,
                "IDTemps"           : int(future_dt.strftime("%Y%m%d%H")),
                "heure_future"      : future_dt.hour,
                "mois"              : future_dt.month,
                "IsWeekend"         : future_dt.weekday() >= 5,
                "Temperature"       : gd["Temperature"],
                "Humidite"          : gd["Humidite"],
                "Pression"          : gd["Pression"],
                "VitesseVent"       : gd["VitesseVent"],
                "wind_direction_10m": forecast["wind_direction_10m"],
                "cloud_cover"       : forecast["cloud_cover"],
                "precipitation"     : forecast["precipitation"],
                "AQI_mean_6h"       : aqi_mean_6h
            }

            features = apply_transformations(row)
            features["NomVille"]         = city_name
            features["DateHeurePredite"] = future_dt
            features["IDTemps"]          = row["IDTemps"]

            rows.append(features)

    if not rows:
        logger.error("Aucune feature construite. Abandon.")
        return False

    df_features = pd.DataFrame(rows)

    # Vérification du contrat de données
    missing = [f for f in FEATURES if f not in df_features.columns]
    assert not missing, f"Features manquantes : {missing}"

    # Écriture dans Silver/features-ml/
    partition   = get_partition_path("features-ml", run_date)
    object_path = f"{partition}features.parquet"
    buffer      = BytesIO()
    df_features.to_parquet(buffer, index=False)
    buffer.seek(0)

    minio_client.put_object(
        "silver",
        object_path,
        buffer,
        length=buffer.getbuffer().nbytes,
        content_type="application/octet-stream"
    )

    logger.info(f"Features écrites : silver/{object_path} ({len(df_features)} lignes)")
    return True