"""Append-only v2: lossless parsing of saved interval floats; original checker preserved.

See data/final_evaluation_corrections/001-validator-csv-roundtrip/defect.json.
No predictions, endpoints, scoring rules or results are changed.
"""

from io import StringIO
import json
from pathlib import Path

import numpy as np
import pandas as pd

from retail_forecasting.final_evaluation import OUTPUT, KEYS, verify_existing, read_json, show_summary
from retail_forecasting.metrics import summarize
from retail_forecasting.uncertainty import summarize_intervals


def equivalent(saved, expected, keys):
    # CSV round trip normalizes date representations without changing values.
    expected = pd.read_csv(StringIO(expected.to_csv(index=False)), dtype={"sku": str})
    pd.testing.assert_frame_equal(saved.sort_values(keys).reset_index(drop=True),
        expected.sort_values(keys).reset_index(drop=True), check_dtype=False, rtol=1e-11, atol=1e-11)


def main(root=None):
    root = Path(__file__).resolve().parents[1] if root is None else root
    out = root / OUTPUT
    summary = verify_existing(root)
    freeze = read_json(out / "freeze.json")
    start = read_json(out / "started.json")
    issued_record = read_json(out / "predictions-issued.json")
    done = read_json(out / "scoring-complete.json")
    assert pd.Timestamp(freeze["frozen_at_utc"]) < pd.Timestamp(start["unblinding_authorized_at_utc"]) < pd.Timestamp(issued_record["issued_at_utc"]) < pd.Timestamp(done["completed_at_utc"])
    assert not issued_record["targets_joined"]
    config = freeze["configuration"]
    dtype = {"sku": str}
    dates = ["origin", "target_date"]
    points = pd.read_csv(out / "point_forecasts.csv.gz", dtype=dtype, parse_dates=dates + ["history_last_date"])
    issued = pd.read_csv(out / "issued_point_forecasts.csv.gz", dtype=dtype, parse_dates=dates + ["history_last_date"])
    assert "actual_sales" not in issued and len(points) == len(issued) == 56000
    pd.testing.assert_frame_equal(points.drop(columns="actual_sales"), issued, check_dtype=False)
    assert points.model.value_counts().eq(28000).all() and points.model.nunique() == 2
    assert points.sku.nunique() == 100 and len(points[["sku", "target_date"]].drop_duplicates()) == 9100
    assert not points.duplicated(["model"] + KEYS).any()
    assert points.target_date.ge("2011-09-05").all() and points.target_date.lt("2011-12-05").all()
    assert sorted(points.origin.dt.strftime("%Y-%m-%d").unique()) == config["origins"]
    assert points.history_last_date.lt(points.origin).all() and points.origin.dt.dayofweek.eq(0).all()
    assert (points.target_date - points.origin).dt.days.eq(points.horizon_day - 1).all()
    assert points.horizon_week.eq((points.horizon_day - 1) // 7 + 1).all()
    assert np.isfinite(points[["predicted_sales", "actual_sales"]]).all().all() and points.predicted_sales.ge(0).all()
    panel = pd.read_csv(root / "data/processed/sales_daily.csv.gz", dtype=dtype, parse_dates=["date"])
    aligned = points.merge(panel[["sku", "date", "sales_units"]], left_on=["sku", "target_date"], right_on=["sku", "date"], validate="many_to_one")
    np.testing.assert_array_equal(aligned.actual_sales, aligned.sales_units)
    scales = pd.read_csv(root / config["scale_source"], dtype=dtype)
    assert len(scales) == 100 and scales.excluded_leading_days.sum() == 484 and scales.excluded_leading_days.gt(0).sum() == 10
    assert scales.loc[scales.sku.eq("21166"), "modelling_start"].iloc[0] == "2009-12-07"
    assert scales.training_end.eq("2011-06-05").all()
    for name, groups in config["point_groups"].items():
        saved = pd.read_csv(out / f"point_metrics_{name}.csv", dtype=dtype)
        equivalent(saved, summarize(points, scales, groups), groups)
    intervals = pd.read_csv(out / "interval_forecasts.csv.gz", dtype=dtype, parse_dates=dates, float_precision="round_trip")
    unscored = pd.read_csv(out / "issued_intervals.csv.gz", dtype=dtype, parse_dates=dates, float_precision="round_trip")
    assert "actual_sales" not in unscored and len(intervals) == len(unscored) == 56000
    pd.testing.assert_frame_equal(intervals[unscored.columns], unscored, check_dtype=False)
    assert not intervals.duplicated(KEYS + ["level"]).any()
    quantiles = pd.read_csv(root / config["calibration_source"], dtype=dtype)
    attached = intervals.merge(quantiles, on=["sku", "horizon_week", "level"], validate="many_to_one", suffixes=("", "_frozen"))
    for col in ("lower_residual_quantile", "upper_residual_quantile"):
        np.testing.assert_allclose(attached[col], attached[col + "_frozen"], rtol=0, atol=0)
    defined = intervals.interval_status.eq("defined")
    np.testing.assert_allclose(intervals.loc[defined, "lower"], np.maximum(0, intervals.loc[defined].point_prediction + intervals.loc[defined].lower_residual_quantile), rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(intervals.loc[defined, "upper"], np.maximum(0, intervals.loc[defined].point_prediction + intervals.loc[defined].upper_residual_quantile), rtol=1e-12, atol=1e-12)
    assert intervals.loc[defined].lower.ge(0).all() and intervals.loc[defined].upper.ge(intervals.loc[defined].lower).all()
    for level in (80, 95):
        part = intervals.loc[intervals.level.eq(level)]
        match = part.merge(points.loc[points.model.eq("weekday_mean"), KEYS + ["predicted_sales", "actual_sales"]], on=KEYS, suffixes=("", "_point"), validate="one_to_one")
        assert len(match) == 28000
        np.testing.assert_array_equal(match.point_prediction, match.predicted_sales)
        np.testing.assert_array_equal(match.actual_sales, match.actual_sales_point)
    nesting = intervals.pivot(index=KEYS, columns="level", values=["lower", "upper"])
    assert nesting["lower"][95].le(nesting["lower"][80] + 1e-12).all()
    assert nesting["upper"][95].ge(nesting["upper"][80] - 1e-12).all()
    below = intervals.actual_sales.lt(intervals.lower)
    above = intervals.actual_sales.gt(intervals.upper)
    np.testing.assert_array_equal(intervals.covered, (~below & ~above).astype(float))
    np.testing.assert_array_equal(intervals.miss_below, below.astype(float))
    np.testing.assert_array_equal(intervals.miss_above, above.astype(float))
    width = intervals.upper - intervals.lower
    score = width + (2 / intervals.alpha) * ((intervals.lower - intervals.actual_sales).where(below, 0) + (intervals.actual_sales - intervals.upper).where(above, 0))
    np.testing.assert_allclose(intervals.width, width, rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(intervals.interval_score, score, rtol=1e-12, atol=1e-12)
    for name, groups in config["interval_groups"].items():
        saved = pd.read_csv(out / f"interval_metrics_{name}.csv", dtype=dtype)
        equivalent(saved, summarize_intervals(intervals, groups), groups)
    calibration = read_json(root / "data/uncertainty/calibration-record.json")
    assert calibration["calibration_target_end_exclusive"] == "2011-06-06"
    assert issued_record["calibration_sha256"] == calibration["quantiles_sha256"]
    assert not (out / "failure.json").exists() and not summary["implementation_defects"]
    show_summary(summary, "PASS: final artifact hashes, issue-before-join sequence, dates/counts, unchanged calibration/scales/points, interval arithmetic and every metric table verified. No forecasting or refitting performed.")


if __name__ == "__main__":
    main()
