"""Fixed empirical historical-error daily prediction intervals, not guarantees."""

import numpy as np
import pandas as pd

from retail_forecasting.baselines import forecast

LEVELS = [
    {"level": 80, "alpha": 0.2, "lower_probability": 0.1, "upper_probability": 0.9},
    {"level": 95, "alpha": 0.05, "lower_probability": 0.025, "upper_probability": 0.975},
]


def historical_forecasts(history: pd.DataFrame, grid: pd.DataFrame, cutoff="2011-06-06") -> pd.DataFrame:
    """Replay weekday mean on the preserved original-training direct-horizon grid."""
    cutoff = pd.Timestamp(cutoff)
    if grid.empty or not grid.target_date.lt(cutoff).all():
        raise ValueError("Every calibration target must precede the training cutoff.")
    training = history.loc[history.date.lt(cutoff)]
    lookup = {sku: group.set_index("date").sales_units.sort_index() for sku, group in training.groupby("sku")}
    records = []
    for (sku, origin), group in grid.groupby(["sku", "origin"], sort=True):
        ordered = group.sort_values("horizon_day")
        targets = pd.date_range(origin, periods=28)
        if (len(ordered) != 28 or pd.Timestamp(origin).dayofweek != 0
            or ordered.horizon_day.tolist() != list(range(1, 29))
            or ordered.target_date.tolist() != targets.tolist()):
            raise ValueError("Calibration grid must contain complete Monday-origin 28-day windows.")
        # Public forecast() checks a complete 56-day window and excludes origin/future.
        prediction = forecast(lookup[sku], origin, "weekday_mean", 28)
        actual = lookup[sku].reindex(targets)
        if actual.isna().any() or not np.array_equal(actual.to_numpy(), ordered.actual_sales.to_numpy()):
            raise ValueError("Calibration grid actuals differ from original training history.")
        if "weekday_mean_8" in ordered and not np.array_equal(prediction.to_numpy(), ordered.weekday_mean_8.to_numpy()):
            raise ValueError("Historical weekday mean differs from saved origin-available features.")
        records.append(pd.DataFrame({"sku": sku, "origin": origin, "target_date": targets,
            "horizon_day": np.arange(1, 29), "horizon_week": np.repeat(np.arange(1, 5), 7),
            "actual_sales": actual.to_numpy(), "point_prediction": prediction.to_numpy(),
            "residual": actual.to_numpy() - prediction.to_numpy()}))
    return pd.concat(records, ignore_index=True)


def fit_quantiles(calibration: pd.DataFrame, skus: list[str], cutoff="2011-06-06") -> pd.DataFrame:
    """Unweighted linear residual quantiles; explicit rows for every missing group."""
    if not calibration.target_date.lt(cutoff).all():
        raise ValueError("Calibration target on/after training cutoff.")
    expected_residual = calibration.actual_sales - calibration.point_prediction
    if (not np.isfinite(expected_residual).all()
        or not np.array_equal(calibration.residual.to_numpy(), expected_residual.to_numpy())):
        raise ValueError("Residual must be finite actual minus point prediction.")
    groups = {(sku, week): group for (sku, week), group in calibration.groupby(["sku", "horizon_week"])}
    rows = []
    for sku in skus:
        for week in range(1, 5):
            group = groups.get((sku, week))
            for level in LEVELS:
                missing = group is None or group.empty
                bounds = [np.nan, np.nan] if missing else np.quantile(group.residual.to_numpy(),
                    [level["lower_probability"], level["upper_probability"]], method="linear")
                rows.append({"sku": sku, "horizon_week": week, **level,
                    "residual_count": 0 if missing else len(group),
                    "unique_target_dates": 0 if missing else group.target_date.nunique(),
                    "distinct_origins": 0 if missing else group.origin.nunique(),
                    "lower_residual_quantile": bounds[0], "upper_residual_quantile": bounds[1],
                    "calibration_status": "missing_calibration_group" if missing else "defined"})
    return pd.DataFrame(rows)


