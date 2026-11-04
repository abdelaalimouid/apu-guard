"""Spark Structured Streaming job: Kafka -> features -> HDFS + Postgres (+ live scores).

Two queries run in one Spark application:
  1. bronze: every raw reading, as Parquet on HDFS, one folder per day
  2. features: 10-minute windows by event time -> HDFS silver (Parquet) and Postgres,
     scored with the current champion model when one exists

Checkpoints on HDFS make it restart-safe: after a crash Spark resumes from the last committed
Kafka offsets, and the Postgres upserts make replays harmless.

Run it with `make stream` (spark-submit on the cluster).
"""
import argparse
import logging
import sys

sys.path.insert(0, "/opt/apu/src")  # the repo's src/ is mounted here in the Spark containers

from pyspark.sql import SparkSession  # noqa: E402
from pyspark.sql import functions as F  # noqa: E402

from apu_guard import config, db, scoring  # noqa: E402
from apu_guard.features import parse_readings, window_features  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("apu-stream")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--starting-offsets", default="earliest")
    ap.add_argument("--checkpoint-tag", default="v1", help="change it to start a fresh query")
    ap.add_argument("--trigger", default="10 seconds")
    args = ap.parse_args()

    spark = (
        SparkSession.builder.appName("apu-stream")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.shuffle.partitions", "4")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")
    ck = f"{config.CHECKPOINTS}/{args.checkpoint_tag}"

    raw = (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", config.KAFKA_BOOTSTRAP)
        .option("subscribe", config.TOPIC_RAW)
        .option("startingOffsets", args.starting_offsets)
        .option("maxOffsetsPerTrigger", 120_000)  # about 2 weeks of data per micro-batch
        .option("failOnDataLoss", "false")
        .load()
    )
    readings = parse_readings(raw)

    bronze = (
        readings.withColumn("date", F.to_date("ts"))
        .writeStream.format("parquet")
        .option("path", config.BRONZE)
        .option("checkpointLocation", f"{ck}/bronze")
        .partitionBy("date")
        .trigger(processingTime=args.trigger)
        .queryName("bronze")
        .start()
    )

    def sink(batch, batch_id: int) -> None:
        if batch.isEmpty():
            return
        batch.write.mode("append").parquet(config.SILVER)
        pdf = batch.toPandas().sort_values("window_start")
        n = db.upsert_features(pdf)
        params = scoring.load_champion()
        scored = 0
        if params is not None:
            scored = db.upsert_scores(scoring.score_frame(pdf, params))
        log.info("batch %s: %s windows (%s to %s), %s scored by model %s", batch_id, n,
                 pdf["window_start"].min(), pdf["window_start"].max(), scored,
                 params["version"] if params else "none")

    features = (
        window_features(readings)
        .writeStream.outputMode("append")
        .foreachBatch(sink)
        .option("checkpointLocation", f"{ck}/features")
        .trigger(processingTime=args.trigger)
        .queryName("features")
        .start()
    )

    log.info("streaming from '%s' (%s); bronze=%s silver=%s", config.TOPIC_RAW, args.starting_offsets,
             config.BRONZE, config.SILVER)
    spark.streams.awaitAnyTermination()
    bronze.stop()
    features.stop()


if __name__ == "__main__":
    main()
