"""Reusable inference from past sales and frozen quantiles; no HTTP or actuals."""

from datetime import date

import numpy as np
import pandas as pd

from retail_forecasting.baselines import forecast
from retail_forecasting.uncertainty import issue_intervals


def infer_one(history: pd.Series, quantiles: pd.DataFrame, sku: str, origin: date, horizon_days=28) -> list[dict]:
    """Generate all 28 values at origin. Never look up saved evaluation forecasts."""
    if type(horizon_days) is not int or horizon_days != 28:
        raise ValueError("Only the fixed 28-day horizon is supported")
    origin = pd.Timestamp(origin)
    # This function and the preserved baseline both enforce strict availability.
    past = history.loc[history.index < origin]
    predictions = forecast(past, origin, "weekday_mean", horizon=28)
    points = pd.DataFrame({"sku": sku, "origin": origin, "target_date": predictions.index,
        "horizon_day": np.arange(1, 29), "point_prediction": predictions.to_numpy()})
    issued = issue_intervals(points, quantiles.loc[quantiles.sku.eq(sku)])
    if len(issued) != 56 or not issued.interval_status.eq("defined").all():
        raise ValueError("Every SKU/horizon-week/level needs frozen calibration")
    if not np.isfinite(issued[["lower", "upper", "point_prediction"]]).all().all():
        raise ValueError("Nonfinite inference output")
    by_level = {level: group.sort_values("horizon_day").reset_index(drop=True) for level, group in issued.groupby("level")}
    rows = []
    for index, (target, point) in enumerate(predictions.items()):
        rows.append({"target_date": target.date(), "horizon_day": index + 1, "predicted_sales": float(point),
            "interval_80": {"lower": float(by_level[80].iloc[index].lower), "upper": float(by_level[80].iloc[index].upper)},
            "interval_95": {"lower": float(by_level[95].iloc[index].lower), "upper": float(by_level[95].iloc[index].upper)}})
    return rows
