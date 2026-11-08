"""Calibrate the frozen uncertainty method on original training only."""

from datetime import datetime, timezone
from importlib.metadata import version
import json
from pathlib import Path
import time

import numpy as np
import pandas as pd

from retail_forecasting.acquisition import sha256
from retail_forecasting.uncertainty import LEVELS, historical_forecasts, fit_quantiles, issue_intervals, score_intervals, summarize_intervals


def require(condition, message):
    if not condition:
        raise ValueError(message)


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def save_frame(path, frame):
    frame.to_csv(path, index=False, compression={"method": "gzip", "mtime": 0} if path.suffix == ".gz" else None)


def protected_inputs(root):
    previous_path = root / "data/boosting/manifest.json"
    previous = json.loads(previous_path.read_text())
    protected = previous["protected_inputs"].copy()
    protected[previous_path.relative_to(root).as_posix()] = sha256(previous_path)
    protected.update({name: entry["sha256"] for name, entry in previous["outputs"].items()})
    protected.update(previous["plots"])
    protected["models/boosting/pipeline.joblib"] = previous["pipeline_sha256"]
    protected["models/boosting/fit-record.json"] = previous["fit_record_sha256"]
    for directory in ("configs", "docs"):
        for path in (root / directory).iterdir():
            if path.is_file() and not any(word in path.name for word in ("uncertainty", "milestone-6", "first-release", "final-evaluation")):
                protected[path.relative_to(root).as_posix()] = sha256(path)
    for name, digest in protected.items():
        require(sha256(root / name) == digest, f"Previous result changed: {name}")
    return protected


