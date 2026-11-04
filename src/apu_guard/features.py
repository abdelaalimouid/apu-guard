"""Feature logic, written once and used by both the streaming job and batch code.

Using the same functions live and in training avoids training/serving skew: the model sees
exactly the features it was trained on. Everything here is Spark SQL (no Python UDFs), so it
runs on the executors without shipping Python code to them.
"""
from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.types import DoubleType, StringType, StructField, StructType

from apu_guard import config

READING_SCHEMA = StructType(
    [StructField("ts", StringType())] + [StructField(s, DoubleType()) for s in config.SIGNALS]
)


def parse_readings(kafka_df: DataFrame) -> DataFrame:
    """Kafka value (JSON bytes) -> one typed row per reading. Malformed messages are dropped."""
    return (
        kafka_df.select(F.from_json(F.col("value").cast("string"), READING_SCHEMA).alias("r"))
        .select("r.*")
        .withColumn("ts", F.to_timestamp("ts"))
        .where(F.col("ts").isNotNull() & F.col("TP3").isNotNull())
    )


def window_features(readings: DataFrame, window: str = config.WINDOW, watermark: str = "2 minutes") -> DataFrame:
    """Readings -> one row per 10-minute window, by event time.

    The watermark tells Spark how long to wait for late readings before closing a window.
    In batch mode Spark ignores it, so the same function works for both.
    """
    loaded = (F.col("DV_eletric") > 0.5) & (F.col("Motor_current") >= 1.0)
    return (
        readings.withWatermark("ts", watermark)
        .groupBy(F.window("ts", window).alias("w"))
        .agg(
            F.count("*").alias("n_rows"),
            F.avg(F.when(loaded, 1.0).otherwise(0.0)).alias("load_share"),
            F.avg("TP3").alias("tp3_mean"),
            F.min("TP3").alias("tp3_min"),
            F.max("TP3").alias("tp3_max"),
            F.max("TP2").alias("tp2_max"),
            F.avg("Motor_current").alias("motor_current_mean"),
            F.avg("Oil_temperature").alias("oil_temp_mean"),
            F.avg("H1").alias("h1_mean"),
            F.avg("DV_pressure").alias("dv_pressure_mean"),
            F.max("LPS").alias("lps_max"),
        )
        .withColumn("tp3_range", F.col("tp3_max") - F.col("tp3_min"))
        # a pressure that does not move at all while the motor runs is a stuck sensor, not a healthy machine
        .withColumn("tp3_flat", (F.col("tp3_range") == 0) & (F.col("motor_current_mean") > 1.0))
        .select(
            F.col("w.start").alias("window_start"),
            F.col("w.end").alias("window_end"),
            "n_rows", *config.FEATURES, "lps_max", "tp3_flat",
        )
    )
