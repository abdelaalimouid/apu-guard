"""Replay MetroPT-3 into Kafka as if the compressor were sending readings live.

Each message keeps its original 2020 timestamp ("event time"), so everything downstream behaves
exactly as it would with a live train, only faster.

    uv run python -m apu_guard.producer.replay --start 2020-02-01 --end 2020-07-10            # as fast as possible
    uv run python -m apu_guard.producer.replay --start 2020-07-10 --end 2020-07-18 --speed 1000  # 1000x real time
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from confluent_kafka import Producer

from apu_guard import config

ROOT = Path(__file__).resolve().parents[3]
PARQUET = ROOT / "data" / "metropt3.parquet"
CSV = ROOT / "data" / "MetroPT3(AirCompressor).csv"


def load(start: str, end: str) -> pd.DataFrame:
    if PARQUET.exists():
        df = pd.read_parquet(PARQUET, columns=config.SIGNALS)
    else:
        df = pd.read_csv(CSV, parse_dates=["timestamp"], index_col="timestamp", usecols=["timestamp", *config.SIGNALS])
    return df.loc[start:end]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", default="2020-02-01")
    ap.add_argument("--end", default="2020-09-01")
    ap.add_argument("--speed", type=float, default=0, help="0 = as fast as possible, 1000 = 1000x real time")
    ap.add_argument("--bootstrap", default=config.KAFKA_BOOTSTRAP)
    ap.add_argument("--topic", default=config.TOPIC_RAW)
    args = ap.parse_args()

    df = load(args.start, args.end)
    if df.empty:
        raise SystemExit("no rows in that period")
    print(f"replaying {len(df):,} readings from {df.index[0]} to {df.index[-1]} "
          f"at {'max speed' if args.speed <= 0 else f'{args.speed:g}x'} into '{args.topic}'")

    producer = Producer({
        "bootstrap.servers": args.bootstrap,
        "enable.idempotence": True,      # no duplicates if the producer retries
        "acks": "all",
        "linger.ms": 20,                 # small batches = high throughput
        "compression.type": "lz4",
        "queue.buffering.max.messages": 500_000,
    })

    # seconds since the first reading, used to pace the replay
    offsets = (df.index - df.index[0]).total_seconds().to_numpy()
    timestamps = df.index.strftime("%Y-%m-%dT%H:%M:%S").to_numpy()
    values = df.to_numpy(dtype=np.float64)
    wall0 = time.monotonic()

    for i in range(len(df)):
        if args.speed > 0:
            ahead = offsets[i] / args.speed - (time.monotonic() - wall0)
            if ahead > 0:
                time.sleep(ahead)
        msg = {"ts": timestamps[i], **dict(zip(config.SIGNALS, values[i].tolist()))}
        while True:
            try:
                producer.produce(args.topic, key=config.UNIT_ID, value=json.dumps(msg))
                break
            except BufferError:  # local queue full: let it drain
                producer.poll(0.1)
        if i % 20_000 == 0:
            producer.poll(0)
            rate = (i + 1) / max(time.monotonic() - wall0, 1e-9)
            print(f"  {i + 1:>9,} sent  |  event time {timestamps[i]}  |  {rate:,.0f} msg/s", flush=True)

    producer.flush()
    print(f"done: {len(df):,} readings in {time.monotonic() - wall0:.1f} s")


if __name__ == "__main__":
    main()
