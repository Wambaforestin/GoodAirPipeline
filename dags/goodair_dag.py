from datetime import datetime, timedelta

from airflow.sdk import DAG
from airflow.providers.standard.operators.python import PythonOperator

from src.extract.extract_apis import run_extract
from src.transform.transform_silver import run_transform
from src.load.load_gold import run_load


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
        run_date = kwargs["logical_date"]
        run_extract(run_date)

    def task_transform(**kwargs):
        run_date = kwargs["logical_date"]
        success = run_transform(run_date)
        if not success:
            raise ValueError("Transformation échouée : aucune donnée valide.")

    def task_load(**kwargs):
        run_date = kwargs["logical_date"]
        batch_id = kwargs["run_id"]
        run_load(run_date, batch_id)

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

    extract >> transform >> load