import os
import smtplib
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from airflow.sdk import DAG
from airflow.providers.standard.operators.python import PythonOperator

from src.extract.extract_apis import run_extract
from src.transform.transform_silver import run_transform
from src.load.load_gold import run_load
from src.ml.feature_engineering import build_features
from src.ml.predict import run_predict
from src.utils.connections import to_paris_time


def send_email_smtp(subject, html_content):
    smtp_user = os.getenv("AIRFLOW__SMTP__SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    recipients = os.getenv("ALERT_EMAILS").split(",")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(html_content, "html"))

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.ehlo()
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.sendmail(smtp_user, recipients, msg.as_string())


def on_failure_callback(context):
    task_id = context["task_instance"].task_id
    dag_id = context["dag"].dag_id
    exec_date = to_paris_time(context["logical_date"])

    send_email_smtp(
        subject=f"Projet MSPR: GoodAir Échec - {dag_id} / {task_id}",
        html_content=f"""
        <html>
        <body style="font-family: Arial, sans-serif; background-color: #f4f4f4; padding: 20px;">
            <div style="max-width: 600px; margin: auto; background: white;
                        border-radius: 8px; overflow: hidden;
                        box-shadow: 0 2px 8px rgba(0,0,0,0.1);">

                <div style="background-color: #c0392b; padding: 20px;">
                    <h2 style="color: white; margin: 0;">
                        Échec du Pipeline GoodAir
                    </h2>
                </div>

                <div style="padding: 24px;">
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="padding: 8px; font-weight: bold; color: #555; width: 120px;">Le DAG</td>
                            <td style="padding: 8px; color: #222;">{dag_id}</td>
                        </tr>
                        <tr style="background-color: #f9f9f9;">
                            <td style="padding: 8px; font-weight: bold; color: #555;">La tâche</td>
                            <td style="padding: 8px; color: #222;">{task_id}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px; font-weight: bold; color: #555;">Date et heure</td>
                            <td style="padding: 8px; color: #222;">{exec_date}</td>
                        </tr>
                    </table>

                    <div style="margin-top: 20px; padding: 12px;
                                background-color: #fdecea; border-left: 4px solid #c0392b;
                                border-radius: 4px;">
                        <p style="margin: 0; color: #c0392b;">
                            Consultez les logs Airflow pour plus de détails.
                        </p>
                    </div>
                </div>

                <div style="padding: 16px; background-color: #f4f4f4;
                            text-align: center; font-size: 12px; color: #999;">
                    Le Pipeline GoodAir de TotalGreen (EPSI MSPR) vous informe.
                </div>
            </div>
        </body>
        </html>
        """,
    )


def send_aqi_alert(city, aqi_predit, date_heure_predite):
    send_email_smtp(
        subject=f"Projet MSPR: GoodAir Alerte Pollution - {city}",
        html_content=f"""
        <html>
        <body style="font-family: Arial, sans-serif; background-color: #f4f4f4; padding: 20px;">
            <div style="max-width: 600px; margin: auto; background: white;
                        border-radius: 8px; overflow: hidden;
                        box-shadow: 0 2px 8px rgba(0,0,0,0.1);">

                <div style="background-color: #e67e22; padding: 20px;">
                    <h2 style="color: white; margin: 0;">
                        Alerte Qualité de l'Air
                    </h2>
                </div>

                <div style="padding: 24px;">
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="padding: 8px; font-weight: bold; color: #555; width: 160px;">Ville</td>
                            <td style="padding: 8px; color: #222;">{city}</td>
                        </tr>
                        <tr style="background-color: #f9f9f9;">
                            <td style="padding: 8px; font-weight: bold; color: #555;">AQI prédit</td>
                            <td style="padding: 8px;">
                                <span style="color: #c0392b; font-size: 18px; font-weight: bold;">
                                    {aqi_predit:.0f}
                                </span>
                                <span style="color: #999; font-size: 13px;">
                                    (seuil d'alerte : 100)
                                </span>
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 8px; font-weight: bold; color: #555;">Heure prévue</td>
                            <td style="padding: 8px; color: #222;">{date_heure_predite}</td>
                        </tr>
                    </table>

                    <div style="margin-top: 20px; padding: 12px;
                                background-color: #fef9e7; border-left: 4px solid #e67e22;
                                border-radius: 4px;">
                        <p style="margin: 0; color: #7d6608;">
                            Qualité de l'air dégradée prévue. Prenez les précautions nécessaires.
                        </p>
                    </div>
                </div>

                <div style="padding: 16px; background-color: #f4f4f4;
                            text-align: center; font-size: 12px; color: #999;">
                    Le Pipeline GoodAir de TotalGreen (EPSI MSPR) vous informe.
                </div>
            </div>
        </body>
        </html>
        """,
    )


default_args = {
    "owner": "goodair",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "on_failure_callback": on_failure_callback,
}

with DAG(
    dag_id="goodair_pipeline",
    default_args=default_args,
    description="Pipeline ETL horaire - Météo + Qualité de l'air + Prévision de l'AQI",
    schedule="@hourly",
    start_date=datetime(2026, 3, 25),
    catchup=False,
    tags=["goodair", "etl", "air_quality", "forecasting"],
) as dag:

    def task_extract(**kwargs):
        # raise ValueError("Test alerte email — erreur volontaire")
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
        run_predict(run_date, batch_id, send_aqi_alert)

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
