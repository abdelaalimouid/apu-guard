#!/usr/bin/env bash
# Create the artifact bucket if needed, then start MLflow.
set -euo pipefail

python - <<'PY'
import os, time
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

s3 = boto3.client("s3", endpoint_url=os.environ["MLFLOW_S3_ENDPOINT_URL"],
                  config=Config(s3={"addressing_style": "path"}))
for _ in range(60):
    try:
        try:
            s3.create_bucket(Bucket="mlflow-artifacts")
        except ClientError as err:  # an existing bucket is fine
            if err.response["Error"]["Code"] not in ("BucketAlreadyExists", "BucketAlreadyOwnedByYou"):
                raise
        print("artifact bucket ready", flush=True)
        break
    except Exception as exc:  # the object store may still be starting
        print("waiting for the object store:", exc, flush=True)
        time.sleep(2)
else:
    raise SystemExit("object store not reachable")
PY

EXTRA=()
# Newer MLflow versions check the Host header; allow other containers and minikube to call it.
if mlflow server --help 2>/dev/null | grep -q -- "--allowed-hosts"; then
  EXTRA+=(--allowed-hosts "*")
fi

exec mlflow server --host 0.0.0.0 --port 5000 --workers 1 \
  --backend-store-uri postgresql+psycopg2://mlflow:mlflow@postgres:5432/mlflow \
  --artifacts-destination s3://mlflow-artifacts --serve-artifacts \
  "${EXTRA[@]}"
