import os
import joblib
import pandas as pd
from io import BytesIO
from sqlalchemy import text

from src.utils.connections import (
    get_minio_client,
    get_sql_engine,
    get_partition_path,
    logger,
)

MODEL_PATH = os.path.join(os.path.dirname(__file__), "models/aqi_model.pkl")
SEUIL_ALERTE = 100

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


def load_model():
    """Charge le modèle depuis le fichier .pkl."""
    model = joblib.load(MODEL_PATH)
    logger.info(f"Modèle chargé : {type(model).__name__} depuis {MODEL_PATH}")
    return model


def load_features(minio_client, run_date):
    """
    Lit le Parquet de features depuis Silver/features-ml/.
    Généré par feature_engineering.py au créneau courant.
    """
    partition = get_partition_path("features-ml", run_date)
    object_path = f"{partition}features.parquet"

    response = minio_client.get_object("silver", object_path)
    df = pd.read_parquet(BytesIO(response.read()))

    logger.info(f"Features chargées : {len(df)} lignes depuis silver/{object_path}")
    return df


def apply_alert_rule(aqi_predit):
    """
    Règle métier : si AQI prédit > 100 → ALERTE. sinon OK.
    Le modèle prédit une valeur continue. c est cette fonction qui décide de l alerte.
    """
    if aqi_predit > SEUIL_ALERTE:
        return "ALERTE"
    else:
        return "OK"


def write_predictions(engine, df_predictions, batch_id):
    """
    Écrit les prédictions dans Gold.AlertesPredites via MERGE.
    Table sans FK — NomVille et IDTemps sont stockés directement.
    Idempotent : si la prédiction existe déjà pour (NomVille. IDTemps). on la met à jour.
    """
    merge_sql = text("""
    MERGE Gold.AlertesPredites AS target
    USING (
        SELECT
            :nom_ville         AS NomVille,
            :id_temps          AS IDTemps,
            :date_heure_predite AS DateHeurePredite,
            :aqi_predit        AS AQI_Predit,
            :alerte            AS Alerte,
            :batch_id          AS IDBatch
    ) AS source
    ON target.NomVille = source.NomVille
    AND target.IDTemps = source.IDTemps

    WHEN MATCHED THEN UPDATE SET
        target.AQI_Predit        = source.AQI_Predit,
        target.Alerte            = source.Alerte,
        target.DateHeurePredite  = source.DateHeurePredite,
        target.DatePrediction    = GETDATE() AT TIME ZONE 'UTC'
                                   AT TIME ZONE 'Romance Standard Time',
        target.IDBatch           = source.IDBatch

    WHEN NOT MATCHED THEN INSERT (
        NomVille, IDTemps, DateHeurePredite, AQI_Predit, Alerte, DatePrediction, IDBatch
    ) VALUES (
        source.NomVille,
        source.IDTemps,
        source.DateHeurePredite,
        source.AQI_Predit,
        source.Alerte,
        GETDATE() AT TIME ZONE 'UTC' AT TIME ZONE 'Romance Standard Time',
        source.IDBatch
    );
""")

    nb_alertes = 0

    with engine.connect() as conn:
        for _, row in df_predictions.iterrows():
            conn.execute(
                merge_sql,
                {
                    "nom_ville": row["NomVille"],
                    "id_temps": int(row["IDTemps"]),
                    "date_heure_predite" : pd.to_datetime(str(row["IDTemps"]), format="%Y%m%d%H"),
                    "aqi_predit": float(row["AQI_Predit"]),
                    "alerte": row["Alerte"],
                    "batch_id": batch_id,
                },
            )
            if row["Alerte"] == "ALERTE":
                nb_alertes += 1
                logger.warning(
                    f"ALERTE POLLUTION — {row['NomVille']} "
                    f"IDTemps={row['IDTemps']} "
                    f"AQI prédit={row['AQI_Predit']:.1f}"
                )
        conn.commit()

    logger.info(
        f"{len(df_predictions)} prédictions écrites dans Gold.AlertesPredites. "
        f"{nb_alertes} alerte(s) détectée(s)."
    )


def run_predict(run_date, batch_id):
    """
    Point d entrée principal. Appelé par le DAG Airflow.
    1. Charge le modèle
    2. Lit les features depuis Silver/features-ml/
    3. Prédit l AQI pour chaque ville et chaque heure future
    4. Applique la règle métier (> 100 = ALERTE)
    5. Écrit dans Gold.AlertesPredites
    """
    minio_client = get_minio_client()
    engine = get_sql_engine()
    model = load_model()

    df = load_features(minio_client, run_date)

    missing = [f for f in FEATURES if f not in df.columns]
    assert not missing, f"Features manquantes : {missing}"

    X = df[FEATURES]
    aqi_predits = model.predict(X)

    df["AQI_Predit"] = aqi_predits
    df["Alerte"] = df["AQI_Predit"].apply(apply_alert_rule)

    logger.info(
        f"Prédictions générées : {len(df)} lignes. "
        f"{(df['Alerte'] == 'ALERTE').sum()} alerte(s)."
    )

    write_predictions(engine, df, batch_id)

    return True
