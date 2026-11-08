"""Validation-only baseline experiment; preserve all Milestone 2 artifacts."""

from datetime import datetime, timezone
from importlib.metadata import version
import json
import os
from pathlib import Path
import time

import numpy as np
import pandas as pd

from retail_forecasting.acquisition import sha256
from retail_forecasting.baselines import MODELS, forecast, seasonal_scale
from retail_forecasting.metrics import summarize


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def first_observations(audit: pd.DataFrame, skus: list[str], training_cutoff: str) -> pd.Series:
    """First qualifying positive date, including pre-study rows; training data only."""
    candidates = audit.loc[
        audit.sku.isin(skus) & audit.timestamp.lt(training_cutoff)
        & audit.disposition.isin(["selected_sale", "eligible_unselected_sku", "outside_protocol_window"])
        & audit.quantity.gt(0) & audit.unit_price.gt(0)
        & ~audit.invoice.fillna("").str.upper().str.startswith("C")
        & np.isfinite(audit.quantity) & np.isfinite(audit.unit_price)
        & (audit.quantity % 1).eq(0)
    ]
    result = candidates.groupby("sku").timestamp.min().dt.normalize().reindex(skus)
    require(result.notna().all(), "A selected SKU has no qualifying positive sale before the training cutoff.")
    return result.rename("first_qualifying_sale")


