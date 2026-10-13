"""Synthetic inputs exist only in tests, never as dashboard weather data."""
from datetime import date, timedelta

import pytest


@pytest.fixture
def complete_records():
    day, end = date(1989, 10, 1), date(2026, 3, 31)
    rows = []
    while day <= end:
        rows.append({"date": day.isoformat(), "tmax_c": 30.0})
        day += timedelta(days=1)
    return rows


def set_heat(rows, start, days, temperature=40):
    start = date.fromisoformat(start)
    stamps = {(start + timedelta(days=i)).isoformat() for i in range(days)}
    for row in rows:
        if row["date"] in stamps:
            row["tmax_c"] = temperature
