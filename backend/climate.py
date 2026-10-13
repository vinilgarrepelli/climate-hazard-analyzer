"""Pure, deterministic climate calculations; no HTTP or database dependencies.

This is a transparent case-study indicator, not an official heat-health warning.
A fixed, all-season baseline is intentional: changing it for each query would
change the yardstick and make different time ranges difficult to compare.
"""
import calendar
import math
from collections import defaultdict
from datetime import date, timedelta
from statistics import mean

BASELINE_START = 1991
BASELINE_END = 2020
MIN_COVERAGE = 0.95
ALGORITHM_VERSION = "heatwave-v1.0"


def percentile_linear(values: list[float], percentile: float) -> float:
    """Linear interpolation (Hyndman-Fan type 7, like NumPy's default)."""
    values = sorted(values)
    if not values:
        raise ValueError("Cannot calculate a percentile without valid baseline data.")
    position = (len(values) - 1) * percentile / 100
    lo, hi = math.floor(position), math.ceil(position)
    return values[lo] + (values[hi] - values[lo]) * (position - lo)


def normalize_daily(payload: dict, start: date, end: date) -> tuple[list[dict], dict]:
    """Keep every calendar date. Missing/invalid values break consecutive runs."""
    daily = payload.get("daily", {})
    times, temperatures = daily.get("time"), daily.get("temperature_2m_max")
    if not isinstance(times, list) or not isinstance(temperatures, list) or len(times) != len(temperatures):
        raise ValueError("The weather provider returned inconsistent daily arrays.")
    unit = payload.get("daily_units", {}).get("temperature_2m_max")
    if unit not in ("°C", "°F", "C", "F"):
        raise ValueError("The weather provider returned an unsupported temperature unit.")
    by_date, duplicates = {}, set()
    invalid_values = malformed_dates = 0
    for stamp, temperature in zip(times, temperatures):
        try:
            day = date.fromisoformat(stamp)
        except (ValueError, TypeError):
            malformed_dates += 1
            continue
        if not start <= day <= end:
            continue
        value = None
        if isinstance(temperature, (float, int)) and not isinstance(temperature, bool) and math.isfinite(temperature):
            value = (temperature - 32) * 5 / 9 if unit in ("°F", "F") else float(temperature)
            if not -90 <= value <= 65:
                value = None
                invalid_values += 1
        elif temperature is not None:
            invalid_values += 1
        if day in by_date:
            # Duplicates are ambiguous, even if identical: exclude conservatively.
            duplicates.add(day)
            by_date[day] = None
        else:
            by_date[day] = value
    records = []
    day = start
    while day <= end:
        records.append({"date": day.isoformat(), "tmax_c": by_date.get(day)})
        day += timedelta(days=1)
    return records, {
        "invalid_values": invalid_values,
        "duplicate_dates": len(duplicates),
        "malformed_dates": malformed_dates,
        "unit_converted": unit in ("°F", "F"),
    }


def detect_heatwaves(records: list[dict], threshold: float, min_duration: int = 3) -> list[dict]:
    """A run must contain consecutive dates AND strictly exceed the threshold."""
    events, run = [], []
    ordered = sorted(records, key=lambda r: r["date"])
    first_day = ordered[0]["date"] if ordered else None
    last_day = ordered[-1]["date"] if ordered else None

    def finish():
        if len(run) >= min_duration:
            temperatures = [r["tmax_c"] for r in run]
            events.append({
                "start_date": run[0]["date"], "end_date": run[-1]["date"],
                "duration_days": len(run),
                "peak_temperature_c": round(max(temperatures), 2),
                "mean_temperature_c": round(mean(temperatures), 2),
                "mean_exceedance_c": round(mean(temperatures) - threshold, 2),
                "peak_exceedance_c": round(max(temperatures) - threshold, 2),
                "boundary_truncated": run[0]["date"] == first_day or run[-1]["date"] == last_day,
            })
        run.clear()

    previous = None
    for record in ordered:
        current = date.fromisoformat(record["date"])
        if previous is not None and current - previous != timedelta(days=1):
            finish()
        value = record["tmax_c"]
        if value is not None and math.isfinite(value) and value > threshold:
            run.append(record)
        else:
            finish()
        previous = current
    finish()
    return events


