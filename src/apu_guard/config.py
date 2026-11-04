"""Settings shared by every part of the pipeline. Hosts come from environment variables,
so the same code runs on the Mac (localhost ports) and inside containers (service names)."""
import os

import pandas as pd

# --- Kafka ---
KAFKA_BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP", "localhost:9092")
TOPIC_RAW = "apu.sensors.raw"
UNIT_ID = "APU01"  # the dataset covers one compressor unit

# --- HDFS layout (bronze = raw readings, silver = feature windows) ---
HDFS = os.environ.get("APU_HDFS", "hdfs://namenode:8020")
BRONZE = f"{HDFS}/apu/bronze/readings"
SILVER = f"{HDFS}/apu/silver/features_10min"
CHECKPOINTS = f"{HDFS}/apu/checkpoints"

# --- Postgres and MLflow ---
POSTGRES_DSN = os.environ.get("APU_POSTGRES_DSN", "postgresql://apu:apu@localhost:5433/apu")
MODEL_NAME = os.environ.get("APU_MODEL_NAME", "apu-anomaly")
EXPERIMENT = "apu-anomaly"

# --- the 15 signals of MetroPT-3 (column names exactly as in the CSV, including the DV_eletric typo) ---
ANALOG = ["TP2", "TP3", "H1", "DV_pressure", "Reservoirs", "Oil_temperature", "Motor_current"]
DIGITAL = ["COMP", "DV_eletric", "Towers", "MPG", "LPS", "Pressure_switch", "Oil_level", "Caudal_impulses"]
SIGNALS = ANALOG + DIGITAL

# --- feature windows ---
WINDOW = "10 minutes"
WINDOW_MINUTES = 10
SAMPLE_SECONDS = 10
FULL_WINDOW_ROWS = WINDOW_MINUTES * 60 // SAMPLE_SECONDS  # 60
MIN_ROWS = FULL_WINDOW_ROWS // 2  # a window counts only if at least half of it was recorded

# Model inputs (all computed in apu_guard.features)
FEATURES = [
    "load_share", "tp3_mean", "tp3_min", "tp3_max", "tp3_range", "tp2_max",
    "motor_current_mean", "oil_temp_mean", "h1_mean", "dv_pressure_mean",
]

# --- training period: the two calibration months used by Troshin et al. (2026) ---
TRAIN_START = pd.Timestamp("2020-02-01")
TRAIN_END = pd.Timestamp("2020-04-01")
PCA_VARIANCE = 0.90      # keep the fewest components that explain 90% of the variance
THRESHOLD_QUANTILE = 0.995  # alarm threshold = 99.5th percentile of training scores
SUSTAIN_WINDOWS = 3      # an alarm needs 3 anomalous windows in a row (30 min)

# --- failure reports (maintenance log, Troshin et al. 2026, Table 2) ---
FAILURE_REPORTS = {
    1: pd.Timestamp("2020-04-18 07:05"),
    2: pd.Timestamp("2020-05-30 01:10"),
    3: pd.Timestamp("2020-06-05 18:00"),
    4: pd.Timestamp("2020-07-15 18:25"),
    5: pd.Timestamp("2020-07-17 05:46"),
}
# Log entries that were not compressor failures (dates only): excluded from false-alarm counting
OTHER_LOG_DATES = [pd.Timestamp(d) for d in ("2020-03-12", "2020-03-27", "2020-04-20")]
