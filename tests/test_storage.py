import asyncio
import gzip
import json
import time

from backend.storage import DocumentStore


def make_seed(monkeypatch, tmp_path):
    path = tmp_path / "seed.json.gz"
    weather = {"request_latitude": 17.385, "request_longitude": 78.4867, "records": [],
               "source": {"model": "ERA5", "retrieved_start": "1989-10-03", "retrieved_end": "2026-03-31"}}
    path.write_bytes(gzip.compress(json.dumps({"_default": {"1": {
        "key": "weather:seed", "data": weather, "expires_epoch": time.time() + 3600}}}).encode()))
    monkeypatch.delenv("MONGODB_URI", raising=False)
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("STORAGE_BACKEND", "tinydb-seeded")
    monkeypatch.setenv("SEED_DB_PATH", str(path))
    return path


def test_seeded_database_survives_a_new_worker(monkeypatch, tmp_path):
    make_seed(monkeypatch, tmp_path)
    first, second = DocumentStore(), DocumentStore()
    assert first.mode == second.mode == "tinydb-seeded"
    assert asyncio.run(first.get("weather:seed")) == asyncio.run(second.get("weather:seed"))


def test_narrower_period_reuses_saved_weather(monkeypatch, tmp_path):
    make_seed(monkeypatch, tmp_path)
    store = DocumentStore()
    assert asyncio.run(store.find_weather(17.385, 78.4867, "1990-10-03", "2020-03-31")) is not None
    assert asyncio.run(store.find_weather(28.6139, 77.209, "1990-10-03", "2020-03-31")) is None
    assert asyncio.run(store.find_weather(17.385, 78.4867, "1940-01-01", "2020-03-31")) is None


def test_runtime_cache_is_bounded_without_deleting_seed(monkeypatch, tmp_path):
    make_seed(monkeypatch, tmp_path)
    store = DocumentStore()

    async def fill():
        for index in range(40):
            await store.put(f"analysis:{index}", {"value": index}, 60)
        assert await store.get("analysis:0") is None
        assert await store.get("analysis:39") == {"value": 39}
        assert await store.get("weather:seed") is not None

    asyncio.run(fill())
