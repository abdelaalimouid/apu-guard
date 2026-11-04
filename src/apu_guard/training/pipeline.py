"""The three training steps the Airflow DAG runs: extract -> train -> evaluate and promote.

  extract   read the silver feature windows from HDFS (Spark) and snapshot them
  train     fit a Spark ML pipeline (StandardScaler + PCA) on the healthy calibration months,
            set the alarm threshold from training scores only, log everything to MLflow
  evaluate  replay the later months through the model, count warnings and false alarms with the
            event-level protocol, compare with the duty-rule baseline and the current champion,
            register the model, and give it the 'champion' alias only if it passes the gate
"""
import json
import logging
import os
from pathlib import Path

import numpy as np
import pandas as pd

from apu_guard import config, scoring
from apu_guard.training import metrics

log = logging.getLogger(__name__)
WORK = Path(os.environ.get("APU_WORK_DIR", "/tmp/apu-work"))


def _spark(app: str):
    from pyspark.sql import SparkSession

    return (
        SparkSession.builder.master("local[2]").appName(app)
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.driver.memory", "1g")
        .getOrCreate()
    )


def training_rows(pdf: pd.DataFrame) -> pd.DataFrame:
    """Healthy calibration months only: complete windows, no frozen sensor, no log-entry days."""
    t = pdf["window_start"]
    keep = (t >= config.TRAIN_START) & (t < config.TRAIN_END)
    keep &= pdf["n_rows"] >= config.MIN_ROWS
    keep &= ~pdf["tp3_flat"].fillna(False).astype(bool)
    keep &= ~metrics.in_any_zone(pd.Index(t)).to_numpy()
    return pdf[keep]


# ---------------------------------------------------------------- step 1
def extract(work_dir: Path = WORK) -> dict:
    spark = _spark("apu-extract")
    try:
        sdf = spark.read.parquet(config.SILVER).dropDuplicates(["window_start"])
        pdf = sdf.toPandas().sort_values("window_start").reset_index(drop=True)
    finally:
        spark.stop()
    work_dir.mkdir(parents=True, exist_ok=True)
    path = work_dir / "features_snapshot.parquet"
    pdf.to_parquet(path, index=False)
    info = {"path": str(path), "windows": len(pdf),
            "from": str(pdf["window_start"].min()), "to": str(pdf["window_start"].max())}
    log.info("snapshot: %s", info)
    return info


# ---------------------------------------------------------------- step 2
def train(snapshot_path: str) -> dict:
    import mlflow
    import mlflow.spark
    from pyspark.ml import Pipeline
    from pyspark.ml.feature import PCA, StandardScaler, VectorAssembler

    pdf = pd.read_parquet(snapshot_path)
    train_pdf = training_rows(pdf)
    if len(train_pdf) < 100:
        raise ValueError(f"only {len(train_pdf)} training windows; replay February-March first")

    spark = _spark("apu-train")
    try:
        sdf = spark.createDataFrame(train_pdf[config.FEATURES].astype(float))
        d = len(config.FEATURES)

        def pipeline(k: int) -> Pipeline:
            return Pipeline(stages=[
                VectorAssembler(inputCols=config.FEATURES, outputCol="raw"),
                StandardScaler(inputCol="raw", outputCol="z", withMean=True, withStd=True),
                PCA(k=k, inputCol="z", outputCol="pc"),
            ])

        explained = pipeline(d).fit(sdf).stages[-1].explainedVariance.toArray()
        k = int(np.searchsorted(np.cumsum(explained), config.PCA_VARIANCE) + 1)  # chosen in-script
        model = pipeline(k).fit(sdf)
        scaler, pca = model.stages[1], model.stages[2]
        params = {
            "features": config.FEATURES,
            "mean": scaler.mean.toArray().tolist(),
            "std": scaler.std.toArray().tolist(),
            "components": pca.pc.toArray().tolist(),
            "k": k,
            "min_rows": config.MIN_ROWS,
        }
        train_scores = scoring.score_matrix(train_pdf[config.FEATURES].to_numpy(dtype=float), params)
        params["threshold"] = float(np.quantile(train_scores, config.THRESHOLD_QUANTILE))

        mlflow.set_experiment(config.EXPERIMENT)
        with mlflow.start_run(run_name=f"pca-k{k}") as run:
            mlflow.log_params({
                "model": "StandardScaler+PCA reconstruction error",
                "features": ",".join(config.FEATURES), "k": k, "variance_target": config.PCA_VARIANCE,
                "threshold_quantile": config.THRESHOLD_QUANTILE, "sustain_windows": config.SUSTAIN_WINDOWS,
                "train_start": str(config.TRAIN_START.date()), "train_end": str(config.TRAIN_END.date()),
                "train_windows": len(train_pdf), "snapshot_windows": len(pdf),
            })
            mlflow.log_metrics({"explained_variance": float(np.cumsum(explained)[k - 1]),
                                "threshold": params["threshold"]})
            mlflow.log_dict(params, "serving/params.json")  # the portable copy the stream and API use
            info = mlflow.spark.log_model(model, artifact_path="model")
    finally:
        spark.stop()
    out = {"run_id": run.info.run_id, "model_uri": info.model_uri, "k": k, "threshold": params["threshold"]}
    log.info("trained: %s", out)
    return out