def run_uncertainty(root):
    started, cpu = time.perf_counter(), time.process_time()
    output = root / "data/uncertainty"
    output.mkdir(parents=True, exist_ok=True)
    config_path = root / "configs/uncertainty.json"
    config = json.loads(config_path.read_text())
    require(config["levels"] == LEVELS and config["quantile_method"] == "linear"
        and config["group_columns"] == ["sku", "horizon_week"] and config["required_history_days"] == 56
        and config["calibration_target_end_exclusive"] == "2011-06-06"
        and not config["rounding"] and not config["force_point_inside"] and not config["weekday_specific_rule"]
        and not config["calibration_updates_on_validation"] and not config["method_adjustments_after_coverage"],
        "Fixed uncertainty specification changed.")
    record_path = output / "experiment-specification.json"
    if record_path.exists():
        require(json.loads(record_path.read_text()) == config, "Recorded uncertainty specification differs.")
    else:
        write_json(record_path, config)
    protected = protected_inputs(root)
    history = pd.read_csv(root / "data/baselines/modelling_history.csv.gz", dtype={"sku": str}, parse_dates=["date"])
    grid = pd.read_csv(root / "data/ridge/training_examples.csv.gz", dtype={"sku": str}, parse_dates=["origin", "target_date"])
    cohort = pd.read_csv(root / "data/processed/sku_selection.csv", dtype={"sku": str})
    require(len(grid) == 185584 and cohort.sku.nunique() == 100 and set(grid.sku) == set(cohort.sku), "Training grid/cohort mismatch.")
    print("Replaying historical weekday-mean forecasts on the preserved training grid ...", flush=True)
    calibration_started = time.perf_counter()
    calibration = historical_forecasts(history, grid)
    save_frame(output / "historical_forecasts_residuals.csv.gz", calibration)
    quantiles = fit_quantiles(calibration, cohort.sku.tolist())
    save_frame(output / "calibration_quantiles.csv", quantiles)
    missing = quantiles.loc[quantiles.calibration_status.ne("defined")]
    save_frame(output / "missing_calibration_groups.csv", missing)
    write_json(output / "calibration-record.json", {
        "calibrated_at_utc": datetime.now(timezone.utc).isoformat(), "residual": "actual - prediction",
        "specification_sha256": sha256(config_path), "historical_grid_sha256": sha256(root / "data/ridge/training_examples.csv.gz"),
        "residual_forecasts_sha256": sha256(output / "historical_forecasts_residuals.csv.gz"),
        "quantiles_sha256": sha256(output / "calibration_quantiles.csv"),
        "calibration_rows": len(calibration), "calibration_target_end_exclusive": "2011-06-06",
        "missing_group_level_rows": len(missing), "quantile_method": "linear",
    })
    calibration_seconds = time.perf_counter() - calibration_started
    # Only after calibration is frozen do validation point forecasts/outcomes enter.
    saved = pd.read_csv(root / "data/baselines/validation_forecasts.csv.gz", dtype={"sku": str}, parse_dates=["origin", "target_date"])
    points = saved.loc[saved.model.eq("weekday_mean")].copy()
    require(len(points) == 28000 and sorted(points.origin.dt.strftime("%Y-%m-%d").unique()) == config["validation_origins"]
        and points.target_date.lt("2011-09-05").all(), "Validation grid mismatch.")
    keys = ["sku", "origin", "target_date", "horizon_day"]
    unscored = points[keys + ["predicted_sales"]].rename(columns={"predicted_sales": "point_prediction"})
    issued = issue_intervals(unscored, quantiles)
    scored = score_intervals(issued, points[keys + ["actual_sales"]])
    require(len(scored) == 56000 and not scored.duplicated(keys + ["level"]).any(), "Interval forecast count/key mismatch.")
    for level in (80, 95):
        aligned = scored.loc[scored.level.eq(level)].merge(points[keys + ["predicted_sales"]], on=keys, validate="one_to_one")
        require(np.array_equal(aligned.point_prediction.to_numpy(), aligned.predicted_sales.to_numpy()), "Point predictions changed.")
    save_frame(output / "validation_intervals.csv.gz", scored)
    dimensions = {"overall": ["level"], "by_sku": ["level", "sku"], "by_horizon_week": ["level", "horizon_week"],
        "by_target_weekday": ["level", "target_weekday"], "by_origin": ["level", "origin"],
        "by_sku_horizon_week": ["level", "sku", "horizon_week"],
        "by_sku_week_weekday": ["level", "sku", "horizon_week", "target_weekday"]}
    metrics = {}
    for name, groups in dimensions.items():
        metrics[name] = summarize_intervals(scored, groups)
        save_frame(output / f"metrics_{name}.csv", metrics[name])
    from retail_forecasting.uncertainty_reporting import make_plots, write_report
    scales = pd.read_csv(root / "data/baselines/history_and_scales.csv", dtype={"sku": str})
    plots = make_plots(root, history, scored, scales, metrics)
    defined = quantiles.loc[quantiles.calibration_status.eq("defined")]
    summary = {
        "point_forecaster": "weekday_mean; frozen first release", "interpretation": config["interpretation"],
        "calibration_rows": len(calibration),
        "calibration_unique_sku_target_dates": len(calibration[["sku", "target_date"]].drop_duplicates()),
        "calibration_sku_origin_groups": len(calibration[["sku", "origin"]].drop_duplicates()),
        "calibration_group_level_rows": len(quantiles), "missing_calibration_group_level_rows": len(missing),
        "sample_count_range": [int(defined.residual_count.min()), int(defined.residual_count.max())] if len(defined) else [],
        "unique_target_count_range": [int(defined.unique_target_dates.min()), int(defined.unique_target_dates.max())] if len(defined) else [],
        "origin_count_range": [int(defined.distinct_origins.min()), int(defined.distinct_origins.max())] if len(defined) else [],
        "calibration_first_target": calibration.target_date.min().date().isoformat(),
        "calibration_last_target": calibration.target_date.max().date().isoformat(),
        "validation_instances_per_level": 28000, "validation_interval_rows": len(scored),
        "validation_unique_sku_target_dates": len(points[["sku", "target_date"]].drop_duplicates()),
        "overall_metrics": json.loads(metrics["overall"].to_json(orient="records")),
        "horizon_metrics": json.loads(metrics["by_horizon_week"].to_json(orient="records")),
        "weekday_metrics": json.loads(metrics["by_target_weekday"].to_json(orient="records")),
        "calibration_wall_seconds": calibration_seconds,
        "total_wall_seconds": time.perf_counter() - started, "total_cpu_seconds": time.process_time() - cpu,
        "plots": plots,
    }
    write_json(output / "summary.json", summary)
    for name, digest in protected.items():
        require(sha256(root / name) == digest, f"Previous result modified: {name}")
    write_json(output / "manifest.json", {
        "created_at_utc": datetime.now(timezone.utc).isoformat(), "evaluation": "validation development only; no final-test evaluation",
        "specification_sha256": sha256(config_path), "specification_document_sha256": sha256(root / "docs/uncertainty-specification.md"),
        "first_release_sha256": sha256(root / "configs/first-release.json"), "protected_inputs": protected,
        "code_sha256": {name: sha256(Path(__file__).with_name(name)) for name in ("uncertainty.py", "uncertainty_experiment.py", "uncertainty_reporting.py")},
        "versions": {name: version(name) for name in ("retail-forecasting", "numpy", "pandas", "matplotlib")},
        "outputs": {path.relative_to(root).as_posix(): {"sha256": sha256(path), "bytes": path.stat().st_size}
            for path in sorted(output.iterdir()) if path.is_file() and path.name != "manifest.json"},
        "plots": {name: sha256(root / name) for name in plots["files"]},
    })
    write_report(root, summary, metrics)
    print(metrics["overall"][["level", "forecast_count", "coverage_pct", "mean_width", "mean_interval_score",
                             "miss_below_count", "miss_above_count", "zero_width_count"]].to_string(index=False), flush=True)
    print(f"Missing calibration group/level rows: {len(missing)}. Point forecasts unchanged; no final-test evaluation.", flush=True)
    return summary
