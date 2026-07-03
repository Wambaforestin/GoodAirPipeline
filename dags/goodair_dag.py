from datetime import datetime, timedelta

from airflow.sdk import DAG
from airflow.providers.standard.operators.python import PythonOperator

from src.extract.extract_apis import run_extract
from src.transform.transform_silver import run_transform
from src.load.load_gold import run_load
from src.ml.feature_engineering import build_features
from src.ml.predict import run_predict
from src.utils.connections import to_paris_time


default_args = {
    "owner": "goodair",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="goodair_pipeline",
    default_args=default_args,
    description="Pipeline ETL horaire - Météo + Qualité de l'air",
    schedule="@hourly",
    start_date=datetime(2026, 3, 25),
    catchup=False,
    tags=["goodair", "etl"],
) as dag:

    def task_extract(**kwargs):
        run_date = to_paris_time(kwargs["logical_date"])
        run_extract(run_date)

    def task_transform(**kwargs):
        run_date = to_paris_time(kwargs["logical_date"])
        success = run_transform(run_date)
        if not success:
            raise ValueError("Transformation échouée : aucune donnée valide.")

    def task_load(**kwargs):
        run_date = to_paris_time(kwargs["logical_date"])
        batch_id = kwargs["run_id"]
        run_load(run_date, batch_id)

    def task_build_features(**kwargs):
        run_date = to_paris_time(kwargs["logical_date"])
        success = build_features(run_date)
        if not success:
            raise ValueError("Feature engineering échoué : aucune feature construite.")

    def task_predict(**kwargs):
        run_date = to_paris_time(kwargs["logical_date"])
        batch_id = kwargs["run_id"]
        run_predict(run_date, batch_id)

    extract = PythonOperator(
        task_id="extract_bronze",
        python_callable=task_extract,
    )

    transform = PythonOperator(
        task_id="transform_silver",
        python_callable=task_transform,
    )

    load = PythonOperator(
        task_id="load_gold",
        python_callable=task_load,
    )

    build_ml_features = PythonOperator(
        task_id="build_ml_features",
        python_callable=task_build_features,
    )

    predict_aqi = PythonOperator(
        task_id="predict_aqi",
        python_callable=task_predict,
    )

    extract >> transform >> [load, build_ml_features]
    build_ml_features >> predict_aqi
