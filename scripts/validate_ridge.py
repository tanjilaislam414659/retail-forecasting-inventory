"""Independent checks of the saved single fit; no fitting or final-test scoring."""

from importlib.metadata import version
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from retail_forecasting.acquisition import sha256
from retail_forecasting.ridge_features import MODEL_FEATURES, NUMERIC_FEATURES, CATEGORICAL_FEATURES


def main():
    root = Path(__file__).resolve().parents[1]
    directory = root / "data/ridge"
    manifest = json.loads((directory / "manifest.json").read_text())
    fit_record = json.loads((root / "models/ridge/fit-record.json").read_text())
    config = json.loads((root / "configs/ridge.json").read_text())
    assert sha256(root / "configs/ridge.json") == manifest["specification_sha256"]
    assert sha256(root / "docs/ridge-experiment-spec.md") == manifest["specification_document_sha256"]
    assert fit_record["fit_count"] == 1
    assert pd.Timestamp(config["recorded_before_fit_at_utc"]) < pd.Timestamp(fit_record["fit_completed_at_utc"])
    assert json.loads((directory / "experiment-specification.json").read_text()) == config
    for path, digest in manifest["protected_inputs"].items():
        assert sha256(root / path) == digest, f"Changed protected data: {path}"
    for path, entry in manifest["outputs"].items():
        assert sha256(root / path) == entry["sha256"], f"Changed Ridge output: {path}"
    for path, digest in manifest["plots"].items():
        assert sha256(root / path) == digest
    for name, digest in manifest["code_sha256"].items():
        assert sha256(root / "src/retail_forecasting" / name) == digest
    for name, expected in manifest["versions"].items():
        assert version(name) == expected
    pipeline_path = root / "models/ridge/pipeline.joblib"
    assert sha256(pipeline_path) == manifest["pipeline_sha256"] == fit_record["pipeline_sha256"]
    assert sha256(root / "models/ridge/fit-record.json") == manifest["fit_record_sha256"]
    assert sha256(directory / "training_examples.csv.gz") == fit_record["signature"]["training_examples_sha256"]

    dates = ["origin", "target_date", "history_start", "history_end"]
    dtypes = {"sku": str, "target_weekday": str, "target_month": str}
    train = pd.read_csv(directory / "training_examples.csv.gz", dtype=dtypes, parse_dates=dates)
    valid = pd.read_csv(directory / "validation_features.csv.gz", dtype=dtypes, parse_dates=dates)
    history = pd.read_csv(root / "data/baselines/modelling_history.csv.gz", dtype={"sku": str}, parse_dates=["date"])
    scales = pd.read_csv(root / "data/baselines/history_and_scales.csv", dtype={"sku": str}).set_index("sku")
    lookup = {sku: group.set_index("date").sales_units.sort_index() for sku, group in history.groupby("sku")}
    assert set(train.sku) == set(valid.sku) == set(scales.index) and len(scales) == 100
    assert train.target_date.lt("2011-06-06").all()
    assert history.date.lt("2011-09-05").all()
    expected_groups = set()
    for sku, series in lookup.items():
        for origin in pd.date_range(series.index.min() + pd.Timedelta(days=56), "2011-05-09", freq="W-MON"):
            expected_groups.add((sku, origin))
    assert set(zip(train.sku, train.origin)) == expected_groups, "Not all/only eligible Monday training origins used"
    assert len(train) == 28 * len(expected_groups) == fit_record["training_rows"]
    assert len(valid) == 28000
    assert sorted(valid.origin.dt.strftime("%Y-%m-%d").unique()) == config["validation_origins"]
    for frame in (train, valid):
        assert not frame.duplicated(["sku", "origin", "horizon_day"]).any()
        assert frame.groupby(["sku", "origin"]).size().eq(28).all()
        assert frame.origin.dt.dayofweek.eq(0).all()
        assert frame.history_end.eq(frame.origin - pd.Timedelta(days=1)).all()
        assert frame.history_start.eq(frame.origin - pd.Timedelta(days=56)).all()
        assert frame.history_end.lt(frame.origin).all()
        assert (frame.target_date - frame.origin).dt.days.eq(frame.horizon_day - 1).all()
        assert frame.target_weekday.eq(frame.target_date.dt.dayofweek.astype(str)).all()
        assert frame.target_month.eq(frame.target_date.dt.month.astype(str)).all()
        for (sku, origin), group in frame.groupby(["sku", "origin"]):
            ordered = group.sort_values("horizon_day")
            source = lookup[sku]
            window = source.reindex(pd.date_range(origin - pd.Timedelta(days=56), periods=56))
            assert window.notna().all()
            values = window.to_numpy(dtype=float)
            constants = {"sales_mean_7": np.mean(values[-7:]), "sales_mean_28": np.mean(values[-28:]),
                "sales_mean_56": np.mean(values), "sales_std_28": np.std(values[-28:], ddof=0),
                "zero_share_28": np.mean(values[-28:] == 0)}
            for name, expected in constants.items():
                np.testing.assert_allclose(ordered[name], expected, rtol=1e-12, atol=1e-12)
            expected_weekdays = [np.mean(values[window.index.dayofweek == day.dayofweek]) for day in ordered.target_date]
            np.testing.assert_allclose(ordered.weekday_mean_8, expected_weekdays, rtol=1e-12)
            np.testing.assert_array_equal(ordered.actual_sales, source.reindex(ordered.target_date))

    pipeline = joblib.load(pipeline_path)
    preprocess = pipeline.named_steps["preprocessing"]
    scaler = preprocess.named_transformers_["numeric"]
    encoder = preprocess.named_transformers_["categorical"]
    assert scaler.n_samples_seen_ == len(train)
    np.testing.assert_allclose(scaler.mean_, train[NUMERIC_FEATURES].mean(), rtol=1e-12)
    np.testing.assert_allclose(scaler.var_, train[NUMERIC_FEATURES].var(ddof=0), rtol=1e-12)
    for name, values in zip(CATEGORICAL_FEATURES, encoder.categories_):
        np.testing.assert_array_equal(values, np.sort(train[name].unique()))
    assert pipeline.named_steps["ridge"].alpha == 1.0
    assert pipeline.named_steps["ridge"].solver == "cholesky"
    forecasts = pd.read_csv(directory / "validation_forecasts.csv.gz", dtype={"sku": str}, parse_dates=["origin", "target_date"])
    baseline = pd.read_csv(root / "data/baselines/validation_forecasts.csv.gz", dtype={"sku": str}, parse_dates=["origin", "target_date"])
    baseline = baseline.loc[baseline.model.eq("weekday_mean")].copy()
    keys = ["sku", "origin", "target_date", "horizon_day"]
    assert len(forecasts) == len(baseline) == 28000
    aligned = forecasts.merge(baseline[keys + ["actual_sales"]], on=keys, validate="one_to_one", suffixes=("", "_baseline"))
    assert len(aligned) == 28000 and aligned.actual_sales.eq(aligned.actual_sales_baseline).all()
    assert forecasts.target_date.ge("2011-06-06").all() and forecasts.target_date.lt("2011-09-05").all()
    with threadpool_limits(limits=1):
        expected_raw = pipeline.predict(valid[MODEL_FEATURES])
    np.testing.assert_allclose(forecasts.raw_predicted_sales, expected_raw, rtol=1e-10, atol=1e-10)
    assert forecasts.was_clipped.eq(forecasts.raw_predicted_sales.lt(0)).all()
    np.testing.assert_array_equal(forecasts.predicted_sales, np.maximum(forecasts.raw_predicted_sales, 0))
    assert sha256(pipeline_path) == fit_record["pipeline_sha256"], "Saved fit changed during inference"
    metrics = pd.read_csv(directory / "metrics_by_model.csv").set_index("model")
    for model, frame in (("ridge", forecasts), ("weekday_mean", baseline)):
        error = frame.predicted_sales - frame.actual_sales
        per_sku_mae = frame.assign(absolute_error=error.abs()).groupby("sku").absolute_error.mean()
        mase = per_sku_mae / scales.mase_scale.reindex(per_sku_mae.index)
        expected = [mase.mean() if mase.notna().all() else np.nan, error.abs().mean(),
                    100 * error.abs().sum() / frame.actual_sales.sum(), error.mean(),
                    100 * error.sum() / frame.actual_sales.sum()]
        saved = metrics.loc[model, ["macro_mase", "mae", "wape_pct", "mean_bias_units", "bias_pct"]].to_numpy(dtype=float)
        np.testing.assert_allclose(saved, expected, rtol=1e-12)
    counts = {"by_model": 2, "by_sku": 200, "by_origin": 20, "by_horizon_week": 8,
              "by_sku_origin": 2000, "by_sku_origin_week": 8000}
    for name, count in counts.items():
        table = pd.read_csv(directory / f"metrics_{name}.csv")
        comparison = pd.read_csv(directory / f"comparison_{name}.csv")
        assert len(table) == count and len(comparison) == count // 2
        assert table.wape_pct.isna().eq(table.wape_status.ne("defined")).all()
        assert table.macro_mase.isna().eq(table.mase_status.ne("defined")).all()
    wins = pd.read_csv(directory / "comparison_by_sku.csv")
    delta = wins.ridge_macro_mase - wins.baseline_macro_mase
    expected_outcome = np.where(np.abs(delta) <= 1e-10, "tie", np.where(delta < 0, "win", "loss"))
    np.testing.assert_array_equal(wins.ridge_result, expected_outcome)
    relative = 100 * (wins.ridge_macro_mase / wins.baseline_macro_mase - 1)
    np.testing.assert_allclose(wins.macro_mase_relative_change_pct, relative, rtol=1e-12)
    print(f"PASS: single saved fit, all {len(train):,} training rows, origin-only features, train-only preprocessing, 28,000 matched validation forecasts, clipping, metrics and protected input hashes.")


if __name__ == "__main__":
    main()
