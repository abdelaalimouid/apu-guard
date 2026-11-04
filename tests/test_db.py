from datetime import datetime
from unittest.mock import MagicMock

import numpy as np
import pandas as pd

from apu_guard import db


def test_values_are_converted_for_psycopg2():
    assert db._plain(pd.Timestamp("2020-07-01")) == datetime(2020, 7, 1)
    assert type(db._plain(np.float64(1.5))) is float
    assert db._plain(float("nan")) is None


def test_empty_upsert_does_not_touch_the_database(monkeypatch):
    connect = MagicMock()
    monkeypatch.setattr(db.psycopg2, "connect", connect)
    assert db.upsert("scores", pd.DataFrame(), ["window_start"], touch="scored_at") == 0
    connect.assert_not_called()


def test_upsert_updates_existing_windows(monkeypatch):
    execute = MagicMock()
    monkeypatch.setattr(db.psycopg2, "connect", MagicMock())
    monkeypatch.setattr(db, "execute_values", execute)
    frame = pd.DataFrame({"window_start": [pd.Timestamp("2020-07-01")], "score": [np.float64(2.0)]})

    assert db.upsert("scores", frame, ["window_start", "score"], touch="scored_at") == 1

    _, sql, rows = execute.call_args.args
    assert "ON CONFLICT (window_start) DO UPDATE SET score = EXCLUDED.score, scored_at = now()" in sql
    assert rows == [(datetime(2020, 7, 1), 2.0)]
