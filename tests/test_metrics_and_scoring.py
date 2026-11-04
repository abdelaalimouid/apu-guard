import numpy as np
import pandas as pd

from apu_guard import scoring
from apu_guard.training import metrics


def _windows(start, end):
    idx = pd.date_range(start, end, freq="10min", inclusive="left")
    return pd.DataFrame({"n_rows": 60, "load_share": 0.1}, index=idx)


def test_alarm_in_warning_zone_counts_as_warned_with_lead_time():
    w = _windows("2020-07-01", "2020-07-20")
    alarm = pd.Series(False, index=w.index)
    alarm.loc["2020-07-15 08:00":"2020-07-15 09:00"] = True          # ~10 h before failure 4
    m = metrics.event_metrics(w, alarm, failures={4: pd.Timestamp("2020-07-15 18:25")})
    assert m["warned"] == 1
    assert 9 < m["lead_hours"][4] < 11
    assert m["false_episodes"] == 0


def test_alarm_far_from_any_failure_is_false():
    w = _windows("2020-07-01", "2020-07-30")
    alarm = pd.Series(False, index=w.index)
    alarm.loc["2020-07-28 08:00":"2020-07-28 09:00"] = True
    m = metrics.event_metrics(w, alarm, failures={4: pd.Timestamp("2020-07-15 18:25")})
    assert m["warned"] == 0 and m["false_episodes"] == 1
    assert m["false_per_1000h"] > 0


def test_close_alarms_merge_into_one_episode():
    idx = pd.date_range("2020-07-01", periods=20, freq="10min")
    a = pd.Series(False, index=idx)
    a.iloc[[0, 1, 5]] = True                                          # 40 min apart -> one episode
    assert len(metrics.episodes(a)) == 1


def test_sustained_needs_k_in_a_row():
    f = pd.Series([True, True, False, True, True, True])
    assert metrics.sustained(f, 3).tolist() == [False, False, False, False, False, True]


def test_pca_score_is_zero_inside_the_learned_subspace():
    params = {"mean": [0, 0], "std": [1, 1], "components": [[1.0], [0.0]]}
    X = np.array([[3.0, 0.0], [0.0, 2.0]])
    s = scoring.score_matrix(X, params)
    assert s[0] == 0.0 and s[1] == 4.0


def test_zero_std_feature_is_ignored_like_spark():
    params = {"mean": [0, 5], "std": [1, 0], "components": [[1.0], [0.0]]}
    s = scoring.score_matrix(np.array([[1.0, 99.0]]), params)
    assert s[0] == 0.0
