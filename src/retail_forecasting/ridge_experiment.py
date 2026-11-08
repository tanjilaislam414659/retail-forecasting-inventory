"""One pooled Ridge fit; compare to saved weekday mean on validation only."""

from datetime import datetime, timezone
from importlib.metadata import version
import json
from pathlib import Path
import time

import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from retail_forecasting.acquisition import sha256
from retail_forecasting.metrics import summarize
from retail_forecasting.ridge_features import CATEGORICAL_FEATURES, MODEL_FEATURES, NUMERIC_FEATURES, training_examples, validation_examples
from retail_forecasting.ridge_model import make_pipeline


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def save_frame(path: Path, frame: pd.DataFrame) -> None:
    compression = {"method": "gzip", "mtime": 0} if path.suffix == ".gz" else None
    frame.to_csv(path, index=False, compression=compression)


def compare_metrics(table: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    measures = ["macro_mase", "mae", "wape_pct", "mean_bias_units", "bias_pct"]
    left = table.loc[table.model.eq("ridge"), keys + measures].rename(columns={m: "ridge_" + m for m in measures})
    right = table.loc[table.model.eq("weekday_mean"), keys + measures].rename(columns={m: "baseline_" + m for m in measures})
    result = left.merge(right, on=keys, validate="one_to_one") if keys else left.merge(right, how="cross")
    for metric in ("macro_mase", "mae", "wape_pct"):
        ridge, base = result["ridge_" + metric], result["baseline_" + metric]
        result[metric + "_difference"] = ridge - base
        result[metric + "_relative_change_pct"] = 100 * (ridge / base.where(base.ne(0)) - 1)
        result[metric + "_relative_status"] = np.select(
            [ridge.isna() | base.isna(), base.eq(0)], ["undefined_input", "undefined_zero_baseline"], default="defined")
    result["signed_bias_difference_units"] = result.ridge_mean_bias_units - result.baseline_mean_bias_units
    result["bias_difference_pp"] = result.ridge_bias_pct - result.baseline_bias_pct
    base_bias = result.baseline_mean_bias_units.abs()
    result["absolute_bias_relative_change_pct"] = 100 * (result.ridge_mean_bias_units.abs() / base_bias.where(base_bias.ne(0)) - 1)
    result["absolute_bias_relative_status"] = np.where(base_bias.eq(0), "undefined_zero_baseline", "defined")
    delta = result.macro_mase_difference
    result["ridge_result"] = np.select([delta.isna(), delta.abs().le(1e-10), delta.lt(0)],
                                        ["undefined", "tie", "win"], default="loss")
    return result


def fit_or_reuse(root: Path, train: pd.DataFrame, config: dict) -> tuple[object, dict, bool]:
    directory = root / "models/ridge"
    directory.mkdir(parents=True, exist_ok=True)
    pipeline_path, record_path = directory / "pipeline.joblib", directory / "fit-record.json"
    signature = {
        "specification_sha256": sha256(root / "configs/ridge.json"),
        "training_examples_sha256": sha256(root / "data/ridge/training_examples.csv.gz"),
        "code_sha256": {name: sha256(Path(__file__).with_name(name)) for name in ("ridge_features.py", "ridge_model.py")},
        "versions": {name: version(name) for name in ("numpy", "pandas", "scikit-learn", "scipy", "joblib", "threadpoolctl")},
    }
    if pipeline_path.exists() or record_path.exists():
        require(pipeline_path.exists() and record_path.exists(), "Incomplete existing fit artifact; refusing to overwrite or refit.")
        record = json.loads(record_path.read_text())
        require(record["signature"] == signature and record["pipeline_sha256"] == sha256(pipeline_path),
                "Existing fitted pipeline does not match this fixed experiment; refusing to refit.")
        print("Reusing the verified single fitted pipeline; no refit.", flush=True)
        return joblib.load(pipeline_path), record, True
    pipeline = make_pipeline()
    wall, cpu = time.perf_counter(), time.process_time()
    with threadpool_limits(limits=1):
        pipeline.fit(train[MODEL_FEATURES], train.actual_sales)
    timings = {"fit_wall_seconds": time.perf_counter() - wall, "fit_cpu_seconds": time.process_time() - cpu}
    joblib.dump(pipeline, pipeline_path, compress=3)
    record = {"fit_count": 1, "fit_completed_at_utc": datetime.now(timezone.utc).isoformat(),
              "signature": signature, "training_rows": len(train), "pipeline_sha256": sha256(pipeline_path), **timings}
    write_json(record_path, record)
    return pipeline, record, False


def run_ridge(root: Path) -> dict:
    wall_started, cpu_started = time.perf_counter(), time.process_time()
    output = root / "data/ridge"
    output.mkdir(parents=True, exist_ok=True)
    config_path = root / "configs/ridge.json"
    config = json.loads(config_path.read_text())
    require(config["primary_metric"] == "macro_mase" and config["ridge"] == {"alpha": 1.0, "solver": "cholesky", "fit_intercept": True}, "Fixed Ridge specification changed.")
    require(config["numeric_features"] == NUMERIC_FEATURES and config["categorical_features"] == CATEGORICAL_FEATURES
            and config["std_ddof"] == 0 and config["clip_negative_predictions"] and not config["prediction_rounding"]
            and config["horizon_days"] == 28 and config["fit_count"] == 1 and not config["validation_refit"],
            "Fixed features or fitting policy changed.")
    baseline_manifest_path = root / "data/baselines/manifest.json"
    baseline_manifest = json.loads(baseline_manifest_path.read_text())
    require(config["validation_origins"] == baseline_manifest["protocol"]["origins"], "Validation origins differ from saved baseline.")
    # Record the exact fixed specification before generating examples or fitting.
    spec_path = output / "experiment-specification.json"
    if spec_path.exists():
        require(json.loads(spec_path.read_text()) == config, "Recorded experiment specification differs.")
    else:
        write_json(spec_path, config)
    protected = {baseline_manifest_path.relative_to(root).as_posix(): sha256(baseline_manifest_path)}
    for name, entry in baseline_manifest["outputs"].items():
        require(sha256(root / name) == entry["sha256"], f"Changed baseline input: {name}")
        protected[name] = entry["sha256"]
    prep_path = root / "data/processed/preparation-manifest.json"
    prep = json.loads(prep_path.read_text())
    protected[prep_path.relative_to(root).as_posix()] = sha256(prep_path)
    for name, entry in prep["outputs"].items():
        path = root / "data/processed" / name
        require(sha256(path) == entry["sha256"], f"Changed prepared input: {name}")
        protected[path.relative_to(root).as_posix()] = entry["sha256"]
    history = pd.read_csv(root / "data/baselines/modelling_history.csv.gz", dtype={"sku": str}, parse_dates=["date"])
    scales = pd.read_csv(root / "data/baselines/history_and_scales.csv", dtype={"sku": str})
    require(history.date.lt("2011-09-05").all() and scales.sku.nunique() == 100, "Modelling view includes final test or changed cohort.")
    saved = pd.read_csv(root / "data/baselines/validation_forecasts.csv.gz", dtype={"sku": str}, parse_dates=["origin", "target_date"])
    baseline = saved.loc[saved.model.eq("weekday_mean")].copy()
    require(len(baseline) == 28000, "Saved weekday-mean comparison instances missing.")
    build_wall, build_cpu = time.perf_counter(), time.process_time()
    train = training_examples(history, config["training_target_end_exclusive"])
    train_wall, train_cpu = time.perf_counter() - build_wall, time.process_time() - build_cpu
    require(train.target_date.lt("2011-06-06").all() and train.origin.dt.dayofweek.eq(0).all(), "Training target boundary violation.")
    require(train.groupby("sku").ngroups == 100, "A selected SKU has no training examples.")
    save_frame(output / "training_examples.csv.gz", train)
    feature_wall, feature_cpu = time.perf_counter(), time.process_time()
    features = validation_examples(history, config["validation_origins"])
    feature_seconds = {"validation_feature_wall_seconds": time.perf_counter() - feature_wall,
                       "validation_feature_cpu_seconds": time.process_time() - feature_cpu}
    keys = ["sku", "origin", "target_date", "horizon_day"]
    features = features.merge(baseline[keys + ["actual_sales"]], on=keys, validate="one_to_one")
    require(len(features) == 28000 and features.target_date.lt("2011-09-05").all(), "Validation instances differ.")
    save_frame(output / "validation_features.csv.gz", features)
    print(f"Prepared {len(train):,} original-training examples; {len(features):,} validation instances.", flush=True)
    pipeline, fit_record, reused = fit_or_reuse(root, train, config)
    prediction_wall, prediction_cpu = time.perf_counter(), time.process_time()
    with threadpool_limits(limits=1):
        raw = pipeline.predict(features[MODEL_FEATURES])
    prediction_timings = {"prediction_wall_seconds": time.perf_counter() - prediction_wall,
                          "prediction_cpu_seconds": time.process_time() - prediction_cpu}
    require(np.isfinite(raw).all(), "Nonfinite raw Ridge predictions.")
    predictions = features[keys + ["actual_sales"]].copy()
    predictions.insert(0, "model", "ridge")
    predictions["horizon_week"] = (predictions.horizon_day - 1) // 7 + 1
    predictions["raw_predicted_sales"] = raw
    predictions["was_clipped"] = raw < 0
    predictions["predicted_sales"] = np.maximum(raw, 0)
    save_frame(output / "validation_forecasts.csv.gz", predictions)
    baseline["raw_predicted_sales"], baseline["was_clipped"] = baseline.predicted_sales, False
    combined = pd.concat([predictions, baseline], ignore_index=True)
    diagnostics = combined.assign(
        actual_zero=combined.actual_sales.eq(0), target_weekday=combined.target_date.dt.day_name(),
        absolute_error=(combined.predicted_sales - combined.actual_sales).abs(),
        signed_error=combined.predicted_sales - combined.actual_sales,
    )
    diagnostic_tables = {}
    for dimension in ("actual_zero", "target_weekday"):
        diagnostic_tables[dimension] = diagnostics.groupby(["model", dimension]).agg(
            row_count=("actual_sales", "size"), actual_mean=("actual_sales", "mean"),
            prediction_mean=("predicted_sales", "mean"), mae=("absolute_error", "mean"),
            mean_bias_units=("signed_error", "mean"), clipped_forecasts=("was_clipped", "sum"),
        ).reset_index()
        save_frame(output / f"diagnostics_by_{dimension}.csv", diagnostic_tables[dimension])
    dimensions = {"by_model": ["model"], "by_sku": ["model", "sku"], "by_origin": ["model", "origin"],
        "by_horizon_week": ["model", "horizon_week"], "by_sku_origin": ["model", "sku", "origin"],
        "by_sku_origin_week": ["model", "sku", "origin", "horizon_week"]}
    tables, comparisons = {}, {}
    for name, groups in dimensions.items():
        table = summarize(combined, scales, groups)
        clipping = combined.groupby(groups).was_clipped.agg(clipped_forecasts="sum", clipping_rate="mean").reset_index()
        clipping["clipping_rate_pct"] = 100 * clipping.pop("clipping_rate")
        table = table.merge(clipping, on=groups, validate="one_to_one")
        save_frame(output / f"metrics_{name}.csv", table)
        tables[name] = table
        comparisons[name] = compare_metrics(table, groups[1:])
        save_frame(output / f"comparison_{name}.csv", comparisons[name])
    existing = pd.read_csv(root / "data/baselines/metrics_by_model.csv").set_index("model").loc["weekday_mean"]
    unchanged = tables["by_model"].set_index("model").loc["weekday_mean"]
    for measure in ("mae", "wape_pct", "mean_bias_units", "bias_pct", "macro_mase"):
        require(np.isclose(existing[measure], unchanged[measure], rtol=1e-12), f"Saved comparator changed: {measure}")
    preprocessing = pipeline.named_steps["preprocessing"]
    scaler = preprocessing.named_transformers_["numeric"]
    encoder = preprocessing.named_transformers_["categorical"]
    write_json(output / "preprocessing.json", {
        "numeric_features": NUMERIC_FEATURES, "mean": scaler.mean_.tolist(), "scale": scaler.scale_.tolist(),
        "variance": scaler.var_.tolist(), "training_rows_seen": int(scaler.n_samples_seen_),
        "categorical_features": CATEGORICAL_FEATURES, "categories": [values.tolist() for values in encoder.categories_],
        "transformed_feature_count": len(preprocessing.get_feature_names_out()),
    })
    save_frame(output / "coefficients.csv", pd.DataFrame({"feature": list(preprocessing.get_feature_names_out()) + ["intercept"],
        "coefficient": list(pipeline.named_steps["ridge"].coef_) + [pipeline.named_steps["ridge"].intercept_]}))
    from retail_forecasting.ridge_reporting import make_plots, write_report
    plots = make_plots(root, history, combined, scales, tables, comparisons)
    summary = {
        "training_rows": len(train), "training_skus": train.sku.nunique(),
        "training_sku_origin_groups": train[["sku", "origin"]].drop_duplicates().shape[0],
        "training_first_origin": train.origin.min().date().isoformat(), "training_last_origin": train.origin.max().date().isoformat(),
        "training_first_target": train.target_date.min().date().isoformat(), "training_last_target": train.target_date.max().date().isoformat(),
        "training_origins_per_sku_min": int(train.groupby("sku").origin.nunique().min()),
        "training_origins_per_sku_max": int(train.groupby("sku").origin.nunique().max()),
        "validation_rows": len(predictions), "fit_count": fit_record["fit_count"], "pipeline_reused": reused,
        "clipped_predictions": int((raw < 0).sum()), "clipping_rate_pct": float(100 * (raw < 0).mean()),
        "raw_prediction_min": float(raw.min()), "raw_prediction_max": float(raw.max()),
        "raw_mean_bias_units": float(np.mean(raw - features.actual_sales.to_numpy())),
        "clipping_added_units": float(np.maximum(raw, 0).sum() - raw.sum()),
        "zero_actual_diagnostics": json.loads(diagnostic_tables["actual_zero"].loc[
            diagnostic_tables["actual_zero"].actual_zero].to_json(orient="records")),
        "saturday_diagnostics": json.loads(diagnostic_tables["target_weekday"].loc[
            diagnostic_tables["target_weekday"].target_weekday.eq("Saturday")].to_json(orient="records")),
        "sku_results": {str(k): int(v) for k, v in comparisons["by_sku"].ridge_result.value_counts().items()},
        "primary_metric": "macro_mase", "primary_result": comparisons["by_model"].ridge_result.iloc[0],
        "model_metrics": json.loads(tables["by_model"].to_json(orient="records")),
        "overall_comparison": json.loads(comparisons["by_model"].to_json(orient="records"))[0],
        "undefined_wape_groups": {k: int(v.wape_pct.isna().sum()) for k, v in tables.items()},
        "undefined_mase_groups": {k: int(v.macro_mase.isna().sum()) for k, v in tables.items()},
        "training_feature_wall_seconds": train_wall, "training_feature_cpu_seconds": train_cpu,
        **feature_seconds, **prediction_timings,
        "fit_wall_seconds": fit_record["fit_wall_seconds"], "fit_cpu_seconds": fit_record["fit_cpu_seconds"],
        "total_wall_seconds": time.perf_counter() - wall_started, "total_cpu_seconds": time.process_time() - cpu_started,
        "plots": plots,
    }
    write_json(output / "summary.json", summary)
    for path, digest in protected.items():
        require(sha256(root / path) == digest, f"Protected input modified: {path}")
    manifest = {"created_at_utc": datetime.now(timezone.utc).isoformat(), "evaluation": "validation only",
        "specification_sha256": sha256(config_path), "specification_document_sha256": sha256(root / "docs/ridge-experiment-spec.md"),
        "protected_inputs": protected,
        "code_sha256": {name: sha256(Path(__file__).with_name(name)) for name in ("ridge_features.py", "ridge_model.py", "ridge_experiment.py", "ridge_reporting.py")},
        "fit_record_sha256": sha256(root / "models/ridge/fit-record.json"), "pipeline_sha256": sha256(root / "models/ridge/pipeline.joblib"),
        "versions": fit_record["signature"]["versions"],
        "outputs": {p.relative_to(root).as_posix(): {"sha256": sha256(p), "bytes": p.stat().st_size}
            for p in sorted(output.iterdir()) if p.is_file() and p.name != "manifest.json"},
        "plots": {path: sha256(root / path) for path in plots["files"]},
    }
    write_json(output / "manifest.json", manifest)
    write_report(root, summary, tables, comparisons)
    print(tables["by_model"][["model", "macro_mase", "mae", "wape_pct", "mean_bias_units", "bias_pct"]].to_string(index=False), flush=True)
    print(f"Ridge primary result: {summary['primary_result']}; SKU results: {summary['sku_results']}; clipped {summary['clipped_predictions']:,}/{len(predictions):,}.", flush=True)
    return summary
