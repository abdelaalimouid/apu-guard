# How apu-guard works, part by part

This document explains every component: what it does, why it is built this way, how to run it, and what to look at. Read it with the architecture figure in the README.

## The problem

The compressor (APU) on a Porto metro car makes the compressed air for the suspension, couplers and sanders. An air leak makes it run longer and longer; if nobody notices, the pressure falls below 7 bar and the car leaves service. The operator wants a warning hours ahead.

There are no labels on individual readings, only a handful of failure reports. So the model learns what **normal** looks like on two healthy months and flags what does not fit: unsupervised anomaly detection. And "normal" changes (summer heat, timetables, repairs), so the model must be retrained safely, without letting a worse model reach production. That is the MLOps part.

## The data path (slide 2)

### 1. Replay producer: `src/apu_guard/producer/replay.py`
- **What:** reads MetroPT-3 (1.5 M readings, one every 10 s, Feb–Aug 2020) and sends each one to Kafka as JSON, keyed by the unit id.
- **Why replay:** there is no live train. Each message keeps its original timestamp (*event time*), so the rest of the system behaves exactly as it would live. `--speed 1000` plays one real hour in 3.6 s; `--speed 0` sends as fast as possible.
- **Design choices:** idempotent producer (no duplicates on retry), `acks=all` (the broker confirms every write), lz4 compression and small batches (`linger.ms`) for throughput.
- **Run:** `make replay FROM=2020-02-01 TO=2020-07-10` (backfill), then `make replay FROM=2020-07-10 TO=2020-07-18 SPEED=1000` (live demo).

### 2. Kafka: service `broker`
- **What:** an ordered, durable log of every reading (topic `apu.sensors.raw`, 3 partitions).
- **Why:** the producer and Spark don't have to run at the same time. If Spark crashes, it restarts from its last committed offset, and history can be replayed.
- **Two addresses:** `localhost:9092` for programs on the Mac (the producer), `broker:29092` for other containers (Spark). Same broker, two listeners.
- **KRaft mode:** Kafka manages its own metadata, with no ZooKeeper.

### 3. Spark Structured Streaming: `src/apu_guard/streaming/job.py` + `src/apu_guard/features.py`
- **What:** reads Kafka, parses the JSON, and runs two queries in one application:
  1. **bronze**: every raw reading to HDFS as Parquet, one folder per day;
  2. **features**: 10-minute windows by event time (load share, pressure min/mean/max, motor current, oil temperature, …) to HDFS silver, PostgreSQL, and live scoring.
- **Event time and watermark:** windows are cut on the reading's own timestamp, not on arrival time. The 2-minute watermark tells Spark how long to wait for late readings before closing a window.
- **Restart-safe:** checkpoints live on HDFS. After a crash Spark resumes from the last committed Kafka offsets. The Postgres writes are *upserts* (insert or update by window), so a replayed window is never duplicated.
- **One feature definition:** `features.py` is used by the stream *and* by training, so the model is scored on exactly the features it learned from. Mismatched features between training and serving are one of the most common MLOps bugs.
- **Data quality:** a window where the pressure sensor does not move at all while the motor runs is flagged `tp3_flat`. Such windows are reported as sensor faults, never as anomalies, and never used for training. The physics preprint found this sensor frozen for up to 62 h.
- **Run:** `make stream`, logs with `make stream-logs`, Spark UI on http://localhost:8080 and http://localhost:4040.

### 4. HDFS: services `namenode`, `datanode1`, `datanode2`
- **What:** the history. `/apu/bronze/readings` holds raw readings, `/apu/silver/features_10min` the feature windows, `/apu/checkpoints` Spark's progress.
- **Why:** cheap, append-only, distributed storage that training reads from. Replication is 2, so every block lives on both DataNodes. In a cloud deployment this role goes to S3 with Iceberg or Delta.
- **Built from** the professor's multi-arch Hadoop image (works on Apple Silicon). UI: http://localhost:9870.

### 5. PostgreSQL: service `postgres`, schema in `infra/postgres/init.sql`
- **What:** the latest features, scores and alarms, for the dashboard. One server also holds the Airflow and MLflow metadata in separate databases.
- **Why not query HDFS:** a dashboard asks "the last hour, now" many times a minute. HDFS is built for big scans; a database answers that kind of query in milliseconds.
- **The `alarms` view:** an alarm needs three anomalous windows in a row (30 min), so one noisy window does not page anyone.

### 6. Grafana: service `grafana`, dashboard in `infra/grafana/dashboards/apu.json`
- **What:**
  - live stat tiles (windows stored, windows in the last minute, champion model version, number of alarms);
  - panel pressure with the 7 bar line;
  - load share with the duty-rule line;
  - anomaly score against the threshold;
  - alarms and frozen-sensor flags;
  - data coverage and oil temperature;
  - the five failure reports as red annotations.
- **Dashboards as code:** the data source and dashboard are files in the repo, loaded at start (no manual clicks).
- **Open:** http://localhost:3000. Anonymous viewing is on; the admin login is admin/admin.

## The ML loop (slide 3)

### 7. Model: Spark ML StandardScaler + PCA (`src/apu_guard/training/pipeline.py`)
- **Training data:** the two healthy calibration months (February–March 2020). Half-empty windows, frozen-sensor windows and the days around non-failure log entries are left out.
- **Model:**
  - Standardise the 10 features, then keep the fewest principal components that explain 90% of the variance. The number is chosen inside the script, not by hand.
  - The anomaly score is the reconstruction error: how far a window is from the patterns of normal operation.
  - The threshold is the 99.5th percentile of the *training* scores. It is never tuned on the failures.
