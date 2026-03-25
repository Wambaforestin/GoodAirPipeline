import os
import logging
import json
import urllib.parse
from datetime import datetime

import yaml
from dotenv import load_dotenv
from sqlalchemy import create_engine
from minio import Minio

# Charger les variables d'environnement
load_dotenv()

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("goodair")


def get_sql_engine():
    """Crée et retourne un engine SQLAlchemy connecté à SQL Server."""
    params = urllib.parse.quote_plus(
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={os.getenv('MSSQL_HOST')},{os.getenv('MSSQL_PORT')};"
        f"DATABASE={os.getenv('MSSQL_DATABASE')};"
        f"UID=sa;"
        f"PWD={os.getenv('MSSQL_SA_PASSWORD')};"
        f"TrustServerCertificate=yes;"
    )
    engine = create_engine(
        f"mssql+pyodbc:///?odbc_connect={params}",
        connect_args={"fast_executemany": True}
    )
    return engine


def get_minio_client():
    """Crée et retourne un client MinIO."""
    client = Minio(
        endpoint=os.getenv("MINIO_ENDPOINT"),
        access_key=os.getenv("MINIO_ROOT_USER"),
        secret_key=os.getenv("MINIO_ROOT_PASSWORD"),
        secure=False
    )
    return client


def load_pipeline_config():
    """Charge le fichier pipeline_config.yaml."""
    config_path = os.path.join(os.path.dirname(__file__), "..", "..", "config", "pipeline_config.yaml")
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    return config


def load_cities_config():
    """Charge la liste des villes depuis cities_config.json."""
    config_path = os.path.join(os.path.dirname(__file__), "..", "..", "config", "cities_config.json")
    with open(config_path, "r") as f:
        cities = json.load(f)
    return cities


def get_partition_path(api_name, run_date):
    """Génère le chemin de partitionnement Bronze/Silver à partir d'une date."""
    # run_date est un datetime (logical_date d'Airflow)
    return (
        f"{api_name}/"
        f"year={run_date.strftime('%Y')}/"
        f"month={run_date.strftime('%m')}/"
        f"day={run_date.strftime('%d')}/"
        f"hour={run_date.strftime('%H')}/"
    )