import json
import numpy as np
import pandas as pd
from io import BytesIO
from zoneinfo import ZoneInfo

from src.utils.connections import (
    get_minio_client,
    get_partition_path,
    load_cities_config,
    logger,
)

PARIS_TZ = ZoneInfo("Europe/Paris")

VILLE_COLS = [
    "ville_Bordeaux",
    "ville_Franconville",
    "ville_Lille",
    "ville_Lyon",
    "ville_Marseille",
    "ville_Nantes",
    "ville_Nice",
    "ville_Paris",
    "ville_Rennes",
    "ville_Strasbourg",
    "ville_Toulouse",
]

FEATURES = [
    "Temperature",
    "Humidite",
    "Pression",
    "VitesseVent",
    "Heure_sin",
    "Heure_cos",
    "Mois_sin",
    "Mois_cos",
    "IsWeekend",
    "wind_dir_sin",
    "wind_dir_cos",
    "cloud_cover",
    "precipitation_bin",
    "AQI_mean_6h",
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
        partition = get_partition_path("mesures", past_date)
        object_path = f"{partition}mesures.parquet"

        try:
            response = minio_client.get_object("silver", object_path)
            df_past = pd.read_parquet(BytesIO(response.read()))
            city_row = df_past[df_past["NomVille"] == city_name]
            if not city_row.empty and not pd.isna(city_row["AqiGlobal"].values[0]):
                aqi_values.append(city_row["AqiGlobal"].values[0])
        except Exception:
            continue

    if aqi_values:
        return np.mean(aqi_values)
    else:
        logger.warning(f"AQI_mean_6h : aucune donnée disponible pour {city_name}")
        return np.nan


def load_open_meteo_forecast(minio_client, run_date, city_name):
    """
    Lit les prévisions Open-Meteo depuis Bronze.
    Retourne un dict indexé par naive datetime (sans timezone).
    """
    partition = get_partition_path("open-meteo", run_date)
    object_path = f"{partition}{city_name}.json"

    response = minio_client.get_object("bronze", object_path)
    data = json.loads(response.read())

    hourly = data["hourly"]
    times = hourly["time"]

    forecasts = {}
    for i, t in enumerate(times):
        dt = pd.to_datetime(t)  # naive datetime. déjà en heure Paris
        forecasts[dt] = {
            "wind_direction_10m": hourly["wind_direction_10m"][i],
            "cloud_cover": hourly["cloud_cover"][i],
            "precipitation": hourly["precipitation"][i],
        }

    logger.info(
        f"Open-Meteo Forecast chargé pour {city_name} : {len(forecasts)} heures"
    )
    return forecasts


def save_rejet(minio_client, run_date, city_name, reason, data):
    """
    Sauvegarde les données incomplètes dans Silver/rejet-ml/ pour analyse ultérieure.
    """
    try:
        partition = get_partition_path("rejet-ml", run_date)
        object_path = f"{partition}{city_name}.json"
        payload = {"city": city_name, "reason": reason, "data": data}
        json_bytes = json.dumps(payload, ensure_ascii=False, default=str).encode(
            "utf-8"
        )

        minio_client.put_object(
            "silver",
            object_path,
            BytesIO(json_bytes),
            length=len(json_bytes),
            content_type="application/json",
        )
        logger.info(f"Rejet sauvegardé : silver/{object_path}")
    except Exception as e:
        logger.warning(f"Impossible de sauvegarder le rejet pour {city_name} : {e}")


def apply_transformations(row):
    """
    Applique les mêmes transformations que 04_data_preparation.ipynb.
    """
    heure = row["heure_future"]
    mois = row["mois"]

    features = {
        "Temperature": row["Temperature"],
        "Humidite": row["Humidite"],
        "Pression": row["Pression"],
        "VitesseVent": row["VitesseVent"],
        "Heure_sin": np.sin(2 * np.pi * heure / 24),
        "Heure_cos": np.cos(2 * np.pi * heure / 24),
        "Mois_sin": np.sin(2 * np.pi * mois / 12),
        "Mois_cos": np.cos(2 * np.pi * mois / 12),
        "IsWeekend": row["IsWeekend"],
        "wind_dir_sin": np.sin(2 * np.pi * row["wind_direction_10m"] / 360),
        "wind_dir_cos": np.cos(2 * np.pi * row["wind_direction_10m"] / 360),
        "cloud_cover": row["cloud_cover"],
        "precipitation_bin": 1 if row["precipitation"] > 0 else 0,
        "AQI_mean_6h": row["AQI_mean_6h"],
    }

    for col in VILLE_COLS:
        features[col] = 1 if col == f"ville_{row['NomVille']}" else 0

    return features


def build_features(run_date, send_warning=None):
    """
    Point d'entrée principal.
    Construit les features pour les 6 prochains créneaux disponibles pour chaque ville.

    FIX TIMEZONE : au lieu de chercher H+1 à H+6 exactement.
    on prend les 6 premiers timestamps Open-Meteo disponibles après run_date.
    Cela évite tout problème de décalage UTC/Paris.

    CHECK MÉTIER : si les features sont incomplètes pour toutes les villes.
    on retourne True (task verte) + email d'alerte + sauvegarde en rejet.
    """
    minio_client = get_minio_client()
    cities = load_cities_config()

    df_silver = load_silver_mesures(minio_client, run_date)

    # run_date en naive datetime pour comparaison avec timestamps Open-Meteo
    run_dt_naive = pd.Timestamp(
        run_date.year, run_date.month, run_date.day, run_date.hour, 0, 0
    )

    rows = []
    villes_rejet = []

    for city in cities:
        city_name = city["city"]
        logger.info(f"Construction des features pour {city_name}...")

        city_row = df_silver[df_silver["NomVille"] == city_name]
        if city_row.empty:
            logger.warning(f"Pas de données Silver pour {city_name}. Skip.")
            save_rejet(minio_client, run_date, city_name, "Silver manquant", {})
            villes_rejet.append(city_name)
            continue

        gd = city_row.iloc[0]

        aqi_mean_6h = compute_aqi_mean_6h(minio_client, run_date, city_name)

        try:
            forecasts = load_open_meteo_forecast(minio_client, run_date, city_name)
        except Exception as e:
            logger.warning(f"Open-Meteo indisponible pour {city_name} : {e}. Skip.")
            save_rejet(minio_client, run_date, city_name, "Open-Meteo indisponible", {})
            villes_rejet.append(city_name)
            continue

        # FIX TIMEZONE : prendre les 6 premiers timestamps futurs disponibles
        future_slots = sorted([dt for dt in forecasts.keys() if dt > run_dt_naive])[:6]

        if not future_slots:
            logger.warning(f"Aucun créneau futur disponible pour {city_name}. Skip.")
            save_rejet(
                minio_client,
                run_date,
                city_name,
                "Aucun créneau futur Open-Meteo",
                {
                    "run_dt_naive": str(run_dt_naive),
                    "forecasts_keys": [str(k) for k in forecasts.keys()],
                },
            )
            villes_rejet.append(city_name)
            continue

        for future_dt in future_slots:
            forecast = forecasts[future_dt]

            row = {
                "NomVille": city_name,
                "DateHeurePredite": future_dt,
                "IDTemps": int(future_dt.strftime("%Y%m%d%H")),
                "heure_future": future_dt.hour,
                "mois": future_dt.month,
                "IsWeekend": future_dt.weekday() >= 5,
                "Temperature": gd["Temperature"],
                "Humidite": gd["Humidite"],
                "Pression": gd["Pression"],
                "VitesseVent": gd["VitesseVent"],
                "wind_direction_10m": forecast["wind_direction_10m"],
                "cloud_cover": forecast["cloud_cover"],
                "precipitation": forecast["precipitation"],
                "AQI_mean_6h": aqi_mean_6h,
            }

            features = apply_transformations(row)
            features["NomVille"] = city_name
            features["DateHeurePredite"] = future_dt
            features["IDTemps"] = row["IDTemps"]

            rows.append(features)

    # CHECK MÉTIER : aucune feature construite
    if not rows:
        logger.warning("Aucune feature construite pour aucune ville.")
        if send_warning:
            send_warning(
                subject="[GoodAir] Prédiction impossible — features manquantes",
                message=f"Aucune feature disponible pour le run {run_date}. "
                f"Villes en rejet : {villes_rejet}. "
                f"Le modèle n'a pas tourné.",
            )
        return True  # Task verte. pas d erreur

    # Si certaines villes sont en rejet mais pas toutes
    if villes_rejet:
        logger.warning(f"Villes sans prédiction : {villes_rejet}")
        if send_warning:
            send_warning(
                subject="[GoodAir] Prédiction partielle — features manquantes",
                message=f"Features manquantes pour : {villes_rejet}. "
                f"Prédictions générées pour les autres villes. "
                f"Données rejetées sauvegardées dans Silver/rejet-ml/.",
            )

    df_features = pd.DataFrame(rows)

    # Vérification du contrat de données
    missing = [f for f in FEATURES if f not in df_features.columns]
    if missing:
        logger.warning(f"Features manquantes dans le dataset : {missing}")
        if send_warning:
            send_warning(
                subject="[GoodAir] Features incomplètes",
                message=f"Features manquantes : {missing}. Le modèle n'a pas tourné.",
            )
        return True  # Task verte. pas d erreur

    # Écriture dans Silver/features-ml/
    partition = get_partition_path("features-ml", run_date)
    object_path = f"{partition}features.parquet"
    buffer = BytesIO()
    df_features.to_parquet(buffer, index=False)
    buffer.seek(0)

    minio_client.put_object(
        "silver",
        object_path,
        buffer,
        length=buffer.getbuffer().nbytes,
        content_type="application/octet-stream",
    )

    logger.info(f"Features écrites : silver/{object_path} ({len(df_features)} lignes)")
    return True
