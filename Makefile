# apu-guard commands. Run `make help` for the list.
SPARK_KAFKA := org.apache.spark:spark-sql-kafka-0-10_2.13:4.2.1
FROM ?= 2020-02-01
TO ?= 2020-07-10
SPEED ?= 0
TAG ?= v1
IMAGE := apu-guard-serving:0.1.0
ARGOCD_VERSION ?= v3.5.6

.PHONY: help up down ps airflow replay stream stream-logs stream-stop train test k8s-up k8s-deploy argocd k8s-test

help:
	@grep -E '^[a-z0-9-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-12s %s\n", $$1, $$2}'

up: ## start the platform (HDFS, Kafka, Spark, Postgres, object store, MLflow, Grafana)
	docker compose up -d --build

down: ## stop everything (data volumes are kept)
	docker compose --profile airflow down

ps: ## show running containers
	docker compose --profile airflow ps

replay: ## send MetroPT-3 readings to Kafka: make replay FROM=2020-07-10 TO=2020-07-18 SPEED=1000
	uv run python -m apu_guard.producer.replay --start $(FROM) --end $(TO) --speed $(SPEED)

stream: ## start the Spark streaming job on the cluster (logs: make stream-logs)
	docker compose exec -d spark-master sh -c '/opt/spark/bin/spark-submit \
	  --master spark://spark-master:7077 --conf spark.jars.ivy=/tmp/ivy --packages $(SPARK_KAFKA) \
	  --conf spark.driver.memory=900m --conf spark.executor.memory=900m --conf spark.cores.max=2 \
	  /opt/apu/src/apu_guard/streaming/job.py --checkpoint-tag $(TAG) > /tmp/stream.log 2>&1'

stream-logs: ## follow the streaming job's log
	docker compose exec spark-master tail -n 50 -f /tmp/stream.log

stream-stop: ## stop the streaming job
	docker compose exec spark-master pkill -f apu_guard/streaming/job.py || true

airflow: ## start Airflow (UI on http://localhost:8090)
	docker compose --profile airflow up -d --build airflow

train: ## run the retraining DAG once, in the foreground
	docker compose --profile airflow exec airflow airflow dags test apu_retrain

test: ## unit tests
	uv run pytest -q

k8s-up: ## start minikube and install Argo CD
	minikube start --driver=docker --memory=3072 --cpus=2
	kubectl create namespace argocd --dry-run=client -o yaml | kubectl apply -f -
	kubectl apply -n argocd --server-side -f https://raw.githubusercontent.com/argoproj/argo-cd/$(ARGOCD_VERSION)/manifests/install.yaml

k8s-deploy: ## build the scoring image, load it into minikube, register the Argo CD application
	docker build -f infra/serving/Dockerfile -t $(IMAGE) .
	minikube image load $(IMAGE)
	kubectl apply -f infra/argocd/application-staging.yaml

k8s-test: ## call the scoring API inside the cluster
	kubectl -n apu-staging port-forward svc/apu-scoring 8000:80 >/dev/null 2>&1 & sleep 3; \
	curl -s localhost:8000/health; echo; curl -s localhost:8000/model; echo; kill %1
