import sys
import time

import numpy as np
import pandas as pd

from apu_guard import scoring

PARAMS = {
    "features": ["a", "b"],
    "mean": [0.0, 0.0],
    "std": [1.0, 1.0],
    "components": [[1.0], [0.0]],
    "threshold": 1.0,
    "min_rows": 30,
    "version": 7,
}


def _frame():
    return pd.DataFrame(
        {
            "window_start": pd.date_range("2020-07-01", periods=4, freq="10min"),
            "n_rows": [60, 10, 60, 60],
            "a": [0.0, 0.0, 0.0, 0.0],
            "b": [0.0, 9.0, 5.0, 5.0],
            "tp3_flat": [False, False, True, None],
        }
    )


def test_pca_score_is_zero_inside_the_learned_subspace():
    params = {"mean": [0, 0], "std": [1, 1], "components": [[1.0], [0.0]]}
    scores = scoring.score_matrix(np.array([[3.0, 0.0], [0.0, 2.0]]), params)
    assert scores.tolist() == [0.0, 4.0]


def test_zero_std_feature_is_ignored_like_spark():
    params = {"mean": [0, 5], "std": [1, 0], "components": [[1.0], [0.0]]}
    assert scoring.score_matrix(np.array([[1.0, 99.0]]), params)[0] == 0.0


def test_score_frame_skips_half_empty_windows():
    scored = scoring.score_frame(_frame(), PARAMS)
    assert len(scored) == 3
    assert set(scored["model_version"]) == {"7"}


def test_frozen_sensor_is_a_fault_not_an_anomaly():
    scored = scoring.score_frame(_frame(), PARAMS)
    assert scored["sensor_fault"].tolist() == [False, True, False]
    assert scored["is_anomaly"].tolist() == [False, False, True]


def test_score_frame_accepts_an_empty_batch():
    assert scoring.score_frame(_frame().iloc[0:0], PARAMS).empty


def test_champion_comes_from_the_cache_while_it_is_fresh(monkeypatch):
    monkeypatch.setitem(scoring._cache, "loaded_at", time.time())
    monkeypatch.setitem(scoring._cache, "params", PARAMS)
    assert scoring.load_champion() is PARAMS


def test_champion_is_none_when_the_registry_is_unavailable(monkeypatch):
    monkeypatch.setitem(sys.modules, "mlflow", None)  # importing mlflow now fails
    monkeypatch.setitem(scoring._cache, "loaded_at", 0.0)
    monkeypatch.setitem(scoring._cache, "params", PARAMS)
    assert scoring.load_champion() is None
