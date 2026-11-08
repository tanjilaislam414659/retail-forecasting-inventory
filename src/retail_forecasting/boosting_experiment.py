"""One validation-informed, fixed Poisson boosting experiment on saved rows."""

from datetime import datetime, timezone
from importlib.metadata import version
import json
from pathlib import Path
import time
import warnings

import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from retail_forecasting.acquisition import sha256
from retail_forecasting.boosting_model import MODEL_PARAMETERS, make_pipeline
from retail_forecasting.metrics import summarize
from retail_forecasting.ridge_features import CATEGORICAL_FEATURES, MODEL_FEATURES, NUMERIC_FEATURES

MODEL_NAME = "hist_poisson"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def write_json(path: Path, data: dict):
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def save_frame(path: Path, frame: pd.DataFrame):
    compression = {"method": "gzip", "mtime": 0} if path.suffix == ".gz" else None
    frame.to_csv(path, index=False, compression=compression)


def comparison(table: pd.DataFrame, keys: list[str], baseline="weekday_mean") -> pd.DataFrame:
    measures = ["macro_mase", "mae", "wape_pct", "mean_bias_units", "bias_pct"]
    candidate = table.loc[table.model.eq(MODEL_NAME), keys + measures].rename(columns={m: "candidate_" + m for m in measures})
    reference = table.loc[table.model.eq(baseline), keys + measures].rename(columns={m: "baseline_" + m for m in measures})
    result = candidate.merge(reference, on=keys, validate="one_to_one") if keys else candidate.merge(reference, how="cross")
    for metric in ("macro_mase", "mae", "wape_pct"):
        x, base = result["candidate_" + metric], result["baseline_" + metric]
        result[metric + "_difference"] = x - base
        result[metric + "_relative_change_pct"] = 100 * (x / base.where(base.ne(0)) - 1)
        result[metric + "_relative_status"] = np.select([x.isna() | base.isna(), base.eq(0)],
            ["undefined_input", "undefined_zero_baseline"], default="defined")
    result["signed_bias_difference_units"] = result.candidate_mean_bias_units - result.baseline_mean_bias_units
    result["bias_difference_pp"] = result.candidate_bias_pct - result.baseline_bias_pct
    base_bias = result.baseline_mean_bias_units.abs()
    result["absolute_bias_relative_change_pct"] = 100 * (result.candidate_mean_bias_units.abs() / base_bias.where(base_bias.ne(0)) - 1)
    result["absolute_bias_relative_status"] = np.where(base_bias.eq(0), "undefined_zero_baseline", "defined")
    delta = result.macro_mase_difference
    result["candidate_result"] = np.select([delta.isna(), delta.abs().le(1e-10), delta.lt(0)], ["undefined", "tie", "win"], default="loss")
    return result


def protected_artifacts(root: Path) -> dict:
    """Verify and retain hashes for every earlier generated result and saved model."""
    protected = {}
    for location in ("data/processed/preparation-manifest.json", "data/baselines/manifest.json", "data/ridge/manifest.json"):
        path = root / location
        manifest = json.loads(path.read_text())
        protected[location] = sha256(path)
        for name, entry in manifest["outputs"].items():
            target = root / "data/processed" / name if location.startswith("data/processed") else root / name
            require(sha256(target) == entry["sha256"], f"Changed prior artifact: {target}")
            protected[target.relative_to(root).as_posix()] = entry["sha256"]
        protected.update(manifest.get("plots", {}))
    ridge_manifest = json.loads((root / "data/ridge/manifest.json").read_text())
    protected["models/ridge/pipeline.joblib"] = ridge_manifest["pipeline_sha256"]
    protected["models/ridge/fit-record.json"] = ridge_manifest["fit_record_sha256"]
    for folder in ("configs", "docs"):
        for path in (root / folder).iterdir():
            if path.is_file() and "boosting" not in path.name and "milestone-5" not in path.name:
                protected[path.relative_to(root).as_posix()] = sha256(path)
    for name, digest in protected.items():
        require(sha256(root / name) == digest, f"Changed protected input: {name}")
    return protected


