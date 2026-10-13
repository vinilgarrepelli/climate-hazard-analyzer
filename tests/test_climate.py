from datetime import date

import pytest

from backend.climate import analyze, detect_heatwaves, normalize_daily, percentile_linear, period_comparison, regression
from conftest import set_heat


def test_percentile_linear_interpolation():
    assert percentile_linear([4, 1, 2, 3], 95) == pytest.approx(3.85)


def test_three_days_strictly_above_threshold():
    records = [{"date": f"2025-01-0{i}", "tmax_c": v} for i, v in enumerate([35, 36, 37, 30, 35, 36], 1)]
    events = detect_heatwaves(records, 30, 3)
    assert len(events) == 1
    assert events[0]["duration_days"] == 3
    assert events[0]["peak_temperature_c"] == 37
    assert events[0]["mean_exceedance_c"] == 6


def test_missing_day_breaks_run_even_when_date_is_absent():
    records = [{"date": "2025-01-01", "tmax_c": 40}, {"date": "2025-01-02", "tmax_c": 40},
               {"date": "2025-01-04", "tmax_c": 40}, {"date": "2025-01-05", "tmax_c": 40}]
    assert detect_heatwaves(records, 30, 3) == []


def test_null_and_threshold_equality_break_runs():
    records = [{"date": f"2025-01-0{i}", "tmax_c": v} for i, v in enumerate([40, 40, None, 40, 30, 40, 40], 1)]
    assert detect_heatwaves(records, 30) == []


def test_normalize_units_duplicates_outliers_and_leap_day():
    payload = {"daily_units": {"temperature_2m_max": "°F"}, "daily": {
        "time": ["2024-02-28", "2024-02-28", "2024-02-29", "2024-03-01", "bad"],
        "temperature_2m_max": [86, 88, 86, 1000, 75]}}
    rows, quality = normalize_daily(payload, date(2024, 2, 28), date(2024, 3, 2))
    assert len(rows) == 4
    assert rows[0]["tmax_c"] is None
    assert rows[1]["tmax_c"] == 30
    assert rows[2]["tmax_c"] is None
    assert rows[3]["tmax_c"] is None
    assert quality == {"invalid_values": 1, "duplicate_dates": 1, "malformed_dates": 1, "unit_converted": True}


def test_misaligned_arrays_rejected():
    with pytest.raises(ValueError, match="inconsistent"):
        normalize_daily({"daily": {"time": ["2020-01-01"], "temperature_2m_max": []}}, date(2020, 1, 1), date(2020, 1, 1))


def test_events_crossing_new_year_are_not_double_counted(complete_records):
    set_heat(complete_records, "1990-12-30", 4)
    result = analyze(complete_records, 1990, 1991)
    assert result["summary"]["total_events"] == 1
    assert [r["event_count"] for r in result["annual"]] == [1, 0]
    assert [r["heatwave_days"] for r in result["annual"]] == [2, 2]
    assert result["events"][0]["duration_days"] == 4
    assert result["events"][0]["boundary_truncated"] is False


def test_event_started_before_selection_is_in_log_but_not_onset_count(complete_records):
    set_heat(complete_records, "2020-12-30", 5)
    result = analyze(complete_records, 2021, 2021)
    assert result["summary"]["total_events"] == 1
    assert result["annual"][0]["event_count"] == 0
    assert result["annual"][0]["heatwave_days"] == 3


def test_fixed_baseline_does_not_change_with_selected_period(complete_records):
    set_heat(complete_records, "2023-05-01", 8)
    early = analyze(complete_records, 1990, 2020)
    late = analyze(complete_records, 2021, 2025)
    assert early["methodology"]["threshold_c"] == late["methodology"]["threshold_c"] == 30
    assert late["summary"]["total_heatwave_days"] == 8


def test_inadequate_baseline_rejected(complete_records):
    rows = [r for r in complete_records if not r["date"].startswith("1995") and not r["date"].startswith("1996")]
    with pytest.raises(ValueError, match="baseline"):
        analyze(rows, 2020, 2025)


def test_inadequate_analysis_year_excluded_from_trend(complete_records):
    for row in complete_records:
        if "2023-01-01" <= row["date"] < "2023-03-01":
            row["tmax_c"] = None
    result = analyze(complete_records, 2018, 2025)
    assert result["quality"]["excluded_trend_years"] == [2023]
    assert result["trends"]["heatwave_days"]["years_used"] == 7
    assert result["comparison"]["available"] is False
    assert result["annual"][-1]["rolling_days"] is None


def test_zero_starting_period_does_not_make_infinite_percentage():
    rows = [{"year": 2000 + i, "heatwave_days": 0 if i < 3 else 9, "reliable": True} for i in range(6)]
    comparison = period_comparison(rows)
    assert comparison["percent_change"] is None
    assert comparison["absolute_change"] == 9
    assert comparison["early_period"] == "2000–2002"
    assert comparison["late_period"] == "2003–2005"


def test_known_regression_slope_and_short_series():
    rows = [{"year": 2000 + i, "heatwave_days": 2 * i + 1, "reliable": True} for i in range(10)]
    result = regression(rows, "heatwave_days")
    assert result["slope_per_decade"] == 20
    assert result["r_squared"] == 1
    assert regression(rows[:4], "heatwave_days")["available"] is False


def test_boundary_truncation_is_disclosed():
    rows = [{"date": f"2025-01-0{i}", "tmax_c": 40} for i in range(1, 5)]
    assert detect_heatwaves(rows, 30)[0]["boundary_truncated"] is True
