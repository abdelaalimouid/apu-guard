import pandas as pd

from apu_guard import config
from apu_guard.producer import replay


def test_load_returns_the_requested_period_with_all_signals(tmp_path, monkeypatch):
    index = pd.to_datetime(["2020-02-01 00:00", "2020-02-02 00:00", "2020-02-03 00:00"])
    frame = pd.DataFrame(1.0, index=index, columns=[*config.SIGNALS, "unused"])
    path = tmp_path / "readings.parquet"
    frame.to_parquet(path)
    monkeypatch.setattr(replay, "PARQUET", path)

    loaded = replay.load("2020-02-02", "2020-02-02")

    assert loaded.index.tolist() == [pd.Timestamp("2020-02-02 00:00")]
    assert loaded.columns.tolist() == config.SIGNALS