def fit_or_reuse(root: Path, train: pd.DataFrame, config: dict):
    directory = root / "models/boosting"
    directory.mkdir(parents=True, exist_ok=True)
    path, record_path = directory / "pipeline.joblib", directory / "fit-record.json"
    signature = {
        "specification_sha256": sha256(root / "configs/boosting.json"),
        "training_rows_sha256": sha256(root / config["training_examples"]),
        "model_code_sha256": sha256(Path(__file__).with_name("boosting_model.py")),
        "versions": {name: version(name) for name in ("numpy", "pandas", "scikit-learn", "scipy", "joblib", "threadpoolctl")},
    }
    if path.exists() or record_path.exists():
        require(path.exists() and record_path.exists(), "Incomplete existing candidate fit; refusing a new fit.")
        record = json.loads(record_path.read_text())
        require(record["signature"] == signature and record["pipeline_sha256"] == sha256(path), "Saved fit signature differs; refusing a new fit.")
        print("Reusing the verified single Poisson-boosting fit; no refit.", flush=True)
        return joblib.load(path), record, True
    pipeline = make_pipeline()
    # Category preparation is reported separately, without including it in fit time.
    x = train[MODEL_FEATURES]
    wall, cpu = time.perf_counter(), time.process_time()
    categories = pipeline.named_steps["categories"]
    typed = categories.fit_transform(x)
    category_times = {"category_preparation_wall_seconds": time.perf_counter() - wall,
                      "category_preparation_cpu_seconds": time.process_time() - cpu}
    wall, cpu = time.perf_counter(), time.process_time()
    with warnings.catch_warnings(record=True) as caught, threadpool_limits(limits=1):
        warnings.simplefilter("always")
        pipeline.named_steps["estimator"].fit(typed, train.actual_sales, sample_weight=None)
    fit_times = {"fit_wall_seconds": time.perf_counter() - wall, "fit_cpu_seconds": time.process_time() - cpu}
    joblib.dump(pipeline, path, compress=3)
    record = {"signature": signature, "fit_count": 1, "fit_completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "training_rows": len(train), "pipeline_sha256": sha256(path), **category_times, **fit_times,
        "fit_warnings": [{"category": item.category.__name__, "message": str(item.message)} for item in caught]}
    write_json(record_path, record)
    return pipeline, record, False


def timed_predictions(pipeline, frame):
    wall, cpu = time.perf_counter(), time.process_time()
    with warnings.catch_warnings(record=True) as caught, threadpool_limits(limits=1):
        warnings.simplefilter("always")
        predictions = pipeline.predict(frame[MODEL_FEATURES])
    return predictions, {"wall_seconds": time.perf_counter() - wall, "cpu_seconds": time.process_time() - cpu,
        "warnings": [{"category": item.category.__name__, "message": str(item.message)} for item in caught]}


def diagnostics(forecasts):
    data = forecasts.assign(actual_zero=forecasts.actual_sales.eq(0), target_weekday=forecasts.target_date.dt.day_name(),
        absolute_error=(forecasts.predicted_sales - forecasts.actual_sales).abs(),
        signed_error=forecasts.predicted_sales - forecasts.actual_sales)
    tables = {}
    total_errors = data.groupby("model").absolute_error.sum()
    for dimension in ("actual_zero", "target_weekday"):
        table = data.groupby(["model", dimension]).agg(row_count=("actual_sales", "size"),
            actual_mean=("actual_sales", "mean"), prediction_mean=("predicted_sales", "mean"),
            absolute_error_units=("absolute_error", "sum"), mae=("absolute_error", "mean"),
            mean_bias_units=("signed_error", "mean")).reset_index()
        denominator = table.model.map(total_errors)
        table["absolute_error_share_pct"] = 100 * table.absolute_error_units / denominator.where(denominator.ne(0))
        tables[dimension] = table
    return tables


