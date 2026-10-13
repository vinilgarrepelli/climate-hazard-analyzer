"""Ingest REAL ERA5 data and publish a versioned TinyDB NoSQL database.

Run locally before deployment, not on every cloud build. New custom queries
still use the Python ingestion pipeline; only predefined history is bundled.
"""
import asyncio
import gzip
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.main import REGIONS, run_analysis
from backend.models import AnalysisRequest
from backend.storage import DocumentStore
from backend.weather import load_weather


async def main():
    store = DocumentStore()
    if store.mode != "tinydb-local":
        raise RuntimeError("Build the public seed from local TinyDB mode, without cloud credentials.")
    semaphore = asyncio.Semaphore(2)

    async def ingest(region):
        async with semaphore:
            request = AnalysisRequest(latitude=region["latitude"], longitude=region["longitude"],
                                      region_name=region["name"], start_year=1990, end_year=date.today().year - 1)
            # Enrich existing raw documents with their original requested point.
            weather, state = await load_weather(request, store)
            result = await run_analysis(request, store)
            print(f"Verified {region['name']}: {result['summary']['total_events']} events, {result['quality']['coverage_pct']}% coverage ({state})", flush=True)

    outcomes = await asyncio.gather(*(ingest(region) for region in REGIONS), return_exceptions=True)
    for region, outcome in zip(REGIONS, outcomes):
        if isinstance(outcome, Exception):
            print(f"Not preloaded: {region['name']} — {outcome}. The live API will fetch it on demand.", flush=True)
    points = {(round(r["latitude"], 4), round(r["longitude"], 4)) for r in REGIONS}
    names = {r["name"] for r in REGIONS}
    docs = []
    for doc in store._db.all():
        data = doc.get("data", {})
        request = data.get("request", {})
        is_weather = "records" in data and (data.get("request_latitude"), data.get("request_longitude")) in points
        is_analysis = request.get("region_name") in names and request.get("start_year") == 1990 and request.get("end_year") == date.today().year - 1 and request.get("percentile") == 95 and request.get("min_duration") == 3
        if is_weather or is_analysis:
            docs.append(dict(doc))
    output = ROOT / "backend/data/climate_seed.json.gz"
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {"_default": {str(i + 1): doc for i, doc in enumerate(docs)}}
    output.write_bytes(gzip.compress(json.dumps(payload, separators=(",", ":")).encode(), mtime=0))
    print(f"Saved {len(docs)} NoSQL documents, {output.stat().st_size} compressed bytes", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
