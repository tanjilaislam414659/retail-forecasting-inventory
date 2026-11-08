"""Independently check saved baseline forecasts, metrics, and preserved inputs."""

from importlib.metadata import version
import json
from pathlib import Path

import numpy as np
import pandas as pd

from retail_forecasting.acquisition import sha256


def main():
    root = Path(__file__).resolve().parents[1]
    directory = root / "data/baselines"
    prepared = root / "data/processed"
    manifest = json.loads((directory / "manifest.json").read_text())
    prep = json.loads((prepared / "preparation-manifest.json").read_text())
    config = manifest["protocol"]
    cutoff = pd.Timestamp(prep["protocol"]["validation_start"])
    test_start = pd.Timestamp(prep["protocol"]["test_start"])
    assert sha256(prepared / "preparation-manifest.json") == manifest["preparation_manifest_sha256"]
    assert sha256(root / "configs/preparation.json") == prep["protocol_sha256"]
    assert sha256(root / "configs/baselines.json") == manifest["config_sha256"]
    for name, entry in prep["outputs"].items():
        assert sha256(prepared / name) == entry["sha256"], f"Changed Milestone 2 file: {name}"
    for path, entry in manifest["outputs"].items():
        assert sha256(root / path) == entry["sha256"], f"Changed baseline output: {path}"
    for path, digest in manifest["plots"].items():
        assert sha256(root / path) == digest
    for name, digest in manifest["code_sha256"].items():
        assert sha256(root / "src/retail_forecasting" / name) == digest
    for name, expected in manifest["versions"].items():
        assert version(name) == expected

    # Load only pre-test panel rows into the calculations below.
    panel_parts = []
    for chunk in pd.read_csv(prepared / "sales_daily.csv.gz", dtype={"sku": str}, parse_dates=["date"], chunksize=20000):
        panel_parts.append(chunk.loc[chunk.date.lt(test_start)])
    panel = pd.concat(panel_parts, ignore_index=True)
    history = pd.read_csv(directory / "modelling_history.csv.gz", dtype={"sku": str}, parse_dates=["date"])
    onset = pd.read_csv(directory / "history_and_scales.csv", dtype={"sku": str},
                        parse_dates=["first_qualifying_sale", "first_positive_in_study", "modelling_start", "training_start", "training_end"])
    cohort = pd.read_csv(prepared / "sku_selection.csv", dtype={"sku": str})
    assert set(history.sku) == set(onset.sku) == set(cohort.sku) and len(onset) == 100
    assert history.date.lt(test_start).all()
    audit_parts = []
    for chunk in pd.read_csv(prepared / "row_audit.csv.gz", dtype={"sku": str, "invoice": str},
        usecols=["sku", "timestamp", "quantity", "unit_price", "invoice", "disposition"],
        parse_dates=["timestamp"], chunksize=150000):
        valid = (chunk.sku.isin(cohort.sku) & chunk.timestamp.lt(cutoff)
            & chunk.disposition.isin(["selected_sale", "eligible_unselected_sku", "outside_protocol_window"])
            & chunk.quantity.gt(0) & chunk.unit_price.gt(0)
            & np.isfinite(chunk.quantity) & np.isfinite(chunk.unit_price) & (chunk.quantity % 1).eq(0)
            & ~chunk.invoice.fillna("").str.upper().str.startswith("C"))
        audit_parts.append(chunk.loc[valid, ["sku", "timestamp"]])
    first = pd.concat(audit_parts).groupby("sku").timestamp.min().dt.normalize()
    assert onset.set_index("sku").first_qualifying_sale.eq(first.reindex(onset.sku)).all()
    excluded_mask = panel.date.lt(panel.sku.map(first))
    assert excluded_mask.sum() == 484 and panel.loc[excluded_mask, "sku"].nunique() == 10
    assert panel.loc[excluded_mask, "sales_units"].eq(0).all()
    pd.testing.assert_frame_equal(history, panel.loc[~excluded_mask].reset_index(drop=True))
    assert history.split.eq("train").sum() == 54116
    assert history.split.eq("validation").sum() == 9100
    special = onset.set_index("sku").loc["21166"]
    assert special.first_qualifying_sale == pd.Timestamp("2009-12-01")
    assert special.first_positive_in_study == pd.Timestamp("2009-12-08")
    assert special.excluded_leading_days == 0 and special.zeros_before_first_in_study == 1

    scales = {}
    for sku, group in history.loc[history.date.lt(cutoff)].groupby("sku"):
        ordered = group.sort_values("date")
        values = ordered.sales_units.to_numpy(dtype=float)
        expected = np.mean(np.abs(values[7:] - values[:-7]))
        saved = onset.set_index("sku").loc[sku]
        np.testing.assert_allclose(expected, saved.mase_scale, rtol=1e-12)
        assert saved.scale_pairs == len(values) - 7 and saved.training_end == pd.Timestamp("2011-06-05")
        scales[sku] = expected

    forecasts = pd.read_csv(directory / "validation_forecasts.csv.gz", dtype={"sku": str}, parse_dates=["origin", "target_date"])
    assert len(forecasts) == 84000
    assert not forecasts.duplicated(["model", "sku", "origin", "target_date"]).any()
    assert set(forecasts.model) == set(config["models"])
    assert sorted(forecasts.origin.dt.strftime("%Y-%m-%d").unique()) == config["origins"]
    assert forecasts.groupby(["model", "sku", "origin"]).size().eq(28).all()
    assert (forecasts.target_date - forecasts.origin).dt.days.eq(forecasts.horizon_day - 1).all()
    assert forecasts.horizon_week.eq((forecasts.horizon_day - 1) // 7 + 1).all()
    assert forecasts.target_date.ge(cutoff).all() and forecasts.target_date.lt(test_start).all()
    assert forecasts[["sku", "target_date"]].drop_duplicates().shape[0] == 9100
    history_lookup = {sku: group.set_index("date").sales_units for sku, group in history.groupby("sku")}
    for (model, sku, origin), group in forecasts.groupby(["model", "sku", "origin"]):
        series = history_lookup[sku]
        ordered = group.sort_values("horizon_day")
        recent = series.reindex(pd.date_range(origin - pd.Timedelta(days=56), periods=56))
        assert recent.notna().all()
        if model == "seasonal_naive":
            expected = np.tile(recent.iloc[-7:].to_numpy(), 4)
        elif model == "recent_mean":
            expected = np.full(28, recent.iloc[-28:].sum() / 28)
        else:
            expected = [recent.loc[recent.index.dayofweek == day.dayofweek].sum() / 8 for day in ordered.target_date]
        np.testing.assert_allclose(ordered.predicted_sales, expected, rtol=1e-12, atol=1e-12)
        np.testing.assert_array_equal(ordered.actual_sales, series.reindex(ordered.target_date))

    saved_metrics = pd.read_csv(directory / "metrics_by_model.csv").set_index("model")
    for model, group in forecasts.groupby("model"):
        error = group.predicted_sales - group.actual_sales
        actual = group.actual_sales.sum()
        per_sku = group.assign(error=error.abs()).groupby("sku").error.mean()
        mase_values = [per_sku.loc[sku] / scales[sku] if scales[sku] != 0 else np.nan for sku in per_sku.index]
        expected_mase = np.nan if any(pd.isna(value) for value in mase_values) else np.mean(mase_values)
        saved = saved_metrics.loc[model]
        np.testing.assert_allclose([saved.mae, saved.wape_pct, saved.mean_bias_units, saved.bias_pct, saved.macro_mase],
            [error.abs().mean(), 100 * error.abs().sum() / actual if actual else np.nan,
             error.mean(), 100 * error.sum() / actual if actual else np.nan, expected_mase], rtol=1e-12)
        assert saved.sku_count == 100 and saved.row_count == 28000
    counts = {"by_model": 3, "by_sku": 300, "by_origin": 30, "by_horizon_week": 12,
              "by_sku_origin": 3000, "by_sku_origin_week": 12000}
    for name, count in counts.items():
        table = pd.read_csv(directory / f"metrics_{name}.csv", dtype={"sku": str})
        assert len(table) == count
        assert table.wape_pct.isna().eq(table.wape_status.ne("defined")).all()
        assert table.macro_mase.isna().eq(table.mase_status.ne("defined")).all()
    print("PASS: preserved inputs, 484-row onset adjustment, SKU 21166, frozen training scales, all 84,000 predictions/actuals, validation dates and independent metric reconciliation.")


if __name__ == "__main__":
    main()
