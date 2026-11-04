# MLflow tracking server + model registry.
# Metadata in Postgres, model files in the S3-compatible object store (SeaweedFS).
FROM python:3.12-slim
RUN pip install --no-cache-dir "mlflow==3.18.0" "psycopg2-binary==2.9.10" "boto3>=1.35,<2"
COPY start.sh /start.sh
RUN chmod +x /start.sh
ENTRYPOINT ["/start.sh"]