def regression(rows: list[dict], metric: str) -> dict:
    eligible = [r for r in rows if r["reliable"] and r[metric] is not None]
    if len(eligible) < 5:
        return {"available": False, "reason": "At least five years with 95% coverage are needed.", "metric": metric}
    xs, ys = [r["year"] for r in eligible], [r[metric] for r in eligible]
    xbar, ybar = mean(xs), mean(ys)
    sxx = sum((x - xbar) ** 2 for x in xs)
    slope = sum((x - xbar) * (y - ybar) for x, y in zip(xs, ys)) / sxx
    intercept = ybar - slope * xbar
    sst = sum((y - ybar) ** 2 for y in ys)
    sse = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys))
    return {
        "available": True, "metric": metric, "years_used": len(xs),
        "slope_per_year": round(slope, 6), "slope_per_decade": round(slope * 10, 3),
        "intercept": intercept, "r_squared": round(max(0, 1 - sse / sst), 4) if sst else 0.0,
        "interpretation": "Descriptive ordinary least squares; no statistical significance or causal attribution is claimed.",
    }


def period_comparison(annual: list[dict]) -> dict:
    # Use non-overlapping equal windows and their actual calendar dates.
    window = min(5, len(annual) // 2)
    if window < 3:
        return {"available": False, "reason": "Select at least six years to compare non-overlapping periods."}
    first, last = annual[:window], annual[-window:]
    if not all(r["reliable"] for r in first + last):
        return {"available": False, "reason": "Both comparison windows need at least 95% daily coverage in every year."}
    early, late = mean(r["heatwave_days"] for r in first), mean(r["heatwave_days"] for r in last)
    return {
        "available": True, "metric": "annual_heatwave_days",
        "early_period": f"{first[0]['year']}–{first[-1]['year']}",
        "late_period": f"{last[0]['year']}–{last[-1]['year']}",
        "early_mean": round(early, 2), "late_mean": round(late, 2),
        "absolute_change": round(late - early, 2),
        "percent_change": round((late - early) / early * 100, 1) if early > 0 else None,
        "window_years": window,
    }


def analyze(records: list[dict], start_year: int, end_year: int, percentile: float = 95,
            min_duration: int = 3, cleaning: dict | None = None) -> dict:
    baseline = [r["tmax_c"] for r in records if BASELINE_START <= int(r["date"][:4]) <= BASELINE_END and r["tmax_c"] is not None]
    expected_baseline = sum(366 if calendar.isleap(y) else 365 for y in range(BASELINE_START, BASELINE_END + 1))
    baseline_coverage = len(baseline) / expected_baseline
    if baseline_coverage < MIN_COVERAGE:
        raise ValueError("The fixed 1991–2020 baseline has less than 95% coverage; the threshold would be unreliable.")
    threshold = percentile_linear(baseline, percentile)
    all_events = detect_heatwaves(records, threshold, min_duration)
    start, end = date(start_year, 1, 1), date(end_year, 12, 31)
    events = [e for e in all_events if date.fromisoformat(e["end_date"]) >= start and date.fromisoformat(e["start_date"]) <= end]
    by_year = defaultdict(list)
    for record in records:
        year = int(record["date"][:4])
        if start_year <= year <= end_year:
            by_year[year].append(record)
    event_days, onset_events = defaultdict(list), defaultdict(list)
    for event in events:
        onset_events[int(event["start_date"][:4])].append(event)
        day = max(start, date.fromisoformat(event["start_date"]))
        until = min(end, date.fromisoformat(event["end_date"]))
        while day <= until:
            event_days[day.year].append(day.isoformat())
            day += timedelta(days=1)
    annual = []
    temperatures_by_day = {r["date"]: r["tmax_c"] for r in records}
    for year in range(start_year, end_year + 1):
        valid = [r["tmax_c"] for r in by_year[year] if r["tmax_c"] is not None]
        expected = 366 if calendar.isleap(year) else 365
        coverage = len(valid) / expected
        hot_values = [temperatures_by_day[day] for day in event_days[year]]
        durations = [e["duration_days"] for e in onset_events[year]]
        annual.append({
            "year": year, "valid_days": len(valid), "expected_days": expected,
            "coverage_pct": round(coverage * 100, 2), "reliable": coverage >= MIN_COVERAGE,
            "event_count": len(onset_events[year]), "heatwave_days": len(hot_values),
            "mean_duration_days": round(mean(durations), 2) if durations else 0,
            "longest_event_days": max(durations, default=0),
            "mean_intensity_c": round(mean(hot_values) - threshold, 2) if hot_values else None,
            "peak_temperature_c": round(max(valid), 2) if valid else None,
            "mean_tmax_c": round(mean(valid), 2) if valid else None,
        })
    for i, row in enumerate(annual):
        rolling = annual[max(0, i - 2):i + 1]
        row["rolling_days"] = round(mean(r["heatwave_days"] for r in rolling), 2) if len(rolling) == 3 and all(r["reliable"] for r in rolling) else None
    trends = {metric: regression(annual, metric) for metric in ("heatwave_days", "event_count", "mean_tmax_c")}
    for row in annual:
        trend = trends["heatwave_days"]
        row["trend_days"] = round(trend["slope_per_year"] * row["year"] + trend["intercept"], 2) if trend["available"] else None
    comparison = period_comparison(annual)
    selected = [r for r in records if start.isoformat() <= r["date"] <= end.isoformat()]
    valid_count = sum(r["tmax_c"] is not None for r in selected)
    expected_count = (end - start).days + 1
    low_quality = [r["year"] for r in annual if not r["reliable"]]
    total_days = sum(r["heatwave_days"] for r in annual)
    peak = max((r["tmax_c"] for r in selected if r["tmax_c"] is not None), default=None)
    insights = []
    if comparison["available"]:
        delta = comparison["percent_change"]
        if delta is None:
            sentence = f"Average heatwave days changed from {comparison['early_mean']} to {comparison['late_mean']} per year; a percentage cannot be calculated from a zero baseline."
        else:
            direction = "increased" if delta > 0 else "decreased" if delta < 0 else "remained unchanged"
            sentence = f"Average annual heatwave days {direction}" + (f" by {abs(delta):.1f}%" if delta else "") + f" between {comparison['early_period']} and {comparison['late_period']}."
        insights.append(sentence)
    else:
        insights.append(comparison["reason"])
    if trends["heatwave_days"]["available"]:
        slope = trends["heatwave_days"]["slope_per_decade"]
        insights.append(f"The fitted heatwave-day trend is {slope:+.2f} days per decade. This describes the selected series and is not a causal conclusion.")
    if low_quality:
        insights.append(f"{len(low_quality)} low-coverage year(s) are excluded from regression; detected events in those years are lower-bound estimates.")
    if any(e["boundary_truncated"] for e in events):
        insights.append("An event touches the weather-data boundary. Its duration is a lower bound and its true onset may precede the available data.")
    return {
        "algorithm_version": ALGORITHM_VERSION,
        "methodology": {
            "hazard": "heatwave", "percentile": percentile, "min_duration_days": min_duration,
            "threshold_c": round(threshold, 3), "baseline": "1991–2020",
            "baseline_coverage_pct": round(baseline_coverage * 100, 2),
            "definition": f"At least {min_duration} consecutive calendar days with daily maximum temperature strictly above the {percentile:g}th percentile of the fixed 1991–2020 baseline.",
            "threshold_scope": "All-season, location-specific daily maximum temperatures; not a seasonally varying percentile or an official warning definition.",
            "year_attribution": "Events are counted in their onset year; heatwave days are allocated to their calendar year. Events overlapping the selected range are shown in full.",
        },
        "summary": {
            "total_events": len(events), "total_heatwave_days": total_days,
            "longest_event_days": max((e["duration_days"] for e in events), default=0),
            "mean_event_duration_days": round(mean(e["duration_days"] for e in events), 2) if events else 0,
            "peak_temperature_c": round(peak, 2) if peak is not None else None,
            "years_analyzed": len(annual), "reliable_years": len(annual) - len(low_quality),
        },
        "quality": {
            "expected_days": expected_count, "valid_days": valid_count,
            "missing_days": expected_count - valid_count,
            "coverage_pct": round(valid_count / expected_count * 100, 2),
            "excluded_trend_years": low_quality, "min_coverage_pct": MIN_COVERAGE * 100,
            "cleaning": cleaning or {}, "missing_data_policy": "No interpolation; missing or invalid days break heatwave runs.",
        },
        "annual": annual, "events": sorted(events, key=lambda e: e["start_date"], reverse=True),
        "trends": trends, "comparison": comparison, "insights": insights,
    }
