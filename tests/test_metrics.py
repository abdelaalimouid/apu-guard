import pandas as pd

from apu_guard.training import metrics

FAILURE_4 = {4: pd.Timestamp("2020-07-15 18:25")}


def _windows(start, end):
    idx = pd.date_range(start, end, freq="10min", inclusive="left")
    return pd.DataFrame({"n_rows": 60, "load_share": 0.1}, index=idx)


def _alarm_between(windows, start, end):
    alarm = pd.Series(False, index=windows.index)
    alarm.loc[start:end] = True
    return alarm


def test_alarm_in_warning_zone_counts_as_warned_with_lead_time():
    w = _windows("2020-07-01", "2020-07-20")
    alarm = _alarm_between(w, "2020-07-15 08:00", "2020-07-15 09:00")  # about 10 h before the report
    m = metrics.event_metrics(w, alarm, failures=FAILURE_4)
    assert m["warned"] == 1
    assert 9 < m["lead_hours"][4] < 11
    assert m["false_episodes"] == 0


def test_alarm_less_than_two_hours_before_report_is_late_not_false():
    w = _windows("2020-07-01", "2020-07-20")
    alarm = _alarm_between(w, "2020-07-15 17:30", "2020-07-15 18:00")
    m = metrics.event_metrics(w, alarm, failures=FAILURE_4)
    assert m["warned"] == 0
    assert m["false_episodes"] == 0


def test_alarm_far_from_any_failure_is_false():
    w = _windows("2020-07-01", "2020-07-30")
    alarm = _alarm_between(w, "2020-07-28 08:00", "2020-07-28 09:00")
    m = metrics.event_metrics(w, alarm, failures=FAILURE_4)
    assert m["warned"] == 0
    assert m["false_episodes"] == 1
    assert m["false_per_1000h"] > 0


def test_alarm_near_a_non_failure_log_entry_is_not_false():
    w = _windows("2020-04-10", "2020-05-01")
    alarm = _alarm_between(w, "2020-04-21 12:00", "2020-04-21 13:00")
    assert metrics.event_metrics(w, alarm, failures={})["false_episodes"] == 0


def test_failure_outside_the_evaluated_period_is_not_in_scope():
    w = _windows("2020-07-20", "2020-07-30")
    alarm = pd.Series(False, index=w.index)
    assert metrics.event_metrics(w, alarm, failures=FAILURE_4)["failures_in_scope"] == 0


def test_close_alarms_merge_into_one_episode():
    idx = pd.date_range("2020-07-01", periods=20, freq="10min")
    alarm = pd.Series(False, index=idx)
    alarm.iloc[[0, 1, 5]] = True  # 30 minutes between the two groups
    assert len(metrics.episodes(alarm)) == 1


def test_distant_alarms_stay_separate_episodes():
    idx = pd.date_range("2020-07-01", periods=40, freq="10min")
    alarm = pd.Series(False, index=idx)
    alarm.iloc[[0, 30]] = True
    assert metrics.episodes(alarm) == [
        (idx[0], idx[1]),
        (idx[30], idx[31]),
    ]


def test_no_alarm_means_no_episode():
    idx = pd.date_range("2020-07-01", periods=3, freq="10min")
    assert metrics.episodes(pd.Series(False, index=idx)) == []


def test_sustained_needs_k_in_a_row():
    flags = pd.Series([True, True, False, True, True, True])
    assert metrics.sustained(flags, 3).tolist() == [False, False, False, False, False, True]


def test_duty_rule_needs_three_windows_above_half_load():
    windows = pd.DataFrame({"load_share": [0.9, 0.9, 0.9, 0.0, 0.0, 0.0, 0.0, 0.0]})
    assert metrics.duty_rule(windows).tolist() == [False, False, True, True, True, False, False, False]
