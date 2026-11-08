"""Plots and an honest, measured comparison for the single Ridge experiment."""

import os
from pathlib import Path

import numpy as np
import pandas as pd


def make_plots(root: Path, history: pd.DataFrame, forecasts: pd.DataFrame, scales: pd.DataFrame,
               tables: dict, comparisons: dict) -> dict:
    os.environ.setdefault("MPLCONFIGDIR", str(root / ".cache/matplotlib"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    directory = root / "reports/generated/ridge"
    directory.mkdir(parents=True, exist_ok=True)
    ranked = scales.sort_values(["training_positive_units", "sku"], ascending=[False, True]).reset_index(drop=True)
    skus = ranked.iloc[[0, 49, 99]].sku.tolist()
    origin = pd.Timestamp("2011-08-08")
    colors = {"ridge": "#D55E00", "weekday_mean": "#0072B2"}
    files = []

    def save(fig, stem):
        for extension in ("png", "svg"):
            path = directory / f"{stem}.{extension}"
            fig.savefig(path, dpi=150)
            files.append(path.relative_to(root).as_posix())
        plt.close(fig)

    fig, axes = plt.subplots(3, 1, figsize=(12, 10), layout="constrained")
    for axis, sku, rank in zip(axes, skus, [1, 50, 100]):
        past = history.loc[history.sku.eq(sku) & history.date.ge(origin - pd.Timedelta(days=56)) & history.date.lt(origin)]
        current = forecasts.loc[forecasts.sku.eq(sku) & forecasts.origin.eq(origin)]
        actual = current.loc[current.model.eq("ridge")]
        axis.plot(past.date, past.sales_units, color="#999999", linewidth=1, label="Observed before origin")
        axis.plot(actual.target_date, actual.actual_sales, color="#111111", linewidth=1.7, label="Validation actuals")
        for model in ("weekday_mean", "ridge"):
            subset = current.loc[current.model.eq(model)].sort_values("target_date")
            axis.plot(subset.target_date, subset.predicted_sales, color=colors[model], linestyle="--",
                      linewidth=1.5, label=model.replace("_", " "))
        axis.axvline(origin, color="#555555", linestyle=":", linewidth=1)
        axis.set(title=f"SKU {sku} | training volume rank {rank} of 100", ylabel="Positive sales units",
                 xlim=(origin - pd.Timedelta(days=56), origin + pd.Timedelta(days=27)))
        axis.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=mdates.MO, interval=2))
        axis.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
        axis.grid(axis="y", color="#DDDDDD", linewidth=0.5)
        axis.spines[["top", "right"]].set_visible(False)
    axes[0].legend(loc="upper left", ncol=2, fontsize=8)
    axes[-1].set_xlabel("2011 dates; all predictions issued before sales on 8 August")
    fig.suptitle("One fixed Ridge versus saved weekday mean", fontsize=14)
    save(fig, "representative_forecasts")

    comparison = comparisons["by_sku"]
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), layout="constrained")
    axes[0].scatter(comparison.baseline_macro_mase, comparison.ridge_macro_mase, color="#0072B2", alpha=0.7, s=25)
    limit = max(comparison.baseline_macro_mase.max(), comparison.ridge_macro_mase.max()) * 1.05
    axes[0].plot([0, limit], [0, limit], color="#777777", linestyle=":")
    axes[0].set(xlabel="Weekday-mean SKU MASE", ylabel="Ridge SKU MASE", xlim=(0, limit), ylim=(0, limit),
                title="100 SKUs; below diagonal favors Ridge")
    for model in ("weekday_mean", "ridge"):
        week = tables["by_horizon_week"].loc[tables["by_horizon_week"].model.eq(model)].sort_values("horizon_week")
        axes[1].plot(week.horizon_week, week.macro_mase, marker="o", color=colors[model], label=model.replace("_", " "))
    axes[1].set(xlabel="Forecast horizon week", ylabel="Macro MASE", xticks=[1, 2, 3, 4],
                title="Validation error by horizon week")
    axes[1].legend()
    for axis in axes:
        axis.grid(color="#DDDDDD", linewidth=0.5)
        axis.spines[["top", "right"]].set_visible(False)
    save(fig, "validation_comparison")
    return {"skus": skus, "training_volume_ranks": [1, 50, 100], "origin": origin.date().isoformat(), "files": files}


