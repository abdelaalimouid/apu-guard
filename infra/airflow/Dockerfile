# Airflow 3.3.2 that can run Spark ML in local mode inside its tasks:
# a Java runtime for Spark, PySpark matching the cluster version, and the MLflow client.
FROM apache/airflow:3.3.2-python3.12
USER root
RUN apt-get update \
 && apt-get install -y --no-install-recommends default-jre-headless \
 && rm -rf /var/lib/apt/lists/* \
 && mkdir -p /opt/airflow/work && chown -R airflow:0 /opt/airflow/work
ENV JAVA_HOME=/usr/lib/jvm/default-java
USER airflow
RUN pip install --no-cache-dir "apache-airflow==3.3.2" "pyspark==4.2.1" "mlflow-skinny==3.18.0"
