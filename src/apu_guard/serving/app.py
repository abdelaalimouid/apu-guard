"""Scoring API, deployed on Kubernetes.

It loads the champion model from the MLflow registry and scores feature windows sent to it.
Readiness fails until a champion exists, so Kubernetes never routes traffic to a pod without a model.

    GET  /live    the process is up (liveness)
    GET  /health  a champion model is loaded (readiness)
    GET  /model   which model is serving
    POST /score   {"windows": [{"load_share": 0.1, "tp3_mean": 9.0, ...}, ...]}
"""
import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from apu_guard import scoring

app = FastAPI(title="APU anomaly scoring", version="0.1.0")


class ScoreRequest(BaseModel):
    windows: list[dict[str, float]]


def _model() -> dict:
    params = scoring.load_champion()
    if params is None:
        raise HTTPException(status_code=503, detail="no champion model in the registry yet")
    return params


@app.get("/live")
def live() -> dict:
    return {"status": "alive"}


@app.get("/health")
def health() -> dict:
    return {"status": "ready", "model_version": _model()["version"]}


@app.get("/model")
def model() -> dict:
    p = _model()
    return {"version": p["version"], "features": p["features"], "components": p["k"], "threshold": p["threshold"]}


@app.post("/score")
def score(req: ScoreRequest) -> dict:
    p = _model()
    missing = sorted({f for w in req.windows for f in p["features"] if f not in w})
    if missing:
        raise HTTPException(status_code=422, detail=f"missing features: {missing}")
    X = np.array([[w[f] for f in p["features"]] for w in req.windows], dtype=float)
    s = scoring.score_matrix(X, p)
    return {
        "model_version": p["version"],
        "threshold": p["threshold"],
        "results": [{"score": float(v), "is_anomaly": bool(v > p["threshold"])} for v in s],
    }