def adjust_history(panel: pd.DataFrame, first: pd.Series, training_cutoff: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Onset adjustment changes the modelling view, never the saved audit panel."""
    before = panel.date.lt(panel.sku.map(first))
    excluded = panel.loc[before]
    require(excluded.sales_units.eq(0).all(), "A positive sale occurs before the first qualifying sale.")
    require(excluded.date.lt(training_cutoff).all(), "Onset adjustment would remove validation dates.")
    starts = first.reset_index()
    starts["excluded_leading_days"] = starts.sku.map(excluded.groupby("sku").size()).fillna(0).astype(int)
    training_positive = panel.loc[panel.date.lt(training_cutoff) & panel.sales_units.gt(0)].groupby("sku").date.min()
    starts["first_positive_in_study"] = starts.sku.map(training_positive)
    starts["zeros_before_first_in_study"] = starts.sku.map(
        panel.loc[panel.date.lt(panel.sku.map(training_positive))].groupby("sku").size()
    ).fillna(0).astype(int)
    modelling = panel.loc[~before].copy()
    starts["modelling_start"] = starts.sku.map(modelling.groupby("sku").date.min())
    return modelling, starts


def training_scales(panel: pd.DataFrame, cutoff: str) -> pd.DataFrame:
    """Freeze the denominator using only the original training interval."""
    training = panel.loc[panel.date.lt(cutoff)]
    records = []
    for sku, group in training.groupby("sku"):
        series = group.set_index("date").sales_units.sort_index()
        scale, pairs = seasonal_scale(series)
        records.append({"sku": sku, "mase_scale": scale, "scale_pairs": pairs,
                        "training_days": len(series), "training_start": series.index.min(),
                        "training_end": series.index.max(), "training_positive_units": int(series.sum())})
    return pd.DataFrame(records)


def issue_forecasts(panel: pd.DataFrame, origins: list[str], validation_start: str, test_start: str) -> pd.DataFrame:
    """Compute origin-issued predictions first, then attach validation actuals."""
    records = []
    for origin_string in origins:
        origin = pd.Timestamp(origin_string)
        targets = pd.date_range(origin, periods=28)
        require(targets.min() >= pd.Timestamp(validation_start) and targets.max() < pd.Timestamp(test_start),
                "A requested forecast target lies outside validation.")
        for sku, group in panel.groupby("sku", sort=True):
            series = group.set_index("date").sales_units
            for model in MODELS:
                predictions = forecast(series, origin, model, horizon=28)
                records.append(pd.DataFrame({"model": model, "sku": sku, "origin": origin,
                    "target_date": predictions.index, "horizon_day": np.arange(1, 29),
                    "predicted_sales": predictions.to_numpy()}))
    result = pd.concat(records, ignore_index=True)
    actuals = panel.loc[panel.date.ge(validation_start) & panel.date.lt(test_start), ["sku", "date", "sales_units"]]
    result = result.merge(actuals.rename(columns={"date": "target_date", "sales_units": "actual_sales"}),
                          on=["sku", "target_date"], how="left", validate="many_to_one")
    require(result.actual_sales.notna().all(), "Missing validation actuals.")
    require(np.isfinite(result.predicted_sales).all() and result.predicted_sales.ge(0).all(), "Invalid forecast.")
    result["horizon_week"] = (result.horizon_day - 1) // 7 + 1
    return result[["model", "sku", "origin", "target_date", "horizon_day", "horizon_week", "actual_sales", "predicted_sales"]]


def plot_examples(root: Path, modelling: pd.DataFrame, predictions: pd.DataFrame, scales: pd.DataFrame) -> dict:
    os.environ.setdefault("MPLCONFIGDIR", str(root / ".cache/matplotlib"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    ranked = scales.sort_values(["training_positive_units", "sku"], ascending=[False, True]).reset_index(drop=True)
    chosen = ranked.iloc[[0, 49, 99]].sku.tolist()
    origin = pd.Timestamp("2011-08-08")
    output = root / "reports/generated/baselines"
    output.mkdir(parents=True, exist_ok=True)
    colors = {"seasonal_naive": "#0072B2", "recent_mean": "#D55E00", "weekday_mean": "#009E73"}
    fig, axes = plt.subplots(3, 1, figsize=(12, 10), layout="constrained")
    for axis, sku, rank in zip(axes, chosen, [1, 50, 100]):
        history = modelling.loc[modelling.sku.eq(sku) & modelling.date.ge(origin - pd.Timedelta(days=56)) & modelling.date.lt(origin)]
        current = predictions.loc[predictions.sku.eq(sku) & predictions.origin.eq(origin)]
        actuals = current.loc[current.model.eq("seasonal_naive")]
        axis.plot(history.date, history.sales_units, color="#888888", linewidth=1.2, label="Observed before origin")
        axis.plot(actuals.target_date, actuals.actual_sales, color="#111111", linewidth=1.7, label="Validation actuals")
        for model in MODELS:
            series = current.loc[current.model.eq(model)]
            axis.plot(series.target_date, series.predicted_sales, color=colors[model], linewidth=1.4,
                      linestyle="--", label=model.replace("_", " "))
        axis.axvline(origin, color="#555555", linewidth=1, linestyle=":")
        axis.set(title=f"SKU {sku} | training volume rank {rank} of 100", ylabel="Positive sales units")
        axis.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=mdates.MO, interval=2))
        axis.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
        axis.grid(axis="y", color="#DDDDDD", linewidth=0.5)
        axis.spines[["top", "right"]].set_visible(False)
    axes[0].legend(loc="upper left", ncol=3, fontsize=8)
    axes[-1].set_xlabel("2011 calendar date; forecast issued 8 August, before that day's sales")
    fig.suptitle("Fixed baselines: examples selected using training volume only", fontsize=14)
    paths = []
    for extension in ("png", "svg"):
        path = output / f"representative_forecasts.{extension}"
        fig.savefig(path, dpi=150)
        paths.append(path.relative_to(root).as_posix())
    plt.close(fig)
    return {"skus": chosen, "training_volume_ranks": [1, 50, 100], "origin": origin.date().isoformat(), "files": paths}


def run_baselines(root: Path) -> dict:
    wall_started, cpu_started = time.perf_counter(), time.process_time()
    prepared = root / "data/processed"
    output = root / "data/baselines"
    output.mkdir(parents=True, exist_ok=True)
    preparation = json.loads((prepared / "preparation-manifest.json").read_text())
    config_path = root / "configs/baselines.json"
    config = json.loads(config_path.read_text())
    protocol = preparation["protocol"]
    origins = pd.date_range("2011-06-06", "2011-08-08", freq="7D").strftime("%Y-%m-%d").tolist()
    require(config["origins"] == origins and config["models"] == list(MODELS), "Fixed origin/model protocol changed.")
    require(config["horizon_days"] == 28 and config["recent_mean_days"] == 28
            and config["weekday_mean_occurrences"] == 8 and config["seasonal_period_days"] == 7,
            "Fixed baseline definitions changed.")
    require(sha256(root / "configs/preparation.json") == preparation["protocol_sha256"], "Preparation rules changed.")
    for name, entry in preparation["outputs"].items():
        require(sha256(prepared / name) == entry["sha256"], f"Prepared input changed: {name}")
    cohort = pd.read_csv(prepared / "sku_selection.csv", dtype={"sku": str})
    require(len(cohort) == 100 and cohort.sku.is_unique, "The original 100-SKU cohort is required.")
    # Discard final-test rows while loading. They never enter model/metric calculations.
    chunks = []
    for chunk in pd.read_csv(prepared / "sales_daily.csv.gz", dtype={"sku": str}, parse_dates=["date"], chunksize=20000):
        chunks.append(chunk.loc[chunk.date.lt(protocol["test_start"])])
    panel = pd.concat(chunks, ignore_index=True)
    require(set(panel.sku) == set(cohort.sku), "Panel/cohort mismatch.")
    audit_chunks = []
    columns = ["sku", "timestamp", "quantity", "unit_price", "invoice", "disposition"]
    for chunk in pd.read_csv(prepared / "row_audit.csv.gz", usecols=columns, dtype={"sku": str, "invoice": str},
                             parse_dates=["timestamp"], chunksize=150000):
        audit_chunks.append(chunk.loc[chunk.sku.isin(cohort.sku) & chunk.timestamp.lt(protocol["validation_start"])])
    first = first_observations(pd.concat(audit_chunks, ignore_index=True), cohort.sku.tolist(), protocol["validation_start"])
    modelling, onset = adjust_history(panel, first, protocol["validation_start"])
    require(onset.excluded_leading_days.sum() == 484 and onset.excluded_leading_days.gt(0).sum() == 10,
            "Leading-zero reconciliation differs from 484 rows / 10 SKUs.")
    special = onset.loc[onset.sku.eq("21166")].iloc[0]
    require(special.excluded_leading_days == 0 and special.zeros_before_first_in_study == 1,
            "SKU 21166's pre-study observation distinction was lost.")
    scales = training_scales(modelling, protocol["validation_start"])
    onset = onset.merge(scales, on="sku", validate="one_to_one")
    onset.to_csv(output / "history_and_scales.csv", index=False)
    modelling.to_csv(output / "modelling_history.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})
    predictions = issue_forecasts(modelling, config["origins"], protocol["validation_start"], protocol["test_start"])
    require(len(predictions) == 84000 and not predictions.duplicated(["model", "sku", "origin", "target_date"]).any(),
            "Incorrect forecast count or repeated forecast key.")
    predictions.to_csv(output / "validation_forecasts.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})
    dimensions = {
        "by_model": ["model"], "by_sku": ["model", "sku"], "by_origin": ["model", "origin"],
        "by_horizon_week": ["model", "horizon_week"],
        "by_sku_origin": ["model", "sku", "origin"],
        "by_sku_origin_week": ["model", "sku", "origin", "horizon_week"],
    }
    tables = {}
    for name, keys in dimensions.items():
        tables[name] = summarize(predictions, scales, keys)
        tables[name].to_csv(output / f"metrics_{name}.csv", index=False)
    plots = plot_examples(root, modelling, predictions, scales)
    summary = {
        "onset_excluded_rows": int(onset.excluded_leading_days.sum()),
        "onset_affected_skus": int(onset.excluded_leading_days.gt(0).sum()),
        "first_study_sale_leading_zeros": int(onset.zeros_before_first_in_study.sum()),
        "sku_21166": json.loads(onset.loc[onset.sku.eq("21166")].to_json(orient="records", date_format="iso"))[0],
        "original_training_rows": int(panel.split.eq("train").sum()),
        "modelling_training_rows": int(modelling.split.eq("train").sum()),
        "validation_rows": int(modelling.split.eq("validation").sum()),
        "zero_training_scales": int(scales.mase_scale.eq(0).sum()),
        "training_scale_min": float(scales.mase_scale.min()), "training_scale_max": float(scales.mase_scale.max()),
        "forecast_rows": len(predictions), "forecasts_per_model": 28000,
        "unique_validation_sku_dates": int(predictions[["sku", "target_date"]].drop_duplicates().shape[0]),
        "first_target": predictions.target_date.min().date().isoformat(),
        "last_target": predictions.target_date.max().date().isoformat(),
        "model_metrics": json.loads(tables["by_model"].to_json(orient="records")),
        "undefined_wape_groups": {name: int(table.wape_pct.isna().sum()) for name, table in tables.items()},
        "undefined_mase_groups": {name: int(table.macro_mase.isna().sum()) for name, table in tables.items()},
        "plots": plots,
        "wall_seconds": round(time.perf_counter() - wall_started, 3),
        "cpu_seconds": round(time.process_time() - cpu_started, 3),
    }
    write_json(output / "summary.json", summary)
    for name, entry in preparation["outputs"].items():
        require(sha256(prepared / name) == entry["sha256"], f"Prepared data modified during evaluation: {name}")
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(), "evaluation": "validation only",
        "protocol": config, "config_sha256": sha256(config_path),
        "preparation_manifest_sha256": sha256(prepared / "preparation-manifest.json"),
        "code_sha256": {name: sha256(Path(__file__).with_name(name)) for name in ("baselines.py", "metrics.py", "baseline_validation.py")},
        "versions": {name: version(name) for name in ("retail-forecasting", "numpy", "pandas", "matplotlib")},
        "outputs": {p.relative_to(root).as_posix(): {"sha256": sha256(p), "bytes": p.stat().st_size}
                    for p in sorted(output.iterdir()) if p.is_file() and p.name != "manifest.json"},
        "plots": {path: sha256(root / path) for path in plots["files"]},
    }
    write_json(output / "manifest.json", manifest)
    write_report(root, summary, tables, onset)
    print(tables["by_model"][["model", "mae", "wape_pct", "mean_bias_units", "bias_pct", "macro_mase"]].to_string(index=False), flush=True)
    print(f"Saved {len(predictions):,} validation forecasts; excluded 484 leading modelling rows; no final-test evaluation.", flush=True)
    return summary


def write_report(root: Path, summary: dict, tables: dict, onset: pd.DataFrame) -> None:
    lines = ["# Milestone 3: fixed baseline validation", "",
        "Generated from the preserved 100-SKU daily panel. No final-test evaluation, window tuning or complex ML.", "",
        "## History adjustment", "",
        "The first qualifying positive sale is determined from pre-2011-06-06 audit records, including records before the study starts. Modelling history begins at the later of that date and 2009-12-07. The original audit panel is unchanged; no earlier pre-study sales are appended to the original training interval.",
        "Removed **484 leading zero-filled training rows across 10 SKUs** in a separate modelling view: **54,116 training rows** remain, plus **9,100 validation rows**. Scale pairs require both dates to be on/after that SKU's modelling start.",
        f"SKU 21166 was first observed on **{onset.loc[onset.sku.eq('21166'), 'first_qualifying_sale'].iloc[0].date()}**, before study start. Its one zero before its first in-window sale is retained. Using in-window first sales alone would remove 485 rows across 11 SKUs; that is not the modelling rule.",
        "This onset rule is a modelling assumption based on the first qualifying recorded sale, not proof of listing or availability. Other zeros and large orders remain unchanged.", "",
        "## Fixed definitions and walk-forward validation", "",
        "- Seasonal naive repeats the last available seven calendar days four times.",
        "- Recent mean uses the previous 28 calendar days, including observed zero-sales days.",
        "- Weekday mean uses the eight prior occurrences of each target weekday (56-day lookback). Its four forecast weeks repeat the same weekday means.",
        "Ten Monday origins run weekly from **2011-06-06 through 2011-08-08**. Each origin issues all 28 daily predictions before observing that day's sales. Later origins may use validation sales already observed before their own issue date; no method consumes actuals from inside its forecast horizon. Definitions never change.",
        "All targets lie in **2011-06-06 through 2011-09-04**. There are **84,000 forecast rows** (28,000 per model), but only **9,100 distinct SKU/target-date pairs**. Overlapping horizons score some dates up to four times at different origins; metrics weight issued forecasts and are not independent daily samples.", "",
        "## Metrics", "",
        "MAE is mean absolute error in units per SKU/day forecast. Pooled WAPE is 100 x sum absolute error / sum actual units. Signed bias is mean(prediction - actual), positive for overforecasting; relative bias uses the same actual-unit denominator as WAPE.",
        "For each SKU, the MASE scale is mean absolute lag-7 difference over adjusted **original training dates only**. It is frozen before validation, never updated at later origins. Per-SKU MASE is validation MAE / that scale; macro MASE averages all 100 SKU values equally. A value below one means errors are below the historical seasonal-naive scale, not necessarily below the validation seasonal-naive baseline.",
        "Zero actual totals make WAPE/relative bias undefined; zero training scales make SKU MASE undefined. CSVs retain the rows with empty metric values and explicit status/count columns. A macro MASE containing any undefined SKU is itself undefined; no epsilon and no silent product removal.",
        f"Actual zero training scales: **{summary['zero_training_scales']}**. Undefined WAPE groups by output: `{summary['undefined_wape_groups']}`. Undefined MASE groups: `{summary['undefined_mase_groups']}`.",
        "Metric definitions follow the [primary forecasting textbook's scaled-error discussion](https://otexts.com/fpp3/toolbox.html#scaled-errors); the denominator/aggregation conventions above specify this experiment.", "",
        "| Model | MAE (units) | Pooled WAPE | Mean signed bias (units) | Relative bias | Macro MASE |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in tables["by_model"].itertuples():
        lines.append(f"| {row.model} | {row.mae:.4f} | {row.wape_pct:.2f}% | {row.mean_bias_units:+.4f} | {row.bias_pct:+.2f}% | {row.macro_mase:.4f} |")
    lines += ["", "### By forecast-horizon week", "",
        "| Model | Week | MAE | WAPE | Signed bias | Macro MASE |", "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for row in tables["by_horizon_week"].itertuples():
        lines.append(f"| {row.model} | {row.horizon_week} | {row.mae:.4f} | {row.wape_pct:.2f}% | {row.mean_bias_units:+.4f} | {row.macro_mase:.4f} |")
    winners = tables["by_sku"].sort_values(["sku", "mae", "model"]).drop_duplicates("sku").model.value_counts().to_dict()
    lines += ["", "## Measured variation and failure patterns", "",
        f"Lowest per-SKU MAE counts (ties broken by model name): `{winners}`. The pooled winner need not win every SKU."]
    for model in MODELS:
        origin_table = tables["by_origin"].loc[tables["by_origin"].model.eq(model)].sort_values("wape_pct")
        worst = tables["by_sku"].loc[tables["by_sku"].model.eq(model)].sort_values("absolute_error_units", ascending=False).iloc[0]
        lines.append(f"- {model}: origin WAPE ranges from {origin_table.iloc[0].wape_pct:.2f}% ({origin_table.iloc[0].origin.date()}) to {origin_table.iloc[-1].wape_pct:.2f}% ({origin_table.iloc[-1].origin.date()}). Largest aggregate absolute-error SKU: {worst.sku}, {worst.absolute_error_units:,.1f} units of absolute error.")
    lines += [
        "These comparisons are descriptive; overlapping horizons and SKU dependence preclude treating 28,000 forecasts as independent evidence. The baselines cannot anticipate unobserved promotions, wholesale spikes or stock availability. Plots below show selected examples without choosing them by validation error.", "",
        "## Representative plots and saved evidence", "",
        f"Plot SKUs are training-volume ranks **1, 50, 100**, ties by SKU ascending: **{', '.join(summary['plots']['skus'])}**. All use the last prescribed origin, **2011-08-08**, and show 56 preceding days plus the 28-day forecast. The selection rule was fixed in `configs/baselines.json` before evaluation.",
        "![Representative validation forecasts](../reports/generated/baselines/representative_forecasts.png)", "",
        "`data/baselines/` contains forecasts with model/SKU/origin/target/horizon/actual/prediction, the separate modelling view, first-sale reconciliation and frozen scales, metrics by model/SKU/origin/horizon week and joint combinations, a summary, and a hash/version manifest. All generated data and plots are ignored by Git.",
        f"This run took {summary['wall_seconds']:.3f} wall seconds / {summary['cpu_seconds']:.3f} CPU seconds, including data loading, reports and plots; it is not a model-only timing benchmark.", "",
        "## Reproduce and next milestone", "",
        "Run `.\\.venv\\Scripts\\python.exe -m retail_forecasting baselines`, then `.\\.venv\\Scripts\\python.exe -m unittest discover -s tests -v` and `.\\.venv\\Scripts\\python.exe scripts\\validate_baselines.py`. Detailed protocol: [Milestone 3](milestone-3.md).",
        "Next proposed modelling milestone: one modest pooled, regularized lag/calendar model using origin-available features and the same validation protocol. Compare with the strongest fixed baseline, report SKU/horizon failures and runtime, and keep final test sealed until the modelling plan is frozen. No API/dashboard or inventory-savings claims yet.", "",
    ]
    (root / "docs/baseline-comparison.md").write_text("\n".join(lines), encoding="utf-8")
