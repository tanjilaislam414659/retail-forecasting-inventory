"""One frozen held-out assessment; repeats verify artifacts without reevaluation."""

from datetime import datetime, timezone
from importlib.metadata import version
import gzip
import json
from pathlib import Path
import time
import traceback

import numpy as np
import pandas as pd

from retail_forecasting.acquisition import sha256
from retail_forecasting.baselines import forecast
from retail_forecasting.metrics import summarize
from retail_forecasting.uncertainty import issue_intervals, score_intervals, summarize_intervals

OUTPUT = Path("data/final_evaluation")
REPORT = Path("docs/final-evaluation-report.md")
PLOTS = Path("reports/generated/final_evaluation")
KEYS = ["sku", "origin", "target_date", "horizon_day"]
MODELS = ("weekday_mean", "seasonal_naive")
PACKAGES = ("retail-forecasting", "numpy", "pandas", "matplotlib")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def save_frame(path, frame):
    # Exclusive creation also protects a partially completed run from overwrite.
    if path.suffix == ".gz":
        with path.open("xb") as raw:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
                compressed.write(frame.to_csv(index=False).encode("utf-8"))
    else:
        with path.open("x", encoding="utf-8", newline="") as stream:
            frame.to_csv(stream, index=False)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def config_for(root):
    config = read_json(root / "configs/final-evaluation.json")
    origins = pd.date_range("2011-09-05", "2011-11-07", freq="7D").strftime("%Y-%m-%d").tolist()
    require(config["origins"] == origins and config["selected_model"] == MODELS[0]
        and config["fixed_reference"] == MODELS[1] and config["cohort_size"] == 100
        and config["horizon_days"] == 28 and config["target_end_exclusive"] == "2011-12-05"
        and config["instances_per_point_method"] == 28000 and config["unique_sku_target_pairs"] == 9100
        and config["interval_levels"] == [80, 95] and not config["model_selection_from_final_test"],
        "Frozen final evaluation grid/model contract changed.")
    return config


def verify_hashes(root, entries):
    for name, digest in entries.items():
        require((root / name).is_file() and sha256(root / name) == digest, f"Hash mismatch or missing file: {name}")


