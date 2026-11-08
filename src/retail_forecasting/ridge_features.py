"""Origin-available features and original-training direct-horizon examples."""

import numpy as np
import pandas as pd

NUMERIC_FEATURES = ["horizon_day", "sales_mean_7", "sales_mean_28", "sales_mean_56",
                    "sales_std_28", "zero_share_28", "weekday_mean_8"]
CATEGORICAL_FEATURES = ["sku", "target_weekday", "target_month"]
MODEL_FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES


def origin_features(series: pd.Series, sku: str, origin: pd.Timestamp) -> pd.DataFrame:
    """Build all 28 feature rows using only sales strictly before the origin."""
    origin = pd.Timestamp(origin)
    if origin != origin.normalize():
        raise ValueError("Origin must be a calendar-day boundary.")
    past = series.loc[series.index < origin].sort_index()
    if not past.index.is_unique:
        raise ValueError("Duplicate history dates.")
    history_dates = pd.date_range(origin - pd.Timedelta(days=56), periods=56, freq="D")
    window = past.reindex(history_dates)
    if window.isna().any() or not np.isfinite(window).all() or window.lt(0).any():
        raise ValueError("Features require 56 preceding retained calendar days.")
    recent = window.iloc[-28:]
    weekday = window.groupby(window.index.dayofweek).mean()
    targets = pd.date_range(origin, periods=28, freq="D")
    return pd.DataFrame({
        "sku": str(sku), "origin": origin, "target_date": targets,
        "horizon_day": np.arange(1, 29), "target_weekday": targets.dayofweek.astype(str),
        "target_month": targets.month.astype(str), "sales_mean_7": window.iloc[-7:].mean(),
        "sales_mean_28": recent.mean(), "sales_mean_56": window.mean(),
        "sales_std_28": recent.std(ddof=0), "zero_share_28": recent.eq(0).mean(),
        "weekday_mean_8": [weekday.loc[day.dayofweek] for day in targets],
        "history_start": history_dates[0], "history_end": history_dates[-1],
    })


def training_examples(panel: pd.DataFrame, cutoff: str = "2011-06-06") -> pd.DataFrame:
    """All eligible Monday SKU/origin groups; every target stays in training."""
    cutoff = pd.Timestamp(cutoff)
    training = panel.loc[panel.date < cutoff]
    records = []
    for sku, group in training.groupby("sku", sort=True):
        series = group.set_index("date").sales_units.sort_index()
        if not series.index.is_unique:
            raise ValueError("Duplicate SKU/day in modelling history.")
        origins = pd.date_range(series.index.min() + pd.Timedelta(days=56),
                                cutoff - pd.Timedelta(days=28), freq="W-MON")
        for origin in origins:
            features = origin_features(series, sku, origin)
            targets = series.reindex(features.target_date)
            if targets.isna().any() or features.target_date.max() >= cutoff:
                raise ValueError("A training target is missing or outside original training.")
            features["actual_sales"] = targets.to_numpy()
            records.append(features)
    if not records:
        raise ValueError("No eligible original-training examples.")
    return pd.concat(records, ignore_index=True)


def validation_examples(panel: pd.DataFrame, origins: list[str]) -> pd.DataFrame:
    """Walk-forward feature refresh, with validation actuals attached separately."""
    records = []
    for origin in origins:
        for sku, group in panel.groupby("sku", sort=True):
            series = group.set_index("date").sales_units
            records.append(origin_features(series, sku, pd.Timestamp(origin)))
    return pd.concat(records, ignore_index=True)
