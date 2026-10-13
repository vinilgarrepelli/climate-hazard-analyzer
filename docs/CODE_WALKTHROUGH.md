# Code walkthrough — plain-language notes

## Start with one request

1. The person chooses a location, start/end years, percentile, and minimum run length in `frontend/App.tsx`.
2. `runAnalysis` posts those values to `/api/analyze`.
3. `AnalysisRequest` in `backend/models.py` validates the input. Future/incomplete years, invalid coordinates, extra fields, and unsupported hazards are rejected.
4. `rate_limit` checks the request budget. `run_analysis` looks for the exact computed result in the NoSQL cache.
5. On a miss, `load_weather` looks for exact raw weather or a saved interval covering the requested years. It fetches ERA5 from a fixed HTTPS host only when both are missing.
6. `normalize_daily` converts units, checks values, and retains a row for each expected calendar day.
7. `analyze` calculates the fixed-baseline percentile, detects runs, summarizes years, calculates comparisons/regressions, and reports coverage.
8. The API writes the result to the selected document store before returning JSON. New seeded-mode writes last for the worker's lifetime; MongoDB writes are durable and shared.
9. React renders cards, charts, annual rows, and the event log from that response.

## The important files

| File | Purpose | What to explain |
|---|---|---|
| `frontend/App.tsx` | Inputs, requests, result views, exports | State, effects, cancellation, stale selections, conditional rendering |
| `frontend/ChartPanel.tsx` | Interactive Recharts visualizations | Each metric's meaning, chart gaps, lazy loading |
| `frontend/types.ts` | TypeScript response contracts | How client assumptions match server JSON |
| `backend/models.py` | Pydantic request schema | Bounded input and complete-year validation |
| `backend/weather.py` | Public API ingestion | Fixed destinations, timeouts, response bounds, retries, raw caching |
| `backend/climate.py` | Pure scientific indicator calculations | Percentile, consecutive days, cross-year attribution, coverage, comparisons |
| `backend/storage.py` | NoSQL adapter | MongoDB, local TinyDB, explicit seeded TinyDB, expiry, cache limits, atomic MongoDB counters |
| `backend/main.py` | HTTP routes and exports | Cache flow, status codes, rate limiting, security headers |
| `app.py` | Cloud entrypoint | Import the backend as a package so relative imports work when the host loads the entrypoint |
| `tests/` | Correctness checks | Synthetic fixtures test rules; application data is real |
| `scripts/build_frontend.py` | Production build | Build React assets for the CDN, keep Python API on the server |
| `scripts/build_seed.py` | Real historical data ingestion | Package fetched weather and default analyses as versioned TinyDB documents; report provider failures |

## Explain percentile interpolation with a small example

For sorted values `[1, 2, 3, 4]`, the 95th-percentile position is `(4−1)×0.95 = 2.85` using zero-based positions. It lies 85% of the way from 3 to 4, so the threshold is **3.85**. This is interpolation, not simply picking the largest value.

The production threshold uses all valid daily maxima in 1991–2020 for the selected location.

## Explain a heatwave run

At a 39°C threshold, temperatures `[40, 41, 42, 39, 40, 41]` contain one qualifying 3-day event. The day at exactly 39°C breaks the run because the rule is strictly above the threshold. The final 2-day run is too short.

`detect_heatwaves` also checks calendar adjacency. Two hot days, one missing day, and two more hot days are not a 4-day heatwave.

## Understand these terms

- **State:** values React remembers, such as the selected city or loaded result.
- **Effect:** work performed after render, such as loading initial data.
- **API:** the HTTP boundary that accepts validated requests and returns JSON.
- **Async:** waiting for network/database work without blocking unrelated requests.
- **Cache:** saving a reusable result to avoid repeating expensive work.
- **NoSQL document:** a nested JSON-like record, suitable for weather arrays and summaries.
- **Regression slope:** the fitted average direction of change per year; multiplied by 10 for a per-decade number.
- **R²:** how much variation the fitted straight line explains; it is not a significance test.
- **Coverage:** valid days divided by expected days; leap years have 366 expected days.

## Practice before submitting

Run the app yourself. Explain a run from inputs to database to charts without reading these notes. Find the exact code for handling missing days, changing the minimum duration, and computing comparison windows. If you cannot explain a piece, practice with its tests before the interview.
