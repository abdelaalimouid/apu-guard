# Spark 4.2.1 with the Python libraries the streaming job needs on the driver:
# pandas/pyarrow (toPandas), psycopg2 (writes to Postgres), mlflow-skinny (loads the champion model).
FROM apache/spark:4.2.1-scala2.13-java17-python3-ubuntu
USER root
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3-pip \
 && rm -rf /var/lib/apt/lists/* \
 && PKGS="numpy==2.2.6 pandas==2.3.3 pyarrow==21.0.0 psycopg2-binary==2.9.10 mlflow-skinny==3.18.0" \
 && (pip3 install --no-cache-dir --break-system-packages $PKGS || pip3 install --no-cache-dir $PKGS) \
 && mkdir -p /tmp/ivy && chown -R spark:spark /tmp/ivy
USER spark
