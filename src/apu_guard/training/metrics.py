"""Event-level evaluation: what an operator would see, not per-row accuracy.

Protocol from Troshin et al. (2026):
  - warning zone of a failure = 7 days to 2 h before its report time: an alarm episode that
    starts there is a useful warning;
  - late zone = 2 h before to 24 h after the report;
  - alarms less than 1 h apart merge into one episode;
  - false episodes start outside every warning, late and exclusion zone, and are counted
    per 1000 hours of recorded data outside those zones.
"""
import pandas as pd

from apu_guard import config

WINDOW = pd.Timedelta(minutes=config.WINDOW_MINUTES)
WARN = pd.Timedelta(days=7)
LATE_START = pd.Timedelta(hours=2)
LATE_END = pd.Timedelta(hours=24)
MERGE = pd.Timedelta(hours=1)


def sustained(flags: pd.Series, k: int) -> pd.Series:
    """True where the last k windows (in row order) were all flagged."""
    return flags.astype(int).rolling(k, min_periods=k).sum().eq(k)


def episodes(alarm: pd.Series) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """Alarm flags indexed by window start -> merged (start, end) episodes."""
    times = alarm.index[alarm.to_numpy(dtype=bool)]
    if len(times) == 0:
        return []
    out, start, prev = [], times[0], times[0]
    for t in times[1:]:
        if t - (prev + WINDOW) <= MERGE:
            prev = t
        else:
            out.append((start, prev + WINDOW))
            start = prev = t
    out.append((start, prev + WINDOW))
    return out


def _zones(failures=config.FAILURE_REPORTS, other=config.OTHER_LOG_DATES):
    zones = [(tf - WARN, tf + LATE_END) for tf in failures.values()]
    zones += [(d - pd.Timedelta(hours=24), d + pd.Timedelta(hours=48)) for d in other]
    return zones


def in_any_zone(times: pd.Index) -> pd.Series:
    mask = pd.Series(False, index=times)
    for a, b in _zones():
        mask |= (times >= a) & (times < b)
    return mask


def event_metrics(windows: pd.DataFrame, alarm: pd.Series, failures=config.FAILURE_REPORTS) -> dict:
    """windows: index = window_start, column n_rows. alarm: bool flags on the same index."""
    eps = episodes(alarm)
    first, last = windows.index.min(), windows.index.max()
    in_scope = {f: tf for f, tf in failures.items() if first <= tf - LATE_START and tf <= last + LATE_END}
    leads: dict[int, float] = {}
    false_eps = 0
    for s, _ in eps:
        counted = False
        for f, tf in in_scope.items():
            if tf - WARN <= s < tf - LATE_START:
                leads[f] = max(leads.get(f, 0.0), (tf - s) / pd.Timedelta(hours=1))
                counted = True
            elif tf - LATE_START <= s <= tf + LATE_END:
                counted = True
        if not counted and not bool(in_any_zone(pd.Index([s])).iloc[0]):
            false_eps += 1
    outside = ~in_any_zone(windows.index)
    hours = float((windows.loc[outside.to_numpy(), "n_rows"] * config.SAMPLE_SECONDS / 3600).sum())
    return {
        "failures_in_scope": len(in_scope),
        "warned": len(leads),
        "lead_hours": {int(k): round(v, 1) for k, v in sorted(leads.items())},
        "episodes": len(eps),
        "false_episodes": false_eps,
        "record_hours_outside_zones": round(hours, 1),
        "false_per_1000h": round(1000 * false_eps / hours, 2) if hours else float("nan"),
    }


def duty_rule(windows: pd.DataFrame) -> pd.Series:
    """Baseline: alarm when the compressor was loaded more than half of the last hour (6 windows)."""
    return windows["load_share"].rolling(6, min_periods=3).mean().gt(0.5)