def issue_intervals(points: pd.DataFrame, quantiles: pd.DataFrame) -> pd.DataFrame:
    """Endpoints depend on point/quantiles only; outcomes are not an input."""
    if "actual_sales" in points:
        raise ValueError("Attach evaluation actuals only after issuing intervals.")
    if not np.isfinite(points.point_prediction).all() or points.point_prediction.lt(0).any():
        raise ValueError("Invalid point prediction.")
    points = points.copy()
    points["horizon_week"] = (points.horizon_day - 1) // 7 + 1
    expanded = points.merge(pd.DataFrame({"level": [80, 95]}), how="cross")
    issued = expanded.merge(quantiles, on=["sku", "horizon_week", "level"], how="left", validate="many_to_one")
    defined = issued.calibration_status.eq("defined")
    if (not np.isfinite(issued.loc[defined, ["lower_residual_quantile", "upper_residual_quantile"]]).all().all()
        or issued.loc[defined, "lower_residual_quantile"].gt(issued.loc[defined, "upper_residual_quantile"]).any()):
        raise ValueError("Invalid or reversed calibration quantiles.")
    issued["interval_status"] = np.where(defined, "defined", "missing_calibration_group")
    issued["lower"] = np.maximum(0, issued.point_prediction + issued.lower_residual_quantile).where(defined)
    issued["upper"] = np.maximum(0, issued.point_prediction + issued.upper_residual_quantile).where(defined)
    return issued


def score_intervals(issued: pd.DataFrame, actuals: pd.DataFrame) -> pd.DataFrame:
    """Inclusive coverage and central interval/Winkler score, with explicit missingness."""
    keys = ["sku", "origin", "target_date", "horizon_day"]
    scored = issued.merge(actuals[keys + ["actual_sales"]], on=keys, how="left", validate="many_to_one")
    if not np.isfinite(scored.actual_sales).all() or scored.actual_sales.lt(0).any():
        raise ValueError("Missing or invalid evaluation actuals.")
    defined = scored.interval_status.eq("defined")
    if scored.loc[defined, "lower"].gt(scored.loc[defined, "upper"]).any():
        raise ValueError("Reversed interval endpoints.")
    below, above = scored.actual_sales.lt(scored.lower), scored.actual_sales.gt(scored.upper)
    scored["covered"] = (~below & ~above).astype(float).where(defined)
    scored["miss_below"] = below.astype(float).where(defined)
    scored["miss_above"] = above.astype(float).where(defined)
    scored["width"] = (scored.upper - scored.lower).where(defined)
    scored["zero_width"] = scored.width.eq(0).astype(float).where(defined)
    scored["point_outside_interval"] = (scored.point_prediction.lt(scored.lower)
        | scored.point_prediction.gt(scored.upper)).astype(float).where(defined)
    scored["interval_score"] = (scored.width + (2 / scored.alpha) *
        ((scored.lower - scored.actual_sales).where(below, 0)
         + (scored.actual_sales - scored.upper).where(above, 0))).where(defined)
    scored["target_weekday"] = scored.target_date.dt.day_name()
    return scored


def summarize_intervals(scored: pd.DataFrame, dimensions: list[str]) -> pd.DataFrame:
    data = scored.assign(defined_interval=scored.interval_status.eq("defined").astype(int))
    result = data.groupby(dimensions, sort=True, dropna=False).agg(
        forecast_count=("interval_status", "size"), defined_interval_count=("defined_interval", "sum"),
        covered_count=("covered", "sum"), miss_below_count=("miss_below", "sum"), miss_above_count=("miss_above", "sum"),
        zero_width_count=("zero_width", "sum"), point_outside_count=("point_outside_interval", "sum"),
        mean_width=("width", "mean"), mean_interval_score=("interval_score", "mean"),
    ).reset_index()
    result["missing_interval_count"] = result.forecast_count - result.defined_interval_count
    complete = result.missing_interval_count.eq(0)
    result["coverage_pct"] = (100 * result.covered_count / result.forecast_count).where(complete)
    result["mean_width"] = result.mean_width.where(complete)
    result["mean_interval_score"] = result.mean_interval_score.where(complete)
    result["metrics_status"] = np.where(complete, "defined", "undefined_missing_intervals")
    for name in ("covered_count", "miss_below_count", "miss_above_count", "zero_width_count", "point_outside_count"):
        result[name] = result[name].astype(int)
    return result
