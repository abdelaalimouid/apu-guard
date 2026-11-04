# apu-guard

Streaming failure detection for a metro train's air compressor, built as a complete MLOps system on open industrial data ([MetroPT-3](https://archive.ics.uci.edu/dataset/791/metropt+3+dataset), Porto metro, 2020).

Sensor readings are replayed into **Kafka**, turned into 10-minute features by **Spark Structured Streaming**, stored in **HDFS** and **PostgreSQL**, and shown live in **Grafana**. An **Airflow** pipeline retrains a **Spark ML** anomaly model, tracks it in **MLflow**, and promotes it only if it beats the current champion. The scoring API runs on **Kubernetes**, deployed by **Argo CD** from this repo.

```
 MetroPT-3 ──► replay producer ──► Kafka ──► Spark Structured Streaming ──┬──► HDFS (bronze: readings, silver: features)
                                                                         ├──► PostgreSQL ──► Grafana dashboard
                                                                         └──► live scores (champion model)
 HDFS silver ──► Airflow: extract ─► train (Spark ML) ─► evaluate + gate ──► MLflow registry (+ S3 object store)
                                                                                 │ alias "champion"
 GitHub repo ──► Argo CD ──► Kubernetes (minikube): scoring API ◄────────────────┘
```

## Quickstart

Needs Docker Desktop with 8 GB or more, `uv`, and `minikube` for the Kubernetes part.

```bash
bash scripts/get_data.sh                          # download MetroPT-3 (not stored in Git)
make up                                           # platform
make stream                                       # streaming job on the Spark cluster
make replay FROM=2020-02-01 TO=2020-07-10         # backfill five months (about 10 s to send)
make airflow && make train                        # train, evaluate, promote, re-score
make replay FROM=2020-07-10 TO=2020-07-18 SPEED=1000   # live: failures 4 and 5 arrive on the dashboard
make k8s-up && make k8s-deploy && make k8s-test   # scoring API on Kubernetes via Argo CD
```

| UI | Address |
|---|---|
| Grafana dashboard | http://localhost:3000 |
| Spark master / running job | http://localhost:8080 / http://localhost:4040 |
| HDFS NameNode | http://localhost:9870 |
| MLflow | http://localhost:5050 |
| Airflow | http://localhost:8090 |

## How it works

[docs/WALKTHROUGH.md](docs/WALKTHROUGH.md) explains every component: what it does, why it is built that way, and what to look at. Exploration of the data is in [notebooks/01_explore.ipynb](notebooks/01_explore.ipynb).

## Repo layout

```
src/apu_guard/            config, features (shared by stream and training), scoring, db helpers
  producer/replay.py      MetroPT-3 -> Kafka, in event time
  streaming/job.py        Kafka -> HDFS + Postgres + live scores
  training/               pipeline (extract, train, evaluate and promote) and event-level metrics
  serving/app.py          FastAPI scoring service
dags/apu_retrain.py       Airflow DAG
infra/                    Dockerfiles, Postgres schema, Grafana dashboards, Kubernetes and Argo CD manifests
notebooks/                data exploration
tests/                    unit tests (metrics and scoring)
```

## Credits

- Data: Davari, Veloso, Ribeiro, Pereira and Gama (2021), MetroPT-3, UCI Machine Learning Repository, CC BY 4.0.
- Failure report times and evaluation protocol: Troshin, Komakhidze and Abakarov (2026), Zenodo, doi:10.5281/zenodo.23737435.
- Hadoop image: course material by Pr. Ziyati Houssaine (INPT).
