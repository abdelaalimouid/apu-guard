#!/usr/bin/env python3
"""Print the champion model's evaluation next to the duty-rule baseline (reads MLflow on localhost:5050)."""

import json
import os
import urllib.parse
import urllib.request

BASE = os.environ.get("MLFLOW_URL", "http://localhost:5050")


def get(path, **params):
    with urllib.request.urlopen(f"{BASE}/api/2.0/mlflow/{path}?{urllib.parse.urlencode(params)}", timeout=15) as r:
        return json.load(r)


mv = get("registered-models/alias", name="apu-anomaly", alias="champion")["model_version"]
run = get("runs/get", run_id=mv["run_id"])["run"]
m = {x["key"]: x["value"] for x in run["data"]["metrics"]}
p = {x["key"]: x["value"] for x in run["data"]["params"]}
print(f"champion: apu-anomaly v{mv['version']}  |  run {mv['run_id'][:8]}")
print(
    f"training: {p['train_windows']} windows, {p['k']} components "
    f"({m['explained_variance']:.1%} of variance), threshold {m['threshold']:.2f}\n"
)
print(f"{'evaluation after training period':<36}{'model':>10}{'duty rule':>12}")
print(f"{'failures warned (7-day zone)':<36}{m['model_warned']:>10.0f}{m['duty_rule_warned']:>12.0f}")
print(f"{'false alarm episodes':<36}{m['model_false_episodes']:>10.0f}{m['duty_rule_false_episodes']:>12.0f}")
print(f"{'false alarms per 1000 h':<36}{m['model_false_per_1000h']:>10.2f}{m['duty_rule_false_per_1000h']:>12.2f}")
