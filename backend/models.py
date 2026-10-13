"""Validated, bounded API inputs. Callers cannot supply an upstream URL."""
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    latitude: float = Field(ge=-89.9, le=89.9)
    longitude: float = Field(ge=-180, le=180)
    region_name: str = Field(default="Selected location", min_length=1, max_length=80)
    start_year: int = Field(default=1990, ge=1940)
    end_year: int = Field(default=2025, ge=1940)
    hazard: Literal["heatwave"] = "heatwave"
    percentile: float = Field(default=95, ge=90, le=99)
    min_duration: int = Field(default=3, ge=3, le=10)

    @model_validator(mode="after")
    def check_range(self):
        if self.end_year >= date.today().year:
            raise ValueError("Use complete historical years only; the current year is incomplete.")
        if self.start_year > self.end_year:
            raise ValueError("The start year must be before or equal to the end year.")
        if self.end_year - self.start_year > 85:
            raise ValueError("Select at most 86 years.")
        self.latitude = round(self.latitude, 4)
        self.longitude = round(self.longitude, 4)
        self.region_name = self.region_name.strip() or "Selected location"
        return self