- **Why PCA:** it is simple, explainable and fast. Published benchmarks show a PCA baseline beats many deep models on time-series anomaly detection when the evaluation is done properly.
- **Portable copy:** the Spark pipeline is logged to MLflow as a Spark model, and its parameters are also logged as a small JSON file. The stream and the API score with numpy from that JSON (`scoring.py`), so they need no Spark runtime.

### 8. Evaluation: `src/apu_guard/training/metrics.py`
Event-level, the way an operator experiences it (protocol of Troshin et al. 2026):
- **Warning zone:** 7 days to 2 h before a failure report. An alarm episode that starts there is a useful warning, and its lead time is recorded.
- **Late zone:** 2 h before to 24 h after a report.
- **Episodes:** alarms less than 1 h apart merge into one episode.
- **False alarms:** episodes that start outside every zone, counted **per 1000 hours** of recorded data.
- **Baseline:** the duty rule (compressor loaded more than half of the last hour). Every model is compared with it.
- **Caution:** with a 7-day zone, a noisy rule fires *somewhere* in the zone by chance (about 60% of the time at 5.7 false episodes per 1000 h). So read "warned" together with the false-alarm rate, never alone.

### 9. MLflow + SeaweedFS: services `mlflow`, `seaweedfs`
- **Tracking:** every training run logs its settings, metrics, the evaluation JSON and the model.
- **Registry:** each trained model becomes a numbered version of `apu-anomaly`. The alias **`champion`** marks the version in production, and the stream and API always load `champion`, never a file path.
- **Storage:** metadata in Postgres, model files in an S3-compatible object store. SeaweedFS fills the role MinIO has on the course slide, because MinIO's free edition was archived in April 2026 and gets no more security fixes. Any S3 store works through `MLFLOW_S3_ENDPOINT_URL`; in the cloud it would be S3, GCS or Azure Blob.
- **UI:** http://localhost:5050.

### 10. Airflow: `dags/apu_retrain.py`
- **What:** three tasks, extract features from HDFS → train → evaluate and promote.
- **The gate:**
  - The first model becomes champion.
  - A later model must warn at least as many failures, with no more false alarms than the current champion, on the same period.
  - Otherwise it is registered but not promoted.
  - The decision is written as a tag on the model version.
- **After a promotion**, every stored window is re-scored with the new champion (backfill). The live stream picks up the new model within a minute without a restart.
- **Run:** `make airflow` then `make train`, or trigger it in the UI at http://localhost:8090.

### 11. Kubernetes + Argo CD: `infra/k8s`, `infra/argocd`
- **What:** the scoring API (FastAPI, `src/apu_guard/serving/app.py`) runs as a Deployment in the `apu-staging` namespace on minikube.
- **Probes:** readiness checks that a champion model is loaded, so no traffic reaches a pod without a model; liveness checks the process.
- **GitOps:** Argo CD watches `infra/k8s/overlays/staging` in the GitHub repo and keeps the cluster equal to it (automatic sync, self-heal). Deploying a new version = a commit that changes the image tag. Promoting to prod = a reviewed commit to a prod overlay.
- **Run:** `make k8s-up`, then `make k8s-deploy`, then `make k8s-test`.

## Order to run everything

```bash
make up                                         # platform
make stream                                     # streaming job
make replay FROM=2020-02-01 TO=2020-07-10       # backfill five months (about 2 minutes)
make airflow && make train                      # train, evaluate, promote, re-score
make replay FROM=2020-07-10 TO=2020-07-18 SPEED=1000   # live: failures 4 and 5 arrive on the dashboard
make k8s-up && make k8s-deploy && make k8s-test # scoring API on Kubernetes
```

## Results (end-to-end run, 4 Nov 2026, MacBook, Docker Desktop with 8 GB)

| Step | Result |
|---|---|
| Replay producer | 1,143,969 readings (1 Feb – 10 Jul 2020) sent in 7.3 s, about 157,000 messages/s |
| Spark streaming | 19,268 ten-minute windows in 11 micro-batches of about 10 s each |
| HDFS | bronze 21.9 MB in 159 daily folders, silver 1.5 MB; replication 2.0, status HEALTHY |
| Data quality | 504 windows (84 h) flagged as frozen pressure sensor, never scored as anomalies |
| Training (Airflow, 27 s) | 6,650 healthy windows (Feb–Mar); PCA kept 3 components (90.6% of variance); threshold 7.04 |
| Registry | `apu-anomaly` v1 promoted to `@champion` (gate: first model); 19,074 windows re-scored |
| Evaluation, 1 Apr – 10 Jul | model: 3/3 failures warned, 8.67 false alarms per 1000 h; duty rule: 3/3, 7.95 per 1000 h |
| First alarm before each report | failure 1: 6.4 h · failure 2: 1.7 h · failure 3: 7.8 h · failure 4: 4.6 h (live) · failure 5: 1.1 h (live) |
| Live scoring | 10–18 July replayed at 2000× (62,295 readings in 389 s), every window scored by model v1 as it arrived |
| Scoring API | normal window → 0.80 (normal); leak-like window → 33.7 (anomaly) |
| Kubernetes | pod Ready 1/1 in `apu-staging` on minikube; readiness = champion v1 loaded from MLflow on the host |
| Argo CD | v3.5.6 installed, application registered; it syncs once the repo is readable (public, or a read-only token added in Argo CD) |

**Reading these numbers honestly**
- **No better than the baseline.** The PCA model ties the one-line duty rule, with slightly more false alarms.
- **The early warnings are luck.** Both rules' "warnings" 139–162 h ahead are unrelated episodes that a 7-day zone happens to catch.
- **What matters is the alarm before each report.** It fires within about an hour of each leak's visible start. Two of three beat the operator's 2-hour target.
- **The leaks themselves are fast.** They develop in hours, so earlier warnings would need physics features (air-consumption share, Troshin et al. 2026), not a bigger model.
