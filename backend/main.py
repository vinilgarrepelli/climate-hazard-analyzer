"""FastAPI transport: validation, caching, rate limiting and CSV exports."""
import asyncio
import csv
import hashlib
import io
import json
import logging
import os
import time
from collections import defaultdict, deque
from datetime import date, datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from .climate import ALGORITHM_VERSION, analyze
from .models import AnalysisRequest
from .storage import StorageError, get_store
from .weather import GEOCODE_URL, WeatherError, get_json, load_weather

load_dotenv()
logger = logging.getLogger("climate_lens")
app = FastAPI(title="Climate Lens API", version="1.0.0", docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)
app.add_middleware(CORSMiddleware,
    allow_origins=["https://climate-lens-vinil-preview.vinilgoudgarrepelli.chatgpt.site", "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"], allow_headers=["Content-Type"],
)
_limits = defaultdict(deque)
REGIONS = [
    {"name": "Hyderabad, India", "latitude": 17.385, "longitude": 78.4867},
    {"name": "New Delhi, India", "latitude": 28.6139, "longitude": 77.209},
    {"name": "Mumbai, India", "latitude": 19.076, "longitude": 72.8777},
    {"name": "Bengaluru, India", "latitude": 12.9716, "longitude": 77.5946},
    {"name": "Chennai, India", "latitude": 13.0827, "longitude": 80.2707},
    {"name": "Ahmedabad, India", "latitude": 23.0225, "longitude": 72.5714},
    {"name": "London, United Kingdom", "latitude": 51.5074, "longitude": -0.1278},
    {"name": "Phoenix, United States", "latitude": 33.4484, "longitude": -112.074},
    {"name": "Sydney, Australia", "latitude": -33.8688, "longitude": 151.2093},
]


@app.middleware("http")
async def protect_api(request: Request, call_next):
    started = time.perf_counter()
    # Body size is checked by streaming into a bounded buffer before Pydantic.
    if request.method == "POST":
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 4096:
                return JSONResponse({"detail": "Request body must be smaller than 4 KiB."}, status_code=413)
        request._body = bytes(body)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Server-Timing"] = f"total;dur={(time.perf_counter() - started) * 1000:.1f}"
    return response


async def rate_limit(request: Request):
    # Trust Vercel's ingress-generated client address only on that platform.
    address = request.headers.get("x-forwarded-for", "").split(",")[0].strip() if os.getenv("VERCEL") else ""
    address = address or (request.client.host if request.client else "unknown")
    identity = hashlib.sha256(address.encode()).hexdigest()[:32]
    limit = int(os.getenv("RATE_LIMIT_PER_MINUTE", "12"))
    store = get_store()
    if store.mode == "mongodb":
        allowed = await store.allow_request(identity, limit)
    else:
        now = time.monotonic()
        requests = _limits[identity]
        while requests and requests[0] < now - 60:
            requests.popleft()
        allowed = len(requests) < limit
        if allowed:
            requests.append(now)
        if len(_limits) > 1000:
            for key in list(_limits):
                if not _limits[key] or _limits[key][-1] < now - 60:
                    _limits.pop(key, None)
    if not allowed:
        raise HTTPException(429, "Too many requests. Wait a minute before trying again.", headers={"Retry-After": "60"})
    return store


@app.exception_handler(StorageError)
async def storage_error_handler(request, exc):
    return JSONResponse({"detail": str(exc)}, status_code=503)


@app.exception_handler(WeatherError)
async def weather_error_handler(request, exc):
    return JSONResponse({"detail": str(exc)}, status_code=502)


@app.get("/api/health")
async def health():
    try:
        store = get_store()
        await store.get("health-check")
    except StorageError:
        return JSONResponse({"status": "degraded", "database": "unavailable", "version": ALGORITHM_VERSION}, status_code=503)
    return {"status": "ok", "database": store.mode, "version": ALGORITHM_VERSION}


@app.get("/api/regions")
async def regions():
    return {"regions": REGIONS, "min_year": 1940, "max_year": date.today().year - 1}


@app.get("/api/geocode")
async def geocode(request: Request, q: str = Query(min_length=2, max_length=80)):
    store = await rate_limit(request)
    q = q.strip()
    if len(q) < 2:
        raise HTTPException(422, "Enter at least two letters of a city name.")
    key = "geocode:" + hashlib.sha256(q.casefold().encode()).hexdigest()
    cached = await store.get(key)
    if cached is not None:
        return {"results": cached, "cache": "hit"}
    data = await get_json(GEOCODE_URL, {"name": q, "count": 6, "language": "en", "format": "json"})
    results = [{"name": ", ".join(filter(None, [r.get("name"), r.get("admin1"), r.get("country")])),
                "latitude": r["latitude"], "longitude": r["longitude"]} for r in data.get("results", [])]
    await store.put(key, results, 86400 * 7)
    return {"results": results, "cache": "miss"}


async def run_analysis(parameters: AnalysisRequest, store):
    canonical = parameters.model_dump()
    # Include the display label to avoid leaking one caller's custom label to another.
    key = "analysis:" + hashlib.sha256(json.dumps({**canonical, "algorithm": ALGORITHM_VERSION}, sort_keys=True).encode()).hexdigest()
    cached = await store.get(key)
    if cached is not None:
        return {**cached, "cache": {"analysis": "hit", "weather": "not-needed", "storage": store.mode}}
    weather, weather_cache = await load_weather(parameters, store)
    try:
        result = await asyncio.to_thread(analyze, weather["records"], parameters.start_year, parameters.end_year,
                                         parameters.percentile, parameters.min_duration, weather["cleaning"])
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    result.update({
        "request": canonical, "source": weather["source"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    })
    await store.put(key, result, int(os.getenv("CACHE_TTL_DAYS", "30")) * 86400)
    return {**result, "cache": {"analysis": "miss", "weather": weather_cache, "storage": store.mode}}


@app.post("/api/analyze")
async def analysis(parameters: AnalysisRequest, request: Request):
    store = await rate_limit(request)
    result = await run_analysis(parameters, store)
    return JSONResponse(result, headers={"Cache-Control": "no-store", "X-Analysis-Cache": result["cache"]["analysis"]})


@app.post("/api/export/csv")
async def export_csv(parameters: AnalysisRequest, request: Request):
    store = await rate_limit(request)
    result = await run_analysis(parameters, store)
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    fields = ["year", "event_count", "heatwave_days", "mean_duration_days", "longest_event_days", "mean_intensity_c", "peak_temperature_c", "coverage_pct", "reliable", "rolling_days", "trend_days"]
    writer.writerow(fields + ["threshold_c", "percentile", "min_duration_days", "baseline", "model"])
    for row in result["annual"]:
        writer.writerow([row.get(field) for field in fields] + [result["methodology"]["threshold_c"], parameters.percentile, parameters.min_duration, "1991-2020", "ERA5"])
    # No user-provided strings enter cells, preventing spreadsheet formula injection.
    filename = f"heatwave-{parameters.start_year}-{parameters.end_year}.csv"
    return Response(output.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"})


@app.get("/", include_in_schema=False)
async def frontend():
    path = Path(__file__).resolve().parents[1] / "public/index.html"
    if path.exists():
        return FileResponse(path)
    return {"message": "Run npm run build, or npm run dev for the frontend.", "api_docs": "/api/docs"}


# Local-only static mount. Vercel serves public/ from its CDN itself.
assets = Path(__file__).resolve().parents[1] / "public/assets"
if not os.getenv("VERCEL") and assets.exists():
    app.mount("/assets", StaticFiles(directory=assets), name="assets")
