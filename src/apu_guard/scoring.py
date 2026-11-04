"""Scoring with the champion model, using only numpy.

Training fits a Spark ML pipeline (scaler + PCA). Its parameters are exported as a small JSON file
(mean, std, principal components, threshold), so the streaming job and the Kubernetes API can score
without a Spark runtime. The score is the PCA reconstruction error: how far a window is from the
"normal" patterns learned on February and March.
"""
import json
import logging
import time

import numpy as np

from apu_guard import config

log = logging.getLogger(__name__)


def score_matrix(X: np.ndarray, params: dict) -> np.ndarray:
    mean = np.asarray(params["mean"], dtype=float)
    std = np.asarray(params["std"], dtype=float)
    P = np.asarray(params["components"], dtype=float)        # d x k
    X = np.asarray(X, dtype=float)
    z = np.divide(X - mean, std, out=np.zeros_like(X), where=std > 0)  # same rule as Spark's StandardScaler
    residual = z - z @ P @ P.T
    return (residual * residual).sum(axis=1)


def score_frame(features, params: dict):
    """Feature windows (pandas) -> score rows. Half-empty windows are not scored;
    frozen-sensor windows are marked as sensor faults instead of anomalies."""
    d = features[features["n_rows"] >= params.get("min_rows", config.MIN_ROWS)].copy()
    if d.empty:
        return d.assign(score=[], threshold=[], is_anomaly=[], sensor_fault=[], model_version=[])
    d["score"] = score_matrix(d[params["features"]].to_numpy(dtype=float), params)
    d["threshold"] = float(params["threshold"])
    d["sensor_fault"] = d["tp3_flat"].fillna(False).astype(bool)
    d["is_anomaly"] = (d["score"] > d["threshold"]) & ~d["sensor_fault"]
    d["model_version"] = str(params.get("version", "local"))
    return d[["window_start", "score", "threshold", "is_anomaly", "sensor_fault", "model_version"]]


_cache = {"loaded_at": 0.0, "params": None}


def load_champion(name: str = config.MODEL_NAME, refresh_seconds: float = 60.0):
    """The current champion's parameters from the MLflow registry (alias 'champion').
    Cached for a minute, so a newly promoted model is picked up without restarting anything."""
    if time.time() - _cache["loaded_at"] < refresh_seconds:
        return _cache["params"]
    params = None
    try:
        from mlflow import MlflowClient, artifacts

        mv = MlflowClient().get_model_version_by_alias(name, "champion")
        path = artifacts.download_artifacts(run_id=mv.run_id, artifact_path="serving/params.json")
        with open(path) as fh:
            params = json.load(fh)
        params["version"] = mv.version
    except Exception as exc:  # no champion yet, or MLflow not reachable
        log.warning("no champion model available: %s", exc)
    _cache.update(loaded_at=time.time(), params=params)
    return params
