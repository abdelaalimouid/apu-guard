"""
### APU anomaly model: retrain, evaluate, promote

1. **extract_features**: snapshot the 10-minute feature windows from HDFS (silver layer).
2. **train_model**: fit StandardScaler + PCA (Spark ML) on the healthy calibration months,
   log parameters, metrics and the model to MLflow.
3. **evaluate_and_promote**: count warned failures and false alarms on the later months,
   compare with the duty-rule baseline and the current champion, register the model and move
   the `champion` alias only if it passes the gate. A promotion re-scores every stored window.

Trigger it from the UI, or run `make train`.
"""
from datetime import datetime

from airflow.sdk import dag, task


@dag(
    dag_id="apu_retrain",
    schedule=None,                      # manual or event-triggered; a weekly schedule is one line away
    start_date=datetime(2026, 11, 1),
    catchup=False,
    tags=["apu", "mlops"],
    doc_md=__doc__,
)
def apu_retrain():
    @task
    def extract_features() -> dict:
        from apu_guard.training import pipeline
        return pipeline.extract()

    @task
    def train_model(snapshot: dict) -> dict:
        from apu_guard.training import pipeline
        return pipeline.train(snapshot["path"])

    @task
    def evaluate_and_promote(snapshot: dict, trained: dict) -> dict:
        from apu_guard.training import pipeline
        return pipeline.evaluate_and_promote(snapshot["path"], trained)

    snapshot = extract_features()
    evaluate_and_promote(snapshot, train_model(snapshot))


apu_retrain()
