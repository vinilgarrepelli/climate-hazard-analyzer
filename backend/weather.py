"""Bounded, fixed-host HTTPS access to Open-Meteo's historical ERA5 API."""
import asyncio
import hashlib
import json
import os
from datetime import date, datetime, timedelta, timezone

import httpx

from .climate import BASELINE_START, BASELINE_END, normalize_daily

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
MAX_RESPONSE_BYTES = 4_000_000
_inflight = {}


class WeatherError(RuntimeError):
    pass


async def get_json(url, params):
    """No user-controlled destinations, redirects, unbounded bodies, or retries."""
    last_error = None
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(22.0, connect=5.0), follow_redirects=False) as client:
                async with client.stream("GET", url, params=params) as response:
                    if response.status_code == 429:
                        raise WeatherError("The weather provider is rate-limiting requests. Try a cached region or retry shortly.")
                    response.raise_for_status()
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > MAX_RESPONSE_BYTES:
                            raise WeatherError("The weather response exceeded the safe size limit.")
                    payload = json.loads(body)
                    if not isinstance(payload, dict) or payload.get("error"):
                        raise WeatherError("The weather provider returned an invalid response.")
                    return payload
        except WeatherError:
            raise
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt == 0 and (isinstance(exc, httpx.TransportError) or (isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code >= 500)):
                await asyncio.sleep(0.4)
                continue
            break
    raise WeatherError("Historical weather data could not be fetched. Please retry; no synthetic data is substituted.") from last_error


async def load_weather(request, store):
    # Ninety days of context recover event onsets/durations at year boundaries.
    # Exceptionally long runs that touch the fetched boundary are flagged.
    start = date(min(request.start_year, BASELINE_START), 1, 1) - timedelta(days=90)
    end = date(max(request.end_year, BASELINE_END), 12, 31) + timedelta(days=90)
    end = min(end, date.today() - timedelta(days=10))
    # ERA5 begins in 1940; do not request unavailable boundary context.
    start = max(start, date(1940, 1, 1))
    params = {
        "latitude": request.latitude, "longitude": request.longitude,
        "start_date": start.isoformat(), "end_date": end.isoformat(),
        "daily": "temperature_2m_max", "models": "era5",
        "timezone": "auto", "temperature_unit": "celsius",
    }
    key = "weather:" + hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()
    cached = await store.get(key)
    if cached:
        return cached, "hit"
    # Coalesce identical cold requests within a worker. Mongo handles persistence
    # across workers; a distributed ingestion lock is a documented next step.
    lock = _inflight.setdefault(key, asyncio.Lock())
    try:
        async with lock:
            cached = await store.get(key)
            if cached:
                return cached, "hit"
            payload = await get_json(ARCHIVE_URL, params)
            try:
                records, cleaning = normalize_daily(payload, start, end)
            except ValueError as exc:
                raise WeatherError(str(exc)) from exc
            data = {
                "records": records, "cleaning": cleaning,
                "source": {
                    "provider": "Open-Meteo Historical Weather API", "model": "ERA5",
                    "kind": "Gridded reanalysis, not a local weather-station measurement",
                    "documentation_url": "https://open-meteo.com/en/docs/historical-weather-api",
                    "grid_latitude": payload.get("latitude"), "grid_longitude": payload.get("longitude"),
                    "timezone": payload.get("timezone"), "elevation_m": payload.get("elevation"),
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                    "retrieved_start": start.isoformat(), "retrieved_end": end.isoformat(),
                    "temperature_unit": "°C", "attribution": "Open-Meteo / ECMWF ERA5 (Copernicus Climate Change Service)",
                },
            }
            await store.put(key, data, int(os.getenv("CACHE_TTL_DAYS", "30")) * 86400)
            return data, "miss"
    finally:
        # Retain the lock while waiters might still reference it; bounded cleanup
        # is handled at API level by the limited coordinate/year input space.
        if len(_inflight) > 200:
            for old in list(_inflight):
                if old != key and not _inflight[old].locked():
                    _inflight.pop(old, None)
                    if len(_inflight) <= 100:
                        break
