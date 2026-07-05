import json
import os
from io import BytesIO

import requests
from minio.error import S3Error

from src.utils.connections import (
    get_minio_client,
    load_cities_config,
    load_open_meteo_config,
    get_partition_path,
    logger,
)


def extract_openweathermap(city, country, api_key):
    """Appelle l'API OpenWeatherMap pour une ville donnée."""
    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {"q": f"{city},{country}", "appid": api_key, "units": "metric"}
    response = requests.get(url, params=params, timeout=30)

    data = response.json()
    if response.status_code == 404:
        logger.warning(f"OpenWeatherMap - Ville introuvable : {city},{country}")
        return None

    response.raise_for_status()
    return data


def extract_aqicn(city, api_key):
    """Appelle l'API AQICN pour une ville donnée."""
    url = f"https://api.waqi.info/feed/{city}/"
    params = {"token": api_key}
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()

    data = response.json()
    if data.get("status") != "ok":
        logger.warning(f"AQICN - Réponse non-ok pour {city} : {data.get('status')}")
        return None

    return data


def extract_open_meteo(latitude, longitude, variables):
    """
    Appelle l'API Open-Meteo Forecast pour une ville donnée.
    Retourne les prévisions horaires sur les 10 prochaines heures.
    """
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": ",".join(variables),
        "forecast_hours": 10,  # 10 au lieu de 6 pour absorber le décalage
        "timezone": "Europe/Paris",
    }

    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()

    data = response.json()
    logger.info(
        f"Open-Meteo - Prévisions reçues : "
        f"lat={latitude}. lon={longitude}. "
        f"{len(data.get('hourly', {}).get('time', []))} heures"
    )
    return data


def save_to_bronze(minio_client, bucket, data, partition_path, filename):
    """Sauvegarde un JSON brut dans MinIO (couche Bronze)."""
    try:
        if not minio_client.bucket_exists(bucket):
            minio_client.make_bucket(bucket)
            logger.info(f"Bucket créé : {bucket}")
    except S3Error:
        pass

    json_bytes = json.dumps(data, ensure_ascii=False).encode("utf-8")
    object_path = f"{partition_path}{filename}"

    minio_client.put_object(
        bucket_name=bucket,
        object_name=object_path,
        data=BytesIO(json_bytes),
        length=len(json_bytes),
        content_type="application/json",
    )
    logger.info(f"Bronze sauvegardé : {bucket}/{object_path}")


def run_extract(run_date):
    """Point d'entrée de l extraction. Appelé par le DAG Airflow."""
    cities = load_cities_config()
    om_config = load_open_meteo_config()
    minio_client = get_minio_client()

    owm_key = os.getenv("OWM_API_KEY")
    aqicn_key = os.getenv("AQICN_API_KEY")
    bronze_bucket = os.getenv("MINIO_BUCKET_BRONZE")
    om_variables = om_config["variables"]
    om_cities = {c["name"]: c for c in om_config["cities"]}

    for city_config in cities:
        city = city_config["city"]
        country = city_config["country"]
        logger.info(f"Extraction pour {city}, {country}...")

        # OpenWeatherMap
        owm_data = extract_openweathermap(city, country, owm_key)
        if owm_data:
            partition = get_partition_path("openweathermap", run_date)
            save_to_bronze(
                minio_client, bronze_bucket, owm_data, partition, f"{city}.json"
            )

        # AQICN
        aqicn_data = extract_aqicn(city, aqicn_key)
        if aqicn_data:
            partition = get_partition_path("aqicn", run_date)
            save_to_bronze(
                minio_client, bronze_bucket, aqicn_data, partition, f"{city}.json"
            )

        # Open-Meteo Forecast
        if city not in om_cities:
            logger.warning(f"Open-Meteo - Ville absente du config : {city}. Skip.")
            continue

        city_coords = om_cities[city]
        om_data = extract_open_meteo(
            latitude=city_coords["latitude"],
            longitude=city_coords["longitude"],
            variables=om_variables,
        )
        if om_data:
            partition = get_partition_path("open-meteo", run_date)
            save_to_bronze(
                minio_client, bronze_bucket, om_data, partition, f"{city}.json"
            )

    logger.info("Extraction terminée (OWM + AQICN + Open-Meteo).")
