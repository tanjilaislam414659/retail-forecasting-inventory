"""Typed HTTP contracts; strict request fields and ISO calendar dates."""

from datetime import date, timedelta
import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, field_validator, model_validator

Units = Annotated[float, Field(ge=0, allow_inf_nan=False)]


class Schema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ForecastRequest(Schema):
    sku: StrictStr = Field(min_length=1, max_length=32, examples=["21212"])
    origin: date = Field(examples=["2011-11-07"])
    horizon_days: StrictInt = Field(default=28, ge=28, le=28, description="Fixed at 28; no other horizon supported.")

    @field_validator("origin", mode="before")
    @classmethod
    def iso_calendar_date(cls, value):
        if not isinstance(value, str) or re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is None:
            raise ValueError("origin must be a calendar date in YYYY-MM-DD format")
        try:
            return date.fromisoformat(value)
        except ValueError:
            raise ValueError("origin must be a valid calendar date") from None


class Bounds(Schema):
    lower: Units
    upper: Units

    @model_validator(mode="after")
    def ordered(self):
        if self.lower > self.upper:
            raise ValueError("Interval endpoints must be ordered")
        return self


class DailyPrediction(Schema):
    target_date: date
    horizon_day: int = Field(ge=1, le=28)
    predicted_sales: Units
    interval_80: Bounds
    interval_95: Bounds

    @model_validator(mode="after")
    def nested(self):
        if self.interval_95.lower > self.interval_80.lower or self.interval_95.upper < self.interval_80.upper:
            raise ValueError("95% daily interval must contain 80% interval")
        return self


class ForecastResponse(Schema):
    service_version: str
    forecast_release_id: str
    calibration_id: str
    forecast_method: Literal["weekday_mean"] = "weekday_mean"
    sku: str
    origin: date
    history_cutoff: date
    horizon_days: Literal[28] = 28
    historical_demo: Literal[True] = True
    intervals_experimental: Literal[True] = True
    interval_interpretation: str = "Experimental empirical historical-error daily prediction intervals; no coverage guarantee or total-sales interval."
    predictions: list[DailyPrediction] = Field(min_length=28, max_length=28)

    @model_validator(mode="after")
    def aligned(self):
        if self.history_cutoff != self.origin - timedelta(days=1):
            raise ValueError("History cutoff must precede origin by one calendar day")
        for day, row in enumerate(self.predictions, start=1):
            if row.horizon_day != day or row.target_date != self.origin + timedelta(days=day - 1):
                raise ValueError("Prediction dates must align to the entire fixed horizon")
        return self


class HealthResponse(Schema):
    status: Literal["alive"] = "alive"
    service_version: str


class ReadyResponse(Schema):
    status: Literal["ready", "not_ready"]
    service_version: str
    startup_ms: float
    forecast_release_id: str | None = None
    error_code: str | None = None


class MetadataResponse(Schema):
    service_version: str
    forecast_release_id: str
    calibration_id: str
    forecast_method: Literal["weekday_mean"] = "weekday_mean"
    horizon_days: Literal[28] = 28
    historical_demo: Literal[True] = True
    intervals_experimental: Literal[True] = True
    supported_skus: list[str]
    supported_origins: list[date]
    frequency: Literal["daily"] = "daily"
    limitations: list[str]


class ErrorDetail(Schema):
    code: str
    message: str


class ErrorResponse(Schema):
    detail: ErrorDetail


class ValidationIssue(Schema):
    location: list[str | int]
    code: str
    message: str


class ValidationErrorResponse(Schema):
    detail: list[ValidationIssue] | ErrorDetail