def write_report(root: Path, summary: dict, tables: dict, comparisons: dict) -> None:
    s = summary
    overall = comparisons["by_model"].iloc[0]
    outcome = {"loss": "loses", "win": "wins", "tie": "ties", "undefined": "has an undefined comparison"}[s["primary_result"]]
    lines = ["# Milestone 4: one pooled Ridge regression", "",
        f"**Primary outcome: Ridge {outcome} versus saved weekday mean on macro MASE.** This is one predefined experiment, not a hyperparameter search. Final test remains unevaluated.",
        "The [fixed experiment specification](ridge-experiment-spec.md) and `configs/ridge.json` were recorded before fitting. The cohort, onset mask, frequency, splits, frozen scales and validation instances are unchanged.", "",
        "## Training and availability", "",
        f"Training uses **{s['training_rows']:,} supervised rows / {s['training_sku_origin_groups']:,} SKU-origin groups / 100 SKUs**, with {s['training_origins_per_sku_min']}–{s['training_origins_per_sku_max']} Monday origins per SKU. Origins span **{s['training_first_origin']} through {s['training_last_origin']}**; all targets lie in **{s['training_first_target']} through {s['training_last_target']}**, strictly before 2011-06-06.",
        "Each origin has 56 consecutive retained historical days. Every sales feature comes from before the origin, including for horizon days 8–28. Features are SKU, horizon day, target weekday/month, means over 7/28/56 days, population standard deviation and zero share over 28 days, and the target weekday's preceding-eight-occurrence mean.",
        "Numeric StandardScaler and categorical OneHotEncoder are fitted inside the pipeline on training rows only. Ridge uses alpha=1.0, Cholesky solver, intercept, untransformed targets and equal row weights. One actual-data fit is persisted; repeated commands reuse it after signature checks. Later validation origins refresh observed-history features without refitting the estimator or preprocessors.",
        "Ridge optimizes **sum of squared errors + alpha × squared coefficient norm**, while macro MASE, MAE and WAPE use absolute errors. Large wholesale spikes therefore have disproportionate training influence, and shared numeric slopes plus SKU intercepts do not model SKU-specific seasonal interactions.", "",
        "## Validation outcome and tradeoffs", "",
        "Same **28,000** validation instances per model, ten origins from 2011-06-06 through 2011-08-08, and targets through 2011-09-04. Signed bias is prediction minus actual; positive means overforecast. Main Ridge scores use the predefined zero-clipped predictions, without rounding.", "",
        "| Model | Macro MASE (primary) | MAE | Pooled WAPE | Signed bias (units) | Relative bias |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in tables["by_model"].itertuples():
        lines.append(f"| {row.model} | {row.macro_mase:.6f} | {row.mae:.4f} | {row.wape_pct:.2f}% | {row.mean_bias_units:+.4f} | {row.bias_pct:+.2f}% |")
    lines += ["", "Relative changes use 100 × (Ridge / baseline − 1); negative means lower error.",
        f"- Macro MASE: **{overall.macro_mase_relative_change_pct:+.2f}%**.",
        f"- MAE: **{overall.mae_relative_change_pct:+.2f}%**; pooled WAPE: **{overall.wape_pct_relative_change_pct:+.2f}%**.",
        f"- Signed bias change: **{overall.signed_bias_difference_units:+.4f} units**; relative-bias difference: **{overall.bias_difference_pp:+.2f} percentage points**. Absolute bias magnitude changes **{overall.absolute_bias_relative_change_pct:+.2f}%**. A sign change is not interpreted as an error-ratio improvement.",
        f"- SKU primary-metric win/tie/loss counts: **{s['sku_results']}**, out of 100. Ties use absolute tolerance 1e-10 only for numerical equality.",
        f"- Negative predictions clipped: **{s['clipped_predictions']:,}/{s['validation_rows']:,} ({s['clipping_rate_pct']:.2f}%)**. Raw predictions range {s['raw_prediction_min']:.4f} to {s['raw_prediction_max']:.4f} units; raw values and clipping flags are saved.", "",
        "### Horizon-week results", "",
        "| Model | Horizon week | Macro MASE | MAE | WAPE | Signed bias |", "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in tables["by_horizon_week"].itertuples():
        lines.append(f"| {row.model} | {row.horizon_week} | {row.macro_mase:.5f} | {row.mae:.4f} | {row.wape_pct:.2f}% | {row.mean_bias_units:+.4f} |")
    zero = {row["model"]: row for row in s["zero_actual_diagnostics"]}
    saturday = {row["model"]: row for row in s["saturday_diagnostics"]}
    lines += ["", "## Major failures and variation", "",
        f"On **{zero['ridge']['row_count']:,} zero-actual forecast instances**, Ridge predicts **{zero['ridge']['prediction_mean']:.4f} units on average**, versus **{zero['weekday_mean']['prediction_mean']:.4f}** for weekday mean. On **{saturday['ridge']['row_count']:,} Saturday instances**, all actual sales are zero; Ridge still predicts **{saturday['ridge']['prediction_mean']:.4f} units on average**, versus **{saturday['weekday_mean']['prediction_mean']:.4f}** for weekday mean. These are observed validation sales, not proof of closure or inventory availability.",
        "The additive model permits a positive SKU-level intercept even when a particular SKU/weekday should have near-zero observed sales. Shared slopes and global weekday effects cannot represent every SKU-specific pattern. Squared-error training emphasizes spikes rather than equal-SKU absolute error; these are plausible contributors, not a causal diagnosis established by this single experiment.",
        f"Clipping adds **{s['clipping_added_units']:,.2f} units** to the aggregate raw forecasts, moving mean signed bias from **{s['raw_mean_bias_units']:+.4f}** before clipping to **{overall.ridge_mean_bias_units:+.4f}** after clipping. Clipping was fixed before evaluation, and was not changed in response to this outcome.", ""]
    worst = comparisons["by_sku"].sort_values("macro_mase_difference", ascending=False).head(5)
    lines += ["Largest SKU MASE increases (positive is worse):", "",
              "| SKU | Weekday-mean MASE | Ridge MASE | Difference |", "| --- | ---: | ---: | ---: |"]
    for row in worst.itertuples():
        lines.append(f"| {row.sku} | {row.baseline_macro_mase:.5f} | {row.ridge_macro_mase:.5f} | {row.macro_mase_difference:+.5f} |")
    for model in ("ridge", "weekday_mean"):
        subset = tables["by_origin"].loc[tables["by_origin"].model.eq(model)].sort_values("macro_mase")
        lines.append(f"\n{model} origin macro MASE ranges **{subset.iloc[0].macro_mase:.5f}** ({subset.iloc[0].origin.date()}) to **{subset.iloc[-1].macro_mase:.5f}** ({subset.iloc[-1].origin.date()}).")
    lines += [
        "\nThe plots expose missed spikes, persistent level errors and the additive model's limitations. Those are descriptive patterns; they do not identify causal effects of price, stockouts or promotions. Large orders were retained. Good signed bias can conceal offsetting over- and underforecasts.",
        "Overlapping horizons repeat targets at up to four origins; 28,000 scored forecasts correspond to 9,100 distinct SKU/target-date pairs. Metric differences are descriptive and not based on independent forecast samples.",
        f"Undefined WAPE groups: `{s['undefined_wape_groups']}`; undefined MASE groups: `{s['undefined_mase_groups']}`. Existing zero-denominator conventions are preserved, with explicit statuses and no dropped SKUs or epsilon.", "",
        "## Timing and evidence", "",
        f"Original pipeline fit, including training-only preprocessing: **{s['fit_wall_seconds']:.4f} wall / {s['fit_cpu_seconds']:.4f} CPU seconds**. Validation pipeline prediction: **{s['prediction_wall_seconds']:.4f} wall / {s['prediction_cpu_seconds']:.4f} CPU seconds**. One BLAS thread; feature building and report work are excluded from those figures.",
        f"Training feature construction: {s['training_feature_wall_seconds']:.3f} wall seconds; validation features: {s['validation_feature_wall_seconds']:.3f}. Full command: {s['total_wall_seconds']:.3f} wall / {s['total_cpu_seconds']:.3f} CPU seconds. Pipeline reused in this invocation: {s['pipeline_reused']}.",
        "`models/ridge/pipeline.joblib` and its fit record preserve the single fitted pipeline. `data/ridge/` contains its exact specification, train/validation features, raw/clipped forecasts, preprocessing statistics, coefficients, all metric tables, relative comparisons, summary and integrity manifest. Generated data/models/plots are ignored by Git.", "",
        f"Forecast plot selection uses original training-volume ranks 1, 50 and 100: **{', '.join(s['plots']['skus'])}**, at origin 2011-08-08. No validation-error selection.",
        "![Representative forecasts](../reports/generated/ridge/representative_forecasts.png)", "",
        "![Per-SKU and horizon comparison](../reports/generated/ridge/validation_comparison.png)", "",
        "## Reproduce and decision", "",
        "Run `.\\.venv\\Scripts\\python.exe -m retail_forecasting ridge`, then the test suite and `scripts/validate_ridge.py`. See [Milestone 4](milestone-4.md) for contracts and checks. Repeating the command reuses a matching saved fit; it does not refit on validation data.",
        ("Ridge does not improve the primary metric; retain weekday mean as the reference. The next milestone should investigate the documented failure patterns and specify one targeted alternative before fitting it, rather than expanding a model search. Keep final test sealed."
         if s["primary_result"] != "win" else
         "Ridge improves the primary metric in this experiment; assess the secondary-metric and per-SKU tradeoffs before replacing weekday mean. The next milestone should predefine one targeted improvement from the error audit, while keeping final test sealed."), "",
    ]
    (root / "docs/ridge-comparison.md").write_text("\n".join(lines), encoding="utf-8")
