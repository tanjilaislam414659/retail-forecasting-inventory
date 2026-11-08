"""Measured, validation-informed comparison and representative scientific plots."""

import os
from pathlib import Path

import pandas as pd

from retail_forecasting.boosting_experiment import MODEL_NAME


def make_plots(root, history, forecasts, scales, tables):
    os.environ.setdefault("MPLCONFIGDIR", str(root / ".cache/matplotlib"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    output = root / "reports/generated/boosting"
    output.mkdir(parents=True, exist_ok=True)
    colors = {MODEL_NAME: "#009E73", "weekday_mean": "#0072B2", "ridge": "#D55E00"}
    files = []

    def save(fig, name):
        for extension in ("png", "svg"):
            path = output / f"{name}.{extension}"
            fig.savefig(path, dpi=150)
            files.append(path.relative_to(root).as_posix())
        plt.close(fig)

    ranked = scales.sort_values(["training_positive_units", "sku"], ascending=[False, True]).reset_index(drop=True)
    skus = ranked.iloc[[0, 49, 99]].sku.tolist()
    origin = pd.Timestamp("2011-08-08")
    fig, axes = plt.subplots(3, 1, figsize=(12, 10), layout="constrained")
    for axis, sku, rank in zip(axes, skus, [1, 50, 100]):
        past = history.loc[history.sku.eq(sku) & history.date.ge(origin - pd.Timedelta(days=56)) & history.date.lt(origin)]
        current = forecasts.loc[forecasts.sku.eq(sku) & forecasts.origin.eq(origin)]
        actual = current.loc[current.model.eq(MODEL_NAME)]
        axis.plot(past.date, past.sales_units, color="#999999", linewidth=1, label="Observed before origin")
        axis.plot(actual.target_date, actual.actual_sales, color="#111111", linewidth=1.7, label="Validation actuals")
        for model in ("weekday_mean", "ridge", MODEL_NAME):
            points = current.loc[current.model.eq(model)].sort_values("target_date")
            axis.plot(points.target_date, points.predicted_sales, color=colors[model], linestyle="--", linewidth=1.5,
                      label=model.replace("_", " "))
        axis.axvline(origin, color="#555555", linestyle=":", linewidth=1)
        axis.set(title=f"SKU {sku} | original training-volume rank {rank} of 100", ylabel="Positive sales units",
                 xlim=(origin - pd.Timedelta(days=56), origin + pd.Timedelta(days=27)))
        axis.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=mdates.MO, interval=2))
        axis.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
        axis.grid(axis="y", color="#DDDDDD", linewidth=0.5)
        axis.spines[["top", "right"]].set_visible(False)
    axes[0].legend(loc="upper left", ncol=3, fontsize=8)
    axes[-1].set_xlabel("2011 dates; forecasts issued before sales on 8 August")
    fig.suptitle("Validation-informed development: one fixed Poisson boosting candidate", fontsize=14)
    save(fig, "representative_forecasts")

    fig, axes = plt.subplots(1, 2, figsize=(12, 5), layout="constrained")
    for model in ("weekday_mean", "ridge", MODEL_NAME):
        weeks = tables["by_horizon_week"].loc[tables["by_horizon_week"].model.eq(model)].sort_values("horizon_week")
        origins = tables["by_origin"].loc[tables["by_origin"].model.eq(model)].sort_values("origin")
        axes[0].plot(weeks.horizon_week, weeks.macro_mase, marker="o", color=colors[model], label=model.replace("_", " "))
        axes[1].plot(origins.origin, origins.macro_mase, marker="o", color=colors[model], label=model.replace("_", " "))
    axes[0].set(title="Primary error by forecast-horizon week", xlabel="Horizon week", ylabel="Macro MASE", xticks=[1, 2, 3, 4])
    axes[1].set(title="Primary error by forecast origin", xlabel="2011 issue date", ylabel="Macro MASE")
    axes[1].xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=mdates.MO, interval=3))
    axes[1].xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    for axis in axes:
        axis.grid(color="#DDDDDD", linewidth=0.5)
        axis.spines[["top", "right"]].set_visible(False)
    axes[0].legend(fontsize=8)
    save(fig, "validation_comparison")
    return {"skus": skus, "training_volume_ranks": [1, 50, 100], "origin": "2011-08-08", "files": files}