def snapshot_inputs(root):
    """Hash bytes without parsing final outcomes; include earlier immutable results."""
    previous_path = root / "data/uncertainty/manifest.json"
    previous = read_json(previous_path)
    protected = previous["protected_inputs"].copy()
    protected.update({name: entry["sha256"] for name, entry in previous["outputs"].items()})
    protected.update(previous["plots"])
    protected[previous_path.relative_to(root).as_posix()] = sha256(previous_path)
    verify_hashes(root, protected)
    for directory in ("src", "scripts", "tests", "configs", "docs"):
        for path in sorted((root / directory).rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts and path.suffix in (".py", ".json", ".md", ".ps1"):
                require(path != root / REPORT, "A final report already exists; refusing a new freeze.")
                protected[path.relative_to(root).as_posix()] = sha256(path)
    for name in ("AGENTS.md", "README.md", "pyproject.toml", "requirements-lock.txt",
                 "data/processed/sales_daily.csv.gz", "data/processed/sku_selection.csv",
                 "data/baselines/history_and_scales.csv", "data/baselines/modelling_history.csv.gz"):
        protected[name] = sha256(root / name)
    return protected


def verify_freeze(root):
    record = read_json(root / OUTPUT / "freeze.json")
    verify_hashes(root, record["sha256"])
    for package, expected in record["versions"].items():
        require(version(package) == expected, f"Software version changed: {package}")
    require(record["configuration"] == config_for(root), "Configuration differs from freeze.")
    return record


def freeze_release(root):
    output = root / OUTPUT
    if output.exists():
        if (output / "manifest.json").exists():
            verify_existing(root)
        else:
            verify_freeze(root)
        print("Existing release freeze verified; no outcomes read or artifacts overwritten.", flush=True)
        return read_json(output / "freeze.json")
    config = config_for(root)
    require(not (root / REPORT).exists() and not (root / PLOTS).exists(), "Final artifacts already exist outside results directory.")
    hashes = snapshot_inputs(root)
    output.mkdir(parents=True, exist_ok=False)
    record = {"frozen_at_utc": now(), "phase": "before semantic final-outcome access",
        "configuration": config, "sha256": hashes,
        "versions": {name: version(name) for name in PACKAGES},
        "source_control": "Local Git main; no commit. Content hashes identify the working source.",
        "point_selection": "weekday_mean frozen before final; seasonal_naive fixed reference only",
        "uncertainty": "unchanged original-training empirical residual intervals; experimental"}
    write_json(output / "freeze.json", record)
    print(f"Release frozen at {record['frozen_at_utc']}; {len(hashes)} input/code/calibration hashes saved. No final sales parsed.", flush=True)
    return record


def issue_points(history, origins, end_exclusive, models=MODELS):
    """Issue unscored forecasts; filtering is both here and inside forecast()."""
    records = []
    lookup = {sku: group.set_index("date").sales_units.sort_index() for sku, group in history.groupby("sku")}
    for origin_string in origins:
        origin = pd.Timestamp(origin_string)
        require(origin.dayofweek == 0 and origin + pd.Timedelta(days=27) < pd.Timestamp(end_exclusive),
                "Invalid Monday origin or target end boundary.")
        for sku, series in sorted(lookup.items()):
            past = series.loc[series.index < origin]
            for model in models:
                prediction = forecast(past, origin, model, 28)
                records.append(pd.DataFrame({"model": model, "sku": sku, "origin": origin,
                    "target_date": prediction.index, "horizon_day": np.arange(1, 29),
                    "horizon_week": np.repeat(np.arange(1, 5), 7),
                    "predicted_sales": prediction.to_numpy(), "history_last_date": past.index.max()}))
    result = pd.concat(records, ignore_index=True)
    require(np.isfinite(result.predicted_sales).all() and result.predicted_sales.ge(0).all(), "Invalid point forecasts.")
    require(result.history_last_date.lt(result.origin).all(), "History reaches forecast origin.")
    return result


def join_actuals(issued, history):
    require("actual_sales" not in issued, "Predictions already contain actuals.")
    actuals = history[["sku", "date", "sales_units"]].rename(columns={"date": "target_date", "sales_units": "actual_sales"})
    scored = issued.merge(actuals, on=["sku", "target_date"], how="left", validate="many_to_one")
    require(scored.actual_sales.notna().all() and np.isfinite(scored.actual_sales).all()
        and scored.actual_sales.ge(0).all(), "Missing or invalid final actuals.")
    return scored


def point_comparison(metrics):
    selected = metrics.loc[metrics.model.eq("weekday_mean")].iloc[0]
    reference = metrics.loc[metrics.model.eq("seasonal_naive")].iloc[0]
    rows = []
    for metric in ("macro_mase", "mae", "wape_pct", "mean_bias_units", "bias_pct"):
        denominator = reference[metric]
        rows.append({"metric": metric, "selected": selected[metric], "reference": denominator,
            "selected_minus_reference": selected[metric] - denominator,
            "relative_change_pct": 100 * (selected[metric] - denominator) / denominator if denominator != 0 else None,
            "relative_change_status": "defined" if denominator != 0 else "undefined_zero_reference",
            "interpretation": "negative is lower error" if metric in ("macro_mase", "mae", "wape_pct") else "signed quantities; compare distance from zero, not improvement"})
    return pd.DataFrame(rows)


def sku_comparison(metrics):
    wide = metrics.pivot(index="sku", columns="model", values="macro_mase").reset_index()
    delta = wide.weekday_mean - wide.seasonal_naive
    wide["selected_minus_reference_mase"] = delta
    wide["outcome"] = np.where(delta.abs().le(1e-10), "tie", np.where(delta.lt(0), "win", "loss"))
    wide.loc[delta.isna(), "outcome"] = "undefined"
    return wide


def diagnostics(forecasts):
    rows = []
    for model, frame in forecasts.groupby("model"):
        total_error = (frame.predicted_sales - frame.actual_sales).abs().sum()
        masks = {"zero_actual": frame.actual_sales.eq(0), "positive_actual": frame.actual_sales.gt(0),
                 "Saturday": frame.target_date.dt.dayofweek.eq(5)}
        for name, mask in masks.items():
            group = frame.loc[mask]
            error = (group.predicted_sales - group.actual_sales).abs().sum()
            rows.append({"model": model, "subset": name, "row_count": len(group),
                "actual_mean": group.actual_sales.mean(), "prediction_mean": group.predicted_sales.mean(),
                "absolute_error_units": error, "absolute_error_contribution_pct": 100 * error / total_error if total_error else None})
    return pd.DataFrame(rows)


def verify_existing(root):
    """Integrity only: never read the sales panel or call prediction/scoring functions."""
    output = root / OUTPUT
    manifest = read_json(output / "manifest.json")
    require(manifest["status"] == "complete", "Final results are incomplete.")
    verify_hashes(root, manifest["artifact_sha256"])
    verify_freeze(root)
    return read_json(output / "summary.json")


def show_summary(summary, prefix):
    print(prefix, flush=True)
    print(pd.DataFrame(summary["point_metrics"])[["model", "macro_mase", "mae", "wape_pct", "mean_bias_units", "bias_pct"]].to_string(index=False), flush=True)
    print(pd.DataFrame(summary["interval_metrics"])[["level", "coverage_pct", "mean_width", "mean_interval_score", "miss_below_count", "miss_above_count"]].to_string(index=False), flush=True)


def run_final(root):
    output = root / OUTPUT
    if (output / "manifest.json").exists():
        summary = verify_existing(root)
        show_summary(summary, "VERIFIED EXISTING FINAL RESULTS; no new forecasts, scoring or overwrite.")
        return summary
    if not output.exists():
        freeze_release(root)
    freeze = verify_freeze(root)
    require(not (output / "started.json").exists(),
        "An evaluation already started without a complete manifest. Refusing reevaluation/overwrite; preserve and investigate artifacts.")
    started = time.perf_counter()
    write_json(output / "started.json", {"unblinding_authorized_at_utc": now(),
        "freeze_sha256": sha256(output / "freeze.json"), "policy": "next operation reads final panel; no tuning or recalibration"})
    try:
        return _evaluate(root, freeze, started)
    except Exception:
        write_json(output / "failure.json", {"recorded_at_utc": now(), "exception": traceback.format_exc(),
            "policy": "Original artifacts preserved. No retry or correction performed. Investigate and log any genuine post-unblinding defect."})
        raise


def _evaluate(root, freeze, started):
    config = freeze["configuration"]
    output = root / OUTPUT
    load_started = time.perf_counter()
    # First semantic access to final outcomes happens only after freeze/start records.
    panel = pd.read_csv(root / "data/processed/sales_daily.csv.gz", dtype={"sku": str}, parse_dates=["date"])
    scales = pd.read_csv(root / config["scale_source"], dtype={"sku": str}, parse_dates=["modelling_start"])
    cohort = pd.read_csv(root / "data/processed/sku_selection.csv", dtype={"sku": str})
    require(len(panel) == 72800 and panel.sku.nunique() == len(scales) == len(cohort) == 100
        and set(panel.sku) == set(scales.sku) == set(cohort.sku), "Cohort/panel integrity mismatch.")
    require(not panel.duplicated(["sku", "date"]).any() and panel.sales_units.ge(0).all(), "Invalid source panel.")
    require(scales.excluded_leading_days.sum() == 484 and scales.excluded_leading_days.gt(0).sum() == 10,
        "Modelling-history mask mismatch.")
    require(scales.loc[scales.sku.eq("21166"), "modelling_start"].iloc[0] == pd.Timestamp("2009-12-07"), "SKU 21166 onset distinction lost.")
    history = panel.loc[panel.date.ge(panel.sku.map(scales.set_index("sku").modelling_start))].copy()
    original_history = pd.read_csv(root / "data/baselines/modelling_history.csv.gz", dtype={"sku": str}, parse_dates=["date"])
    prior = history.loc[history.date.lt("2011-09-05")].sort_values(["sku", "date"])
    old = original_history.sort_values(["sku", "date"])
    pd.testing.assert_frame_equal(prior[old.columns].reset_index(drop=True), old.reset_index(drop=True), check_dtype=False)
    quantiles = pd.read_csv(root / config["calibration_source"], dtype={"sku": str})
    require(len(quantiles) == 800 and set(quantiles.sku) == set(cohort.sku)
        and not quantiles.duplicated(["sku", "horizon_week", "level"]).any(), "Calibration group integrity mismatch.")
    loading_seconds = time.perf_counter() - load_started
    prediction_started = time.perf_counter()
    issued_points = issue_points(history, config["origins"], config["target_end_exclusive"])
    require(len(issued_points) == 56000 and not issued_points.duplicated(["model"] + KEYS).any(), "Final point grid mismatch.")
    selected = issued_points.loc[issued_points.model.eq("weekday_mean")]
    require(len(selected) == 28000 and len(selected[["sku", "target_date"]].drop_duplicates()) == 9100, "Final instance/unique-date mismatch.")
    save_frame(output / "issued_point_forecasts.csv.gz", issued_points)
    interval_points = selected[KEYS + ["predicted_sales"]].rename(columns={"predicted_sales": "point_prediction"})
    issued_intervals = issue_intervals(interval_points, quantiles)
    save_frame(output / "issued_intervals.csv.gz", issued_intervals)
    write_json(output / "predictions-issued.json", {"issued_at_utc": now(), "targets_joined": False,
        "point_forecasts_sha256": sha256(output / "issued_point_forecasts.csv.gz"),
        "intervals_sha256": sha256(output / "issued_intervals.csv.gz"),
        "calibration_sha256": sha256(root / config["calibration_source"]),
        "policy": "Each issue uses strictly prior history; all horizon values generated before target join."})
    prediction_seconds = time.perf_counter() - prediction_started
    scoring_started = time.perf_counter()
    scored = join_actuals(issued_points, history)
    selected_actuals = scored.loc[scored.model.eq("weekday_mean"), KEYS + ["actual_sales"]]
    intervals = score_intervals(issued_intervals, selected_actuals)
    save_frame(output / "point_forecasts.csv.gz", scored)
    save_frame(output / "interval_forecasts.csv.gz", intervals)
    point_metrics, interval_metrics = {}, {}
    for name, dimensions in config["point_groups"].items():
        point_metrics[name] = summarize(scored, scales, dimensions)
        save_frame(output / f"point_metrics_{name}.csv", point_metrics[name])
    for name, dimensions in config["interval_groups"].items():
        interval_metrics[name] = summarize_intervals(intervals, dimensions)
        save_frame(output / f"interval_metrics_{name}.csv", interval_metrics[name])
    comparison = point_comparison(point_metrics["by_model"])
    sku_results = sku_comparison(point_metrics["by_sku"])
    save_frame(output / "point_reference_comparison.csv", comparison)
    save_frame(output / "sku_reference_comparison.csv", sku_results)
    save_frame(output / "point_diagnostics.csv", diagnostics(scored))
    missing = quantiles.loc[quantiles.calibration_status.ne("defined")]
    save_frame(output / "missing_calibration_groups.csv", missing)
    # Copy saved validation summaries, without recomputing or changing earlier artifacts.
    validation_points = pd.read_csv(root / "data/baselines/metrics_by_model.csv")
    validation_points = validation_points.loc[validation_points.model.isin(MODELS)]
    validation_intervals = pd.read_csv(root / "data/uncertainty/metrics_overall.csv")
    save_frame(output / "validation_point_metrics_snapshot.csv", validation_points)
    save_frame(output / "validation_interval_metrics_snapshot.csv", validation_intervals)
    write_json(output / "scoring-complete.json", {"completed_at_utc": now(), "point_rows": len(scored), "interval_rows": len(intervals)})
    scoring_seconds = time.perf_counter() - scoring_started
    from retail_forecasting.final_reporting import make_plots, write_report
    plots = make_plots(root, history, scored, intervals, scales, interval_metrics, config)
    summary = {"evaluated_at_utc": now(), "selected_model": "weekday_mean", "reference": "seasonal_naive",
        "selection_changed": False, "uncertainty": config["uncertainty_label"], "point_instances_per_model": 28000,
        "unique_sku_target_pairs": 9100, "origins": config["origins"], "target_first": "2011-09-05", "target_last": "2011-12-04",
        "point_metrics": json.loads(point_metrics["by_model"].to_json(orient="records")),
        "interval_metrics": json.loads(interval_metrics["overall"].to_json(orient="records")),
        "reference_comparison": json.loads(comparison.to_json(orient="records")),
        "sku_mase_wins_ties_losses": sku_results.outcome.value_counts().to_dict(),
        "missing_calibration_group_level_rows": len(missing), "calibration_unchanged": True,
        "nonfinite_point_predictions": int((~np.isfinite(issued_points.predicted_sales)).sum()),
        "load_seconds": loading_seconds, "prediction_and_interval_seconds": prediction_seconds,
        "scoring_seconds": scoring_seconds, "total_wall_seconds": time.perf_counter() - started,
        "implementation_defects": [], "plots": plots,
        "test_claim": "Descriptive final held-out assessment; overlapping instances dependent; no significance claim."}
    write_report(root, summary, point_metrics, interval_metrics, validation_points, validation_intervals)
    write_json(output / "summary.json", summary)
    # All protected previous artifacts and frozen sources must still be identical.
    verify_freeze(root)
    artifact_paths = [p for p in output.iterdir() if p.is_file()] + [root / REPORT] + [root / name for name in plots["files"]]
    write_json(output / "manifest.json", {"status": "complete", "completed_at_utc": now(),
        "freeze_sha256": sha256(output / "freeze.json"),
        "artifact_sha256": {path.relative_to(root).as_posix(): sha256(path) for path in sorted(artifact_paths)},
        "policy": "No overwrite; repeat verifies saved hashes and reports existing summary without reevaluation."})
    verify_existing(root)
    show_summary(summary, "ONE FINAL EVALUATION COMPLETED; selected method remains weekday mean.")
    return summary
