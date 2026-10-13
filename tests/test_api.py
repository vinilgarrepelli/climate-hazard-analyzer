import copy
import json

import pytest
from fastapi.testclient import TestClient

from backend import main
from backend.storage import DocumentStore, StorageError
from backend.weather import WeatherError
from conftest import set_heat

PARAMETERS = {"latitude": 17.385, "longitude": 78.4867, "region_name": "Hyderabad", "start_year": 2021, "end_year": 2025}


class MemoryStore:
    mode = "tinydb-local"

    def __init__(self):
        self.documents = {}

    async def get(self, key):
        return copy.deepcopy(self.documents.get(key))

    async def put(self, key, data, ttl):
        self.documents[key] = copy.deepcopy(data)


@pytest.fixture
def api(monkeypatch, complete_records):
    store = MemoryStore()
    main._limits.clear()
    monkeypatch.setattr(main, "get_store", lambda: store)
    set_heat(complete_records, "2023-05-01", 5)
    calls = []

    async def weather(parameters, store):
        calls.append(parameters)
        return {"records": complete_records, "cleaning": {}, "source": {"provider": "Test fixture", "model": "ERA5"}}, "miss"

    monkeypatch.setattr(main, "load_weather", weather)
    with TestClient(main.app) as client:
        yield client, store, calls


def test_repeat_analysis_reads_database_without_fetch(api):
    client, store, calls = api
    first = client.post("/api/analyze", json=PARAMETERS)
    second = client.post("/api/analyze", json=PARAMETERS)
    assert first.status_code == second.status_code == 200
    assert first.json()["cache"]["analysis"] == "miss"
    assert second.json()["cache"]["analysis"] == "hit"
    assert len(calls) == 1
    assert first.json()["summary"]["total_heatwave_days"] == 5


@pytest.mark.parametrize("extra", [{"latitude": 91}, {"longitude": -181}, {"start_year": 2030},
                                   {"end_year": 2026}, {"start_year": 1939}, {"percentile": 89},
                                   {"min_duration": 2}, {"hazard": "rainfall"}, {"url": "http://internal/"}])
def test_invalid_inputs_are_rejected_before_weather_fetch(api, extra):
    client, store, calls = api
    response = client.post("/api/analyze", json={**PARAMETERS, **extra})
    assert response.status_code == 422
    assert calls == []


def test_csv_export_uses_analysis_cache_and_contains_method(api):
    client, store, calls = api
    response = client.post("/api/export/csv", json={**PARAMETERS, "region_name": "=DANGEROUS()"})
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "1991-2020" in response.text
    assert "=DANGEROUS()" not in response.text
    assert len(response.text.splitlines()) == 6
    assert "attachment" in response.headers["content-disposition"]


def test_local_rate_limit_returns_retry_after(api, monkeypatch):
    client, store, calls = api
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "2")
    assert client.post("/api/analyze", json=PARAMETERS).status_code == 200
    assert client.post("/api/analyze", json=PARAMETERS).status_code == 200
    response = client.post("/api/analyze", json=PARAMETERS)
    assert response.status_code == 429
    assert response.headers["retry-after"] == "60"


def test_large_body_rejected(api):
    client, store, calls = api
    response = client.post("/api/analyze", content=json.dumps({"region_name": "x" * 5000}), headers={"Content-Type": "application/json"})
    assert response.status_code == 413
    assert calls == []


def test_upstream_failure_is_an_error_not_invented_data(api, monkeypatch):
    client, store, calls = api

    async def fail(*args):
        raise WeatherError("Provider unavailable")

    monkeypatch.setattr(main, "load_weather", fail)
    response = client.post("/api/analyze", json=PARAMETERS)
    assert response.status_code == 502
    assert response.json()["detail"] == "Provider unavailable"


def test_serverless_never_silently_uses_temporary_file(monkeypatch):
    monkeypatch.delenv("MONGODB_URI", raising=False)
    monkeypatch.setenv("VERCEL", "1")
    with pytest.raises(StorageError, match="persistent"):
        DocumentStore()