# ---------------------------------------------------------------- step 3
def evaluate_and_promote(snapshot_path: str, trained: dict) -> dict:
    import mlflow
    from mlflow import MlflowClient

    client = MlflowClient()
    pdf = pd.read_parquet(snapshot_path)
    params_path = mlflow.artifacts.download_artifacts(run_id=trained["run_id"], artifact_path="serving/params.json")
    with open(params_path) as fh:
        params = json.load(fh)

    test = pdf[(pdf["window_start"] >= config.TRAIN_END) & (pdf["n_rows"] >= config.MIN_ROWS)]
    test = test.set_index("window_start").sort_index()
    scored = scoring.score_frame(test.reset_index(), params).set_index("window_start")
    model_alarm = metrics.sustained(scored["is_anomaly"], config.SUSTAIN_WINDOWS)
    m_model = metrics.event_metrics(test, model_alarm.reindex(test.index, fill_value=False))
    m_duty = metrics.event_metrics(test, metrics.duty_rule(test))

    with mlflow.start_run(run_id=trained["run_id"]):
        for prefix, m in (("model", m_model), ("duty_rule", m_duty)):
            mlflow.log_metrics({f"{prefix}_warned": m["warned"], f"{prefix}_false_per_1000h": m["false_per_1000h"],
                                f"{prefix}_false_episodes": m["false_episodes"]})
        mlflow.log_dict({"model": m_model, "duty_rule": m_duty}, "evaluation/event_metrics.json")

    mv = mlflow.register_model(trained["model_uri"], config.MODEL_NAME)
    try:
        champ = client.get_model_version_by_alias(config.MODEL_NAME, "champion")
        cm = client.get_run(champ.run_id).data.metrics
        champ_metrics = {"warned": cm.get("model_warned", 0), "false_per_1000h": cm.get("model_false_per_1000h", 1e9)}
    except Exception:
        champ, champ_metrics = None, None

    # The gate: the first model becomes champion; later ones must warn at least as many failures
    # with no more false alarms than the current champion, on the same evaluation period.
    if champ is None:
        promote, reason = True, "first model"
    elif m_model["warned"] >= champ_metrics["warned"] and m_model["false_per_1000h"] <= champ_metrics["false_per_1000h"]:
        promote, reason = True, f"beats champion v{champ.version}"
    else:
        promote, reason = False, f"does not beat champion v{champ.version}"

    client.set_model_version_tag(config.MODEL_NAME, mv.version, "gate", reason)
    if promote:
        client.set_registered_model_alias(config.MODEL_NAME, "champion", mv.version)
        rescored = rescore_all(params | {"version": mv.version})
    else:
        rescored = 0
    out = {"version": mv.version, "promoted": promote, "reason": reason, "model": m_model,
           "duty_rule": m_duty, "rescored_windows": rescored}
    log.info("evaluation: %s", json.dumps(out, default=str))
    return out


def rescore_all(params: dict) -> int:
    """After a promotion, score every stored window with the new champion (backfill)."""
    from apu_guard import db

    feats = db.read_features()
    return db.upsert_scores(scoring.score_frame(feats, params)) if not feats.empty else 0
