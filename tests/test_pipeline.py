import pandas as pd

from apu_guard.training import pipeline


def test_training_keeps_only_complete_healthy_calibration_windows():
    rows = pd.DataFrame(
        [
            ("2020-02-02 00:00", 60, False),  # kept
            ("2020-02-02 00:10", 10, False),  # half-empty window
            ("2020-02-02 00:20", 60, True),  # frozen pressure sensor
            ("2020-03-12 12:00", 60, False),  # around a maintenance log entry
            ("2020-04-02 00:00", 60, False),  # after the calibration period
        ],
        columns=["window_start", "n_rows", "tp3_flat"],
    )
    rows["window_start"] = pd.to_datetime(rows["window_start"])

    kept = pipeline.training_rows(rows)

    assert kept["window_start"].tolist() == [pd.Timestamp("2020-02-02 00:00")]