def write_report(root, summary, tables, comparisons):
    s = summary
    overall = s["overall_vs_weekday"]
    winner = overall["candidate_result"] == "win"
    lines = ["# Milestone 5: one fixed pooled Poisson boosting experiment", "",
        "**Validation-informed model development**, following documented Ridge failures. The model class and loss were selected after viewing prior validation results. This is not an untouched final assessment; final test remains unevaluated.",
        f"Primary comparison versus saved weekday mean: **{overall['candidate_result']}**, macro MASE relative change **{overall['macro_mase_relative_change_pct']:+.2f}%**. Exactly one candidate fit; no hyperparameter search or automatic replacement model.",
        "The [fixed specification](boosting-experiment-spec.md) and `configs/boosting.json` were recorded before fitting. All prior results and saved feature rows are hash-verified and unchanged.", "",
        "## Fixed inputs and estimator", "",
        "Same **185,584 original-training examples**, **28,000 validation instances**, 100 SKUs, onset mask, ten origins, daily frequency, 28-day horizon and frozen seven-day MASE scales. Training targets end before 2011-06-06; validation targets end on 2011-09-04. Existing Ridge feature values are loaded verbatim, including zeros and extreme orders.",
        "HistGradientBoostingRegressor uses loss=poisson, learning_rate=0.05, max_iter=200, max_leaf_nodes=15, min_samples_leaf=50, l2_regularization=1.0, early_stopping=False and random_state=42. Other estimator defaults are pinned by sklearn 1.7.2. Unordered SKU/weekday/month categories are learned from training rows only, with native categorical splits; numeric scaling is absent. Targets retain original units and uniform weights.",
        "No Saturday rule, hurdle stage, manual target transformation, weighting, clipping or prediction rounding. Later origins use sales already observed before their issue date through the preserved feature rows, without refitting. The saved model is reused on matching future invocations.",
        "Poisson loss is the training objective, not macro MASE. Its internal log link belongs to the estimator; no manual log target is added. Changing model class and loss together does **not** identify which change causes any gain. [Official estimator documentation](https://scikit-learn.org/1.7/modules/generated/sklearn.ensemble.HistGradientBoostingRegressor.html).", "",
        "## Walk-forward validation results", "",
        "| Model | Macro MASE (primary) | MAE | WAPE | Mean signed bias | Relative bias |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in tables["by_model"].itertuples():
        lines.append(f"| {row.model} | {row.macro_mase:.6f} | {row.mae:.4f} | {row.wape_pct:.2f}% | {row.mean_bias_units:+.4f} | {row.bias_pct:+.2f}% |")
    lines += ["", "Relative changes are 100 × (candidate / weekday mean − 1); negative means lower error.",
        f"Macro MASE: **{overall['macro_mase_relative_change_pct']:+.2f}%**; MAE: **{overall['mae_relative_change_pct']:+.2f}%**; WAPE: **{overall['wape_pct_relative_change_pct']:+.2f}%**. Relative-bias shift: **{overall['bias_difference_pp']:+.2f} percentage points**. Absolute bias magnitude change: **{overall['absolute_bias_relative_change_pct']:+.2f}%**.",
        f"Per-SKU MASE versus weekday mean: **{s['sku_results_vs_weekday']}**. Versus Ridge: **{s['sku_results_vs_ridge']}**. Ties use absolute tolerance 1e-10 only for equality.",
        "The score pools 28,000 forecast instances per model, corresponding to 9,100 distinct SKU/target dates. Overlapping horizons repeat some dates at up to four origins; these errors are dependent. Frozen scales and all undefined-denominator conventions are preserved, without epsilon or dropped SKUs.", "",
        "### Forecast origins", "",
        "| Origin | Model | Macro MASE | MAE | WAPE | Relative bias |", "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for row in tables["by_origin"].sort_values(["origin", "model"]).itertuples():
        lines.append(f"| {row.origin.date()} | {row.model} | {row.macro_mase:.5f} | {row.mae:.3f} | {row.wape_pct:.2f}% | {row.bias_pct:+.2f}% |")
    lines += ["", "### Horizon weeks", "", "| Week | Model | Macro MASE | MAE | WAPE | Relative bias |",
              "| ---: | --- | ---: | ---: | ---: | ---: |"]
    for row in tables["by_horizon_week"].sort_values(["horizon_week", "model"]).itertuples():
        lines.append(f"| {row.horizon_week} | {row.model} | {row.macro_mase:.5f} | {row.mae:.3f} | {row.wape_pct:.2f}% | {row.bias_pct:+.2f}% |")
    lines += ["", "## Zero-sales, positive-sales and Saturday diagnostics", "",
        "These retrospective groups describe errors; no group-specific prediction rule was introduced. Absolute-error shares use each model's total validation absolute error.", "",
        "| Group | Model | Instances | Actual mean | Prediction mean | Absolute-error sum | Share of model error |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in s["zero_positive_diagnostics"]:
        group = "Zero sales" if row["actual_zero"] else "Positive sales"
        lines.append(f"| {group} | {row['model']} | {row['row_count']:,} | {row['actual_mean']:.4f} | {row['prediction_mean']:.4f} | {row['absolute_error_units']:,.2f} | {row['absolute_error_share_pct']:.2f}% |")
    for row in s["saturday_diagnostics"]:
        lines.append(f"| Saturday (subset of zeros) | {row['model']} | {row['row_count']:,} | {row['actual_mean']:.4f} | {row['prediction_mean']:.6f} | {row['absolute_error_units']:,.2f} | {row['absolute_error_share_pct']:.2f}% |")
    lines += ["", "Saturday rows overlap the zero-sales group, so their errors must not be added again. Observed Saturday zeros do not prove closure or availability. The model can learn category interactions, but any causal interpretation of changed errors would require a separate design.", "",
        "## Training versus validation: different evaluation meanings", "",
        "| Evaluation | Rows | Macro MASE | MAE | WAPE | Relative bias |", "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in s["training_vs_validation"]:
        lines.append(f"| {row['evaluation']} | {row['row_count']:,} | {row['macro_mase']:.6f} | {row['mae']:.4f} | {row['wape_pct']:.2f}% | {row['bias_pct']:+.2f}% |")
    lines += ["", "Training is **in-sample**, using the fully fitted estimator on its own original-training examples. It is not held out or rolling-origin model evaluation, and it has different target-date weights/seasonal coverage from validation. A train/validation difference alone is not a causal measure of overfitting.", "",
        "## Numerical behavior and timing", "",
        f"Numerical status: `{s['numerical_status']}`. Fit warnings: `{s['fit_warnings']}`. Prediction warnings: `{s['prediction_warnings']}`. Predictions are not clipped or repaired; nonfinite/nonpositive values cause the experiment to stop.",
        "New sales-feature calculations: **0**, because existing rows are reused. The historical Ridge construction timings were "
        f"{s['historical_ridge_training_feature_wall_seconds']:.3f}s for training and {s['historical_ridge_validation_feature_wall_seconds']:.3f}s for validation; those are prior-run measurements, not time spent recomputing features here.",
        f"Current saved-row loading: **{s['feature_loading_wall_seconds']:.3f}s wall / {s['feature_loading_cpu_seconds']:.3f}s CPU**. Original training-category preparation: **{s['category_preparation_wall_seconds']:.3f}s wall / {s['category_preparation_cpu_seconds']:.3f}s CPU**.",
        f"Single estimator fit: **{s['fit_wall_seconds']:.3f}s wall / {s['fit_cpu_seconds']:.3f}s CPU**. Validation prediction including category conversion: **{s['validation_prediction_time']['wall_seconds']:.3f}s wall / {s['validation_prediction_time']['cpu_seconds']:.3f}s CPU**. Training in-sample prediction: **{s['training_prediction_time']['wall_seconds']:.3f}s wall / {s['training_prediction_time']['cpu_seconds']:.3f}s CPU**. One local thread; no validation refit or early stopping.",
        f"Total command: {s['total_wall_seconds']:.3f}s wall / {s['total_cpu_seconds']:.3f}s CPU. Saved fit reused in this invocation: {s['pipeline_reused']}.", "",
        "## Artifacts, plots and decision", "",
        f"Forecast examples retain original training-volume ranks 1, 50, 100: **{', '.join(s['plots']['skus'])}**, at 2011-08-08. No validation-error-based example selection.",
        "![Representative forecasts](../reports/generated/boosting/representative_forecasts.png)", "",
        "![Origin and horizon comparisons](../reports/generated/boosting/validation_comparison.png)", "",
        "`models/boosting/` contains the model and single-fit record. `data/boosting/` contains config snapshot, training in-sample and validation predictions, all metric/comparison tables, diagnostic sums/shares, category metadata, numerical status, summary and version/hash manifest. All generated artifacts are ignored by Git. [Protocol and reproducible commands](milestone-5.md).", "",
        ("**Recommendation: replace weekday mean as the current development candidate**, because primary validation macro MASE improves. This is provisional selection on a repeatedly consulted validation set, not a final-test result. Retain both saved comparators and review the secondary metrics and individual losses before freezing any final evaluation."
         if winner else
         "**Recommendation: retain weekday mean as the current reference**, because this candidate does not improve primary validation macro MASE. Preserve the negative result; no alternate model was automatically tried."), "",
    ]
    (root / "docs/boosting-comparison.md").write_text("\n".join(lines), encoding="utf-8")
