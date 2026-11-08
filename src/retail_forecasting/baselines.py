"""Fixed, origin-safe multi-step sales forecasts using past calendar days only."""

import numpy as np
import pandas as pd

MODELS = ("seasonal_naive", "recent_mean", "weekday_mean")


def forecast(history: pd.Series, origin: pd.Timestamp, model: str, horizon: int = 28) -> pd.Series:
    """Issue the whole horizon at once; never consume actuals on/after origin."""
    origin = pd.Timestamp(origin)
    if origin != origin.normalize() or horizon < 1:
        raise ValueError("Origin must be a calendar-day boundary and horizon positive.")
    if model not in MODELS:
        raise ValueError(f"Unknown baseline: {model}")
    # Filtering is inside this public function, not a caller convention.
    past = history.loc[history.index < origin].sort_index()
    if not past.index.is_unique:
        raise ValueError("History has duplicate calendar dates.")
    lookback = {"seasonal_naive": 7, "recent_mean": 28, "weekday_mean": 56}[model]
    dates = pd.date_range(origin - pd.Timedelta(days=lookback), periods=lookback, freq="D")
    window = past.reindex(dates)
    if window.isna().any() or not np.isfinite(window).all() or window.lt(0).any():
        raise ValueError(f"{model} requires {lookback} consecutive observed calendar days.")
    targets = pd.date_range(origin, periods=horizon, freq="D")
    if model == "seasonal_naive":
        predictions = np.tile(window.to_numpy(dtype=float), (horizon + 6) // 7)[:horizon]
    elif model == "recent_mean":
        predictions = np.full(horizon, window.mean(), dtype=float)
    else:
        # A 56-day window contains exactly eight occurrences of each weekday.
        weekday_means = window.groupby(window.index.dayofweek).mean()
        predictions = np.array([weekday_means.loc[day.dayofweek] for day in targets], dtype=float)
    return pd.Series(predictions, index=targets, name="predicted_sales")


def seasonal_scale(training: pd.Series, period: int = 7) -> tuple[float, int]:
    """MASE denominator from a contiguous, already-onset-trimmed training series."""
    training = training.sort_index()
    expected = pd.date_range(training.index.min(), training.index.max(), freq="D")
    if not training.index.is_unique or not training.index.equals(expected):
        raise ValueError("MASE training history must be consecutive daily dates.")
    if len(training) <= period or training.isna().any() or not np.isfinite(training).all():
        raise ValueError("Insufficient or invalid training values for the seasonal scale.")
    differences = np.abs(training.to_numpy(dtype=float)[period:] - training.to_numpy(dtype=float)[:-period])
    return float(differences.mean()), len(differences)
