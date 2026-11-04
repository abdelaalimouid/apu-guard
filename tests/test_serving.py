import pytest
from fastapi.testclient import TestClient

from apu_guard import scoring
from apu_guard.serving.app import app

PARAMS = {
    "features": ["a", "b"],
    "mean": [0.0, 0.0],
    "std": [1.0, 1.0],
    "components": [[1.0], [0.0]],
    "k": 1,
    "threshold": 1.0,
    "version": "3",
}

client = TestClient(app)


@pytest.fixture
def champion(monkeypatch):
    monkeypatch.setattr(scoring, "load_champion", lambda: PARAMS)


@pytest.fixture
def no_champion(monkeypatch):
    monkeypatch.setattr(scoring, "load_champion", lambda: None)


def test_liveness_does_not_need_a_model(no_champion):
    assert client.get("/live").status_code == 200


def test_not_ready_without_a_champion(no_champion):
    assert client.get("/health").status_code == 503
    assert client.post("/score", json={"windows": []}).status_code == 503


def test_ready_reports_the_champion_version(champion):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["model_version"] == "3"


def test_model_endpoint_describes_the_champion(champion):
    assert client.get("/model").json() == {"version": "3", "features": ["a", "b"], "components": 1, "threshold": 1.0}


def test_score_flags_windows_above_the_threshold(champion):
    windows = [{"a": 0.0, "b": 0.0}, {"a": 0.0, "b": 5.0}]
    body = client.post("/score", json={"windows": windows}).json()
    assert body["results"] == [{"score": 0.0, "is_anomaly": False}, {"score": 25.0, "is_anomaly": True}]


def test_score_rejects_missing_features(champion):
    response = client.post("/score", json={"windows": [{"a": 0.0}]})
    assert response.status_code == 422
    assert "b" in response.json()["detail"]
