"""Read-only validation of the single saved Poisson candidate; never refits."""

from importlib.metadata import version
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from retail_forecasting.acquisition import sha256
from retail_forecasting.boosting_model import MODEL_PARAMETERS
from retail_forecasting.ridge_features import CATEGORICAL_FEATURES, MODEL_FEATURES, NUMERIC_FEATURES


def main():
    root = Path(__file__).resolve().parents[1]
    output = root / "data/boosting"
    manifest = json.loads((output / "manifest.json").read_text())
    config = json.loads((root / "configs/boosting.json").read_text())
    record = json.loads((root / "models/boosting/fit-record.json").read_text())
    summary = json.loads((output / "summary.json").read_text())
    assert record["fit_count"] == 1
    assert pd.Timestamp(config["recorded_before_fit_at_utc"]) < pd.Timestamp(record["fit_completed_at_utc"])
    assert sha256(root / "configs/boosting.json") == manifest["specification_sha256"]
    assert sha256(root / "docs/boosting-experiment-spec.md") == manifest["specification_document_sha256"]
    assert json.loads((output / "experiment-specification.json").read_text()) == config
    assert sha256(root / "models/boosting/fit-record.json") == manifest["fit_record_sha256"]
    assert sha256(root / "models/boosting/pipeline.joblib") == manifest["pipeline_sha256"] == record["pipeline_sha256"]
    for path, digest in manifest["protected_inputs"].items():
        assert sha256(root / path) == digest, f"Previous result changed: {path}"
    for path, entry in manifest["outputs"].items():
        assert sha256(root / path) == entry["sha256"], f"Changed candidate output: {path}"
    for path, digest in manifest["plots"].items():
        assert sha256(root / path) == digest
    for name, digest in manifest["code_sha256"].items():
        assert sha256(root / "src/retail_forecasting" / name) == digest
    for name, expected in manifest["versions"].items():
        assert version(name) == expected

    types = {"sku": str, "target_weekday": str, "target_month": str}
    dates = ["origin", "target_date", "history_start", "history_end"]
    train = pd.read_csv(root / config["training_examples"], dtype=types, parse_dates=dates)
    valid = pd.read_csv(root / config["validation_features"], dtype=types, parse_dates=dates)
    assert len(train) == 185584 and len(valid) == 28000
    assert sha256(root / config["training_examples"]) == record["signature"]["training_rows_sha256"]
    assert train.target_date.lt("2011-06-06").all()
    assert valid.target_date.ge("2011-06-06").all() and valid.target_date.lt("2011-09-05").all()
    assert train.actual_sales.ge(0).all() and train.actual_sales.eq(0).any()
    assert train.history_end.lt(train.origin).all() and valid.history_end.lt(valid.origin).all()
    assert sorted(valid.origin.dt.strftime("%Y-%m-%d").unique()) == config["validation_origins"]
    pipeline = joblib.load(root / "models/boosting/pipeline.joblib")
    transformer = pipeline.named_steps["categories"]
    estimator = pipeline.named_steps["estimator"]
    assert transformer.n_samples_seen_ == len(train)
    assert estimator.n_iter_ == 200 and not estimator.do_early_stopping_
    for name, expected in MODEL_PARAMETERS.items():
        assert estimator.get_params()[name] == expected
    expected_mask = [name in CATEGORICAL_FEATURES for name in MODEL_FEATURES]
    np.testing.assert_array_equal(estimator.is_categorical_, expected_mask)
    transformed = transformer.transform(valid[MODEL_FEATURES])
    pd.testing.assert_frame_equal(transformed[NUMERIC_FEATURES], valid[NUMERIC_FEATURES])
    categories_before = {name: values.copy() for name, values in transformer.categories_.items()}
    for name in CATEGORICAL_FEATURES:
        assert transformer.categories_[name] == sorted(train[name].unique().tolist())
        assert isinstance(transformed[name].dtype, pd.CategoricalDtype) and not transformed[name].cat.ordered
    validation = pd.read_csv(output / "validation_forecasts.csv.gz", dtype={"sku": str}, parse_dates=["origin", "target_date"])
    training = pd.read_csv(output / "training_in_sample_predictions.csv.gz", dtype={"sku": str}, parse_dates=["origin", "target_date"])
    with threadpool_limits(limits=1):
        validation_reloaded = pipeline.predict(valid[MODEL_FEATURES])
        training_reloaded = pipeline.predict(train[MODEL_FEATURES])
    np.testing.assert_allclose(validation.predicted_sales, validation_reloaded, rtol=1e-14)
    np.testing.assert_allclose(training.predicted_sales, training_reloaded, rtol=1e-14)
    assert np.isfinite(validation_reloaded).all() and (validation_reloaded > 0).all()
    assert np.isfinite(training_reloaded).all() and (training_reloaded > 0).all()
    assert categories_before == transformer.categories_
    assert summary["new_sales_feature_calculations"] == 0
    keys = ["sku", "origin", "target_date", "horizon_day"]
    references = [pd.read_csv(root / "data/ridge/validation_forecasts.csv.gz", dtype={"sku": str}, parse_dates=["origin", "target_date"]),
        pd.read_csv(root / "data/baselines/validation_forecasts.csv.gz", dtype={"sku": str}, parse_dates=["origin", "target_date"])]
    references[1] = references[1].loc[references[1].model.eq("weekday_mean")]
    for reference in references:
        aligned = validation.merge(reference[keys + ["actual_sales"]], on=keys, validate="one_to_one", suffixes=("", "_reference"))
        assert len(aligned) == 28000 and aligned.actual_sales.eq(aligned.actual_sales_reference).all()
    scales = pd.read_csv(root / "data/baselines/history_and_scales.csv", dtype={"sku": str}).set_index("sku").mase_scale
    metrics = pd.read_csv(output / "metrics_by_model.csv").set_index("model")
    for frame in [validation] + references:
        error = frame.predicted_sales - frame.actual_sales
        per_sku = frame.assign(absolute_error=error.abs()).groupby("sku").absolute_error.mean()
        expected = [np.mean(per_sku / scales.reindex(per_sku.index)), error.abs().mean(),
            100 * error.abs().sum() / frame.actual_sales.sum(), error.mean(), 100 * error.sum() / frame.actual_sales.sum()]
        saved = metrics.loc[frame.model.iloc[0], ["macro_mase", "mae", "wape_pct", "mean_bias_units", "bias_pct"]]
        np.testing.assert_allclose(saved.to_numpy(dtype=float), expected, rtol=1e-12)
    performance = pd.read_csv(output / "training_vs_validation.csv").set_index("evaluation")
    error = training.predicted_sales - training.actual_sales
    per_sku = training.assign(absolute_error=error.abs()).groupby("sku").absolute_error.mean()
    expected = [np.mean(per_sku / scales.reindex(per_sku.index)), error.abs().mean(), 100 * error.abs().sum() / training.actual_sales.sum()]
    np.testing.assert_allclose(performance.loc["original-training in-sample", ["macro_mase", "mae", "wape_pct"]].to_numpy(dtype=float), expected, rtol=1e-12)
    counts = {"by_model": 3, "by_sku": 300, "by_origin": 30, "by_horizon_week": 12,
        "by_sku_origin": 3000, "by_sku_origin_week": 12000}
    for name, count in counts.items():
        table = pd.read_csv(output / f"metrics_{name}.csv")
        comparison = pd.read_csv(output / f"comparison_to_weekday_{name}.csv")
        assert len(table) == count and len(comparison) == count // 3
        assert table.wape_pct.isna().eq(table.wape_status.ne("defined")).all()
        assert table.macro_mase.isna().eq(table.mase_status.ne("defined")).all()
    for dimension in ("actual_zero", "target_weekday"):
        saved = pd.read_csv(output / f"diagnostics_by_{dimension}.csv")
        for frame in [validation] + references:
            model = frame.model.iloc[0]
            errors = (frame.predicted_sales - frame.actual_sales).abs()
            if dimension == "actual_zero":
                labels = frame.actual_sales.eq(0)
            else:
                labels = frame.target_date.dt.day_name()
            for label in labels.unique():
                mask = labels.eq(label)
                row = saved.loc[saved.model.eq(model) & saved[dimension].eq(label)].iloc[0]
                assert row.row_count == mask.sum()
                np.testing.assert_allclose(row.prediction_mean, frame.loc[mask, "predicted_sales"].mean(), rtol=1e-12)
                np.testing.assert_allclose(row.absolute_error_units, errors.loc[mask].sum(), rtol=1e-12)
                np.testing.assert_allclose(row.absolute_error_share_pct, 100 * errors.loc[mask].sum() / errors.sum(), rtol=1e-12)
    wins = pd.read_csv(output / "comparison_to_weekday_by_sku.csv")
    delta = wins.candidate_macro_mase - wins.baseline_macro_mase
    expected = np.where(delta.abs() <= 1e-10, "tie", np.where(delta < 0, "win", "loss"))
    np.testing.assert_array_equal(wins.candidate_result, expected)
    assert sha256(root / "models/boosting/pipeline.joblib") == record["pipeline_sha256"]
    print("PASS: prior artifacts unchanged, exact saved features, training-only native categories, one 200-iteration fit, finite positive reload predictions, matched forecasts, training/validation metrics and diagnostic error contributions.")


if __name__ == "__main__":
    main()
