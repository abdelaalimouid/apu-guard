"""Small Postgres helpers: idempotent upserts, so replaying data never creates duplicates."""
import math

import numpy as np
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

from apu_guard import config

FEATURE_COLUMNS = ["window_start", "window_end", "n_rows", *config.FEATURES, "lps_max", "tp3_flat"]
SCORE_COLUMNS = ["window_start", "score", "threshold", "is_anomaly", "sensor_fault", "model_version"]


def _plain(v):
    """numpy/pandas values -> plain Python values psycopg2 understands."""
    if isinstance(v, pd.Timestamp):
        return v.to_pydatetime()
    if isinstance(v, np.generic):
        v = v.item()
    if isinstance(v, float) and math.isnan(v):
        return None
    return v


def upsert(table: str, df: pd.DataFrame, columns: list[str], touch: str, key: str = "window_start") -> int:
    if df.empty:
        return 0
    rows = [tuple(_plain(v) for v in r) for r in df[columns].itertuples(index=False)]
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in columns if c != key)
    sql = (f"INSERT INTO {table} ({', '.join(columns)}) VALUES %s "
           f"ON CONFLICT ({key}) DO UPDATE SET {updates}, {touch} = now()")
    with psycopg2.connect(config.POSTGRES_DSN) as conn, conn.cursor() as cur:
        execute_values(cur, sql, rows, page_size=1000)
    return len(rows)


def upsert_features(df: pd.DataFrame) -> int:
    return upsert("features", df, FEATURE_COLUMNS, touch="ingested_at")


def upsert_scores(df: pd.DataFrame) -> int:
    return upsert("scores", df, SCORE_COLUMNS, touch="scored_at")


def read_features() -> pd.DataFrame:
    with psycopg2.connect(config.POSTGRES_DSN) as conn, conn.cursor() as cur:
        cur.execute(f"SELECT {', '.join(FEATURE_COLUMNS)} FROM features ORDER BY window_start")
        return pd.DataFrame(cur.fetchall(), columns=FEATURE_COLUMNS)
