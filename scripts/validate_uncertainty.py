"""Independent read-only interval validation; no recalibration or final scoring."""

from importlib.metadata import version
import json
from pathlib import Path

import numpy as np
import pandas as pd

from retail_forecasting.acquisition import sha256


def main():
    root = Path(__file__).resolve().parents[1]
    output = root / "data/uncertainty"
    manifest = json.loads((output / "manifest.json").read_text())
    config = json.loads((root / "configs/uncertainty.json").read_text())
    record = json.loads((output / "calibration-record.json").read_text())
    assert pd.Timestamp(config["recorded_before_calculation_at_utc"]) < pd.Timestamp(record["calibrated_at_utc"])
    assert sha256(root / "configs/uncertainty.json") == manifest["specification_sha256"]
    assert sha256(root / "docs/uncertainty-specification.md") == manifest["specification_document_sha256"]
    assert sha256(root / "configs/first-release.json") == manifest["first_release_sha256"]
    assert json.loads((output / "experiment-specification.json").read_text()) == config
    for path, digest in manifest["protected_inputs"].items():
        assert sha256(root / path) == digest, f"Earlier artifact changed: {path}"
    for path, entry in manifest["outputs"].items():
        assert sha256(root / path) == entry["sha256"], f"Interval artifact changed: {path}"
    for path, digest in manifest["plots"].items():
        assert sha256(root / path) == digest
    for name, digest in manifest["code_sha256"].items():
        assert sha256(root / "src/retail_forecasting" / name) == digest
    for name, expected in manifest["versions"].items():
        assert version(name) == expected
    calibration = pd.read_csv(output / "historical_forecasts_residuals.csv.gz", dtype={"sku": str}, parse_dates=["origin", "target_date"])
    grid = pd.read_csv(root / "data/ridge/training_examples.csv.gz", dtype={"sku": str}, parse_dates=["origin", "target_date"])
    quantiles = pd.read_csv(output / "calibration_quantiles.csv", dtype={"sku": str})
    history = pd.read_csv(root / "data/baselines/modelling_history.csv.gz", dtype={"sku": str}, parse_dates=["date"])
    history = history.loc[history.date.lt("2011-06-06")]
    lookup = {sku: group.set_index("date").sales_units for sku, group in history.groupby("sku")}
    keys = ["sku", "origin", "target_date", "horizon_day"]
    assert len(calibration) == len(grid) == 185584 and calibration.target_date.lt("2011-06-06").all()
    matched = calibration.merge(grid[keys + ["actual_sales", "weekday_mean_8"]], on=keys, validate="one_to_one", suffixes=("", "_grid"))
    assert len(matched) == 185584 and matched.actual_sales.eq(matched.actual_sales_grid).all()
    np.testing.assert_array_equal(matched.point_prediction, matched.weekday_mean_8)
    np.testing.assert_array_equal(calibration.residual, calibration.actual_sales - calibration.point_prediction)
    assert calibration.horizon_week.eq((calibration.horizon_day - 1) // 7 + 1).all()
    for (sku, origin), group in calibration.groupby(["sku", "origin"]):
        ordered = group.sort_values("horizon_day")
        assert ordered.horizon_day.tolist() == list(range(1, 29))
        assert (ordered.target_date - ordered.origin).dt.days.eq(ordered.horizon_day - 1).all()
        source = lookup[sku]
        window = source.reindex(pd.date_range(origin - pd.Timedelta(days=56), periods=56))
        assert window.notna().all()
        expected = [window.loc[window.index.dayofweek == date.dayofweek].sum() / 8 for date in ordered.target_date]
        np.testing.assert_array_equal(ordered.point_prediction, expected)
    assert len(quantiles) == 800 and not quantiles.duplicated(["sku", "horizon_week", "level"]).any()
    missing = pd.read_csv(output / "missing_calibration_groups.csv", dtype={"sku": str})
    assert len(missing) == quantiles.calibration_status.ne("defined").sum()
    for (sku, week), rows in calibration.groupby(["sku", "horizon_week"]):
        for level, probabilities in [(80, [0.1, 0.9]), (95, [0.025, 0.975])]:
            saved = quantiles.loc[quantiles.sku.eq(sku) & quantiles.horizon_week.eq(week) & quantiles.level.eq(level)].iloc[0]
            expected = np.quantile(rows.residual, probabilities, method="linear")
            np.testing.assert_allclose([saved.lower_residual_quantile, saved.upper_residual_quantile], expected, rtol=1e-12, atol=1e-12)
            assert saved.residual_count == len(rows)
            assert saved.unique_target_dates == rows.target_date.nunique()
            assert saved.distinct_origins == rows.origin.nunique()
    intervals = pd.read_csv(output / "validation_intervals.csv.gz", dtype={"sku": str}, parse_dates=["origin", "target_date"])
    points = pd.read_csv(root / "data/baselines/validation_forecasts.csv.gz", dtype={"sku": str}, parse_dates=["origin", "target_date"])
    points = points.loc[points.model.eq("weekday_mean")]
    assert len(intervals) == 56000 and not intervals.duplicated(keys + ["level"]).any()
    assert intervals.target_date.ge("2011-06-06").all() and intervals.target_date.lt("2011-09-05").all()
    matched = intervals.merge(points[keys + ["actual_sales", "predicted_sales"]], on=keys, validate="many_to_one", suffixes=("", "_saved"))
    assert len(matched) == 56000 and matched.actual_sales.eq(matched.actual_sales_saved).all()
    np.testing.assert_array_equal(matched.point_prediction, matched.predicted_sales)
    expected_lower = np.maximum(0, intervals.point_prediction + intervals.lower_residual_quantile)
    expected_upper = np.maximum(0, intervals.point_prediction + intervals.upper_residual_quantile)
    np.testing.assert_allclose(intervals.lower, expected_lower, rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(intervals.upper, expected_upper, rtol=1e-12, atol=1e-12)
    assert intervals.lower.ge(0).all() and intervals.upper.ge(intervals.lower).all()
    pivot = intervals.pivot(index=keys, columns="level", values=["lower", "upper"])
    assert pivot["lower"][95].le(pivot["lower"][80] + 1e-12).all()
    assert pivot["upper"][95].ge(pivot["upper"][80] - 1e-12).all()
    below, above = intervals.actual_sales.lt(intervals.lower), intervals.actual_sales.gt(intervals.upper)
    width = intervals.upper - intervals.lower
    covered = ~below & ~above
    score = width + (2 / intervals.alpha) * (
        (intervals.lower - intervals.actual_sales).where(below, 0)
        + (intervals.actual_sales - intervals.upper).where(above, 0))
    np.testing.assert_array_equal(intervals.covered, covered.astype(float))
    np.testing.assert_array_equal(intervals.miss_below, below.astype(float))
    np.testing.assert_array_equal(intervals.miss_above, above.astype(float))
    np.testing.assert_allclose(intervals.interval_score, score, rtol=1e-12, atol=1e-12)
    for name, groups in {"overall": ["level"], "by_sku": ["level", "sku"],
        "by_horizon_week": ["level", "horizon_week"], "by_target_weekday": ["level", "target_weekday"],
        "by_origin": ["level", "origin"], "by_sku_horizon_week": ["level", "sku", "horizon_week"],
        "by_sku_week_weekday": ["level", "sku", "horizon_week", "target_weekday"]}.items():
        saved = pd.read_csv(output / f"metrics_{name}.csv", dtype={"sku": str}, parse_dates=["origin"] if "origin" in groups else None).set_index(groups)
        assert len(saved) == intervals.groupby(groups).ngroups
        for key, group in intervals.groupby(groups):
            row = saved.loc[key]
            y, lower, upper = group.actual_sales, group.lower, group.upper
            lo, hi = y < lower, y > upper
            expected_score = upper - lower + (2 / group.alpha) * ((lower - y).where(lo, 0) + (y - upper).where(hi, 0))
            assert row.forecast_count == len(group) and row.missing_interval_count == 0
            assert row.covered_count == (~lo & ~hi).sum()
            assert row.miss_below_count == lo.sum() and row.miss_above_count == hi.sum()
            assert row.zero_width_count == upper.eq(lower).sum()
            np.testing.assert_allclose([row.coverage_pct, row.mean_width, row.mean_interval_score],
                [100 * (~lo & ~hi).mean(), (upper - lower).mean(), expected_score.mean()], rtol=1e-12, atol=1e-12)
    print("PASS: preserved point/results hashes, exact historical grid/forecasts, residual sign, linear quantiles/counts, fixed validation bounds, nonnegative nesting and all coverage/width/score/miss tables; no final-test evaluation.")


if __name__ == "__main__":
    main()