def run_boosting(root: Path):
    started_wall, started_cpu = time.perf_counter(), time.process_time()
    output = root / "data/boosting"
    output.mkdir(parents=True, exist_ok=True)
    config = json.loads((root / "configs/boosting.json").read_text())
    require(config["estimator"] == MODEL_PARAMETERS and config["primary_metric"] == "macro_mase"
            and config["numeric_features"] == NUMERIC_FEATURES and config["categorical_features"] == CATEGORICAL_FEATURES
            and config["fit_count"] == 1 and not config["validation_refit"] and not config["numeric_scaling"], "Fixed candidate specification changed.")
    specification_path = output / "experiment-specification.json"
    if specification_path.exists():
        require(json.loads(specification_path.read_text()) == config, "Recorded candidate specification differs.")
    else:
        write_json(specification_path, config)
    protected = protected_artifacts(root)
    load_wall, load_cpu = time.perf_counter(), time.process_time()
    dtypes = {"sku": str, "target_weekday": str, "target_month": str}
    dates = ["origin", "target_date", "history_start", "history_end"]
    train = pd.read_csv(root / config["training_examples"], dtype=dtypes, parse_dates=dates)
    valid = pd.read_csv(root / config["validation_features"], dtype=dtypes, parse_dates=dates)
    feature_loading = {"feature_loading_wall_seconds": time.perf_counter() - load_wall,
                       "feature_loading_cpu_seconds": time.process_time() - load_cpu}
    require(len(train) == 185584 and len(valid) == 28000 and train.sku.nunique() == valid.sku.nunique() == 100, "Saved rows/cohort differ.")
    require(train.target_date.lt("2011-06-06").all() and valid.target_date.ge("2011-06-06").all()
            and valid.target_date.lt("2011-09-05").all(), "Target boundary violation.")
    require(sorted(valid.origin.dt.strftime("%Y-%m-%d").unique()) == config["validation_origins"], "Origin mismatch.")
    require(train.history_end.lt(train.origin).all() and valid.history_end.lt(valid.origin).all(), "Feature availability violation.")
    require(np.isfinite(train.actual_sales).all() and train.actual_sales.ge(0).all() and train.actual_sales.sum() > 0,
            "Poisson requires nonnegative targets with a positive sum.")
    require(np.isfinite(train[NUMERIC_FEATURES]).all().all() and np.isfinite(valid[NUMERIC_FEATURES]).all().all(), "Nonfinite feature.")
    scales = pd.read_csv(root / "data/baselines/history_and_scales.csv", dtype={"sku": str})
    print(f"Reusing {len(train):,} saved training rows and {len(valid):,} validation features unchanged.", flush=True)
    pipeline, fit_record, reused = fit_or_reuse(root, train, config)
    validation_pred, validation_prediction_time = timed_predictions(pipeline, valid)
    training_pred, training_prediction_time = timed_predictions(pipeline, train)
    numeric_status = {
        "training_nonfinite_predictions": int((~np.isfinite(training_pred)).sum()),
        "validation_nonfinite_predictions": int((~np.isfinite(validation_pred)).sum()),
        "training_nonpositive_predictions": int((training_pred <= 0).sum()),
        "validation_nonpositive_predictions": int((validation_pred <= 0).sum()),
        "training_prediction_min": float(training_pred.min()), "training_prediction_max": float(training_pred.max()),
        "validation_prediction_min": float(validation_pred.min()), "validation_prediction_max": float(validation_pred.max()),
    }
    write_json(output / "numerical-status.json", {**numeric_status, "fit_warnings": fit_record["fit_warnings"],
        "validation_prediction_warnings": validation_prediction_time["warnings"], "training_prediction_warnings": training_prediction_time["warnings"]})
    require(all(numeric_status[name] == 0 for name in ("training_nonfinite_predictions", "validation_nonfinite_predictions",
            "training_nonpositive_predictions", "validation_nonpositive_predictions")), "Numerical or nonpositive prediction problem; no automatic repair or alternate fit.")
    columns = ["sku", "origin", "target_date", "horizon_day", "actual_sales"]
    candidate = valid[columns].copy()
    candidate.insert(0, "model", MODEL_NAME)
    candidate["horizon_week"] = (candidate.horizon_day - 1) // 7 + 1
    candidate["predicted_sales"] = validation_pred
    in_sample = train[columns].copy()
    in_sample.insert(0, "model", MODEL_NAME)
    in_sample["horizon_week"] = (in_sample.horizon_day - 1) // 7 + 1
    in_sample["predicted_sales"] = training_pred
    save_frame(output / "validation_forecasts.csv.gz", candidate)
    save_frame(output / "training_in_sample_predictions.csv.gz", in_sample)
    ridge = pd.read_csv(root / "data/ridge/validation_forecasts.csv.gz", dtype={"sku": str}, parse_dates=["origin", "target_date"])
    saved = pd.read_csv(root / "data/baselines/validation_forecasts.csv.gz", dtype={"sku": str}, parse_dates=["origin", "target_date"])
    weekday = saved.loc[saved.model.eq("weekday_mean")]
    keys = ["sku", "origin", "target_date", "horizon_day"]
    for frame in (ridge, weekday):
        aligned = candidate.merge(frame[keys + ["actual_sales"]], on=keys, validate="one_to_one", suffixes=("", "_reference"))
        require(len(aligned) == 28000 and aligned.actual_sales.eq(aligned.actual_sales_reference).all(), "Saved comparison instances differ.")
    all_forecasts = pd.concat([candidate, ridge[candidate.columns], weekday[candidate.columns]], ignore_index=True)
    dimensions = {"by_model": ["model"], "by_sku": ["model", "sku"], "by_origin": ["model", "origin"],
        "by_horizon_week": ["model", "horizon_week"], "by_sku_origin": ["model", "sku", "origin"],
        "by_sku_origin_week": ["model", "sku", "origin", "horizon_week"]}
    tables, comparisons = {}, {}
    for name, groups in dimensions.items():
        tables[name] = summarize(all_forecasts, scales, groups)
        save_frame(output / f"metrics_{name}.csv", tables[name])
        comparisons[name] = comparison(tables[name], groups[1:])
        save_frame(output / f"comparison_to_weekday_{name}.csv", comparisons[name])
    comparisons["sku_to_ridge"] = comparison(tables["by_sku"], ["sku"], "ridge")
    save_frame(output / "comparison_to_ridge_by_sku.csv", comparisons["sku_to_ridge"])
    train_metrics = summarize(in_sample, scales, ["model"])
    train_metrics.insert(0, "evaluation", "original-training in-sample")
    validation_metrics = tables["by_model"].loc[tables["by_model"].model.eq(MODEL_NAME)].copy()
    validation_metrics.insert(0, "evaluation", "walk-forward validation")
    performance = pd.concat([train_metrics, validation_metrics], ignore_index=True)
    save_frame(output / "training_vs_validation.csv", performance)
    diagnostic_tables = diagnostics(all_forecasts)
    for name, frame in diagnostic_tables.items():
        save_frame(output / f"diagnostics_by_{name}.csv", frame)
    for reference in ("ridge", "weekday_mean"):
        old = pd.read_csv(root / "data/ridge/metrics_by_model.csv").set_index("model").loc[reference]
        current = tables["by_model"].set_index("model").loc[reference]
        for metric in ("macro_mase", "mae", "wape_pct", "bias_pct"):
            require(np.isclose(old[metric], current[metric], rtol=1e-12), "Saved reference metrics changed.")
    transformer = pipeline.named_steps["categories"]
    estimator = pipeline.named_steps["estimator"]
    write_json(output / "categories.json", {"categories": transformer.categories_, "ordered": False,
        "training_rows_seen": transformer.n_samples_seen_, "feature_order": MODEL_FEATURES,
        "categorical_features": CATEGORICAL_FEATURES, "numeric_scaling": False,
        "native_categorical_mask": estimator.is_categorical_.tolist(), "iterations": int(estimator.n_iter_)})
    from retail_forecasting.boosting_reporting import make_plots, write_report
    history = pd.read_csv(root / "data/baselines/modelling_history.csv.gz", dtype={"sku": str}, parse_dates=["date"])
    plots = make_plots(root, history, all_forecasts, scales, tables)
    ridge_summary = json.loads((root / "data/ridge/summary.json").read_text())
    count = lambda table: {label: int(table.candidate_result.eq(label).sum()) for label in ("win", "tie", "loss", "undefined")}
    summary = {
        "training_rows": len(train), "validation_rows": len(valid), "fit_count": fit_record["fit_count"], "pipeline_reused": reused,
        "development_status": config["development_status"], "model_metrics": json.loads(tables["by_model"].to_json(orient="records")),
        "overall_vs_weekday": json.loads(comparisons["by_model"].to_json(orient="records"))[0],
        "sku_results_vs_weekday": count(comparisons["by_sku"]), "sku_results_vs_ridge": count(comparisons["sku_to_ridge"]),
        "training_vs_validation": json.loads(performance.to_json(orient="records")),
        "zero_positive_diagnostics": json.loads(diagnostic_tables["actual_zero"].to_json(orient="records")),
        "saturday_diagnostics": json.loads(diagnostic_tables["target_weekday"].loc[diagnostic_tables["target_weekday"].target_weekday.eq("Saturday")].to_json(orient="records")),
        "numerical_status": numeric_status, "fit_warnings": fit_record["fit_warnings"],
        "prediction_warnings": validation_prediction_time["warnings"] + training_prediction_time["warnings"],
        "new_sales_feature_calculations": 0,
        "historical_ridge_training_feature_wall_seconds": ridge_summary["training_feature_wall_seconds"],
        "historical_ridge_validation_feature_wall_seconds": ridge_summary["validation_feature_wall_seconds"],
        **feature_loading,
        "category_preparation_wall_seconds": fit_record["category_preparation_wall_seconds"],
        "category_preparation_cpu_seconds": fit_record["category_preparation_cpu_seconds"],
        "fit_wall_seconds": fit_record["fit_wall_seconds"], "fit_cpu_seconds": fit_record["fit_cpu_seconds"],
        "validation_prediction_time": validation_prediction_time, "training_prediction_time": training_prediction_time,
        "total_wall_seconds": time.perf_counter() - started_wall, "total_cpu_seconds": time.process_time() - started_cpu,
        "plots": plots,
    }
    write_json(output / "summary.json", summary)
    for name, digest in protected.items():
        require(sha256(root / name) == digest, f"Prior artifact modified: {name}")
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(), "evaluation": "validation-informed development; no final-test evaluation",
        "specification_sha256": sha256(root / "configs/boosting.json"), "specification_document_sha256": sha256(root / "docs/boosting-experiment-spec.md"),
        "protected_inputs": protected,
        "code_sha256": {name: sha256(Path(__file__).with_name(name)) for name in ("boosting_model.py", "boosting_experiment.py", "boosting_reporting.py")},
        "pipeline_sha256": sha256(root / "models/boosting/pipeline.joblib"), "fit_record_sha256": sha256(root / "models/boosting/fit-record.json"),
        "versions": fit_record["signature"]["versions"],
        "outputs": {p.relative_to(root).as_posix(): {"sha256": sha256(p), "bytes": p.stat().st_size}
            for p in sorted(output.iterdir()) if p.is_file() and p.name != "manifest.json"},
        "plots": {name: sha256(root / name) for name in plots["files"]},
    }
    write_json(output / "manifest.json", manifest)
    write_report(root, summary, tables, comparisons)
    print(tables["by_model"][["model", "macro_mase", "mae", "wape_pct", "mean_bias_units", "bias_pct"]].to_string(index=False), flush=True)
    print(f"Primary result versus weekday mean: {summary['overall_vs_weekday']['candidate_result']}; SKU results: {summary['sku_results_vs_weekday']}.", flush=True)
    return summary
