"""Predefined final report and training-selected scientific plots."""

import os

import numpy as np
import pandas as pd

from retail_forecasting.final_evaluation import OUTPUT, PLOTS, REPORT, diagnostics, require


def table(frame, columns, digits=4):
    rows = ["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
    for values in frame[columns].itertuples(index=False, name=None):
        rows.append("| " + " | ".join(f"{v:.{digits}f}" if isinstance(v, (float, np.floating)) else str(v) for v in values) + " |")
    return "\n".join(rows)


def make_plots(root, history, points, intervals, scales, metrics, config):
    os.environ.setdefault("MPLCONFIGDIR", str(root / ".cache/matplotlib"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    directory = root / PLOTS
    directory.mkdir(parents=True, exist_ok=False)
    ranked = scales.sort_values(["training_positive_units", "sku"], ascending=[False, True]).reset_index(drop=True)
    ranks = config["plot_rule"]["training_volume_ranks"]
    skus = ranked.iloc[[rank - 1 for rank in ranks]].sku.tolist()
    origin = pd.Timestamp(config["plot_rule"]["origin"])
    files = []

    def save(fig, stem):
        for extension in ("png", "svg"):
            path = directory / f"{stem}.{extension}"
            with path.open("xb") as stream:
                fig.savefig(stream, format=extension, dpi=150)
            files.append(path.relative_to(root).as_posix())
        plt.close(fig)

    fig, axes = plt.subplots(3, 1, figsize=(12, 10), layout="constrained")
    for axis, sku, rank in zip(axes, skus, ranks):
        past = history.loc[history.sku.eq(sku) & history.date.ge(origin - pd.Timedelta(days=28)) & history.date.lt(origin)]
        subset = intervals.loc[intervals.sku.eq(sku) & intervals.origin.eq(origin)].sort_values("target_date")
        wide, narrow = subset.loc[subset.level.eq(95)], subset.loc[subset.level.eq(80)]
        reference = points.loc[points.model.eq("seasonal_naive") & points.sku.eq(sku) & points.origin.eq(origin)].sort_values("target_date")
        axis.plot(past.date, past.sales_units, color="#888888", linewidth=1, label="Observed before origin")
        axis.fill_between(wide.target_date, wide.lower, wide.upper, color="#0072B2", alpha=.15, label="95% experimental daily interval")
        axis.fill_between(narrow.target_date, narrow.lower, narrow.upper, color="#0072B2", alpha=.3, label="80% experimental daily interval")
        axis.plot(wide.target_date, wide.actual_sales, color="#111111", linewidth=1.5, label="Final actuals")
        axis.plot(wide.target_date, wide.point_prediction, color="#D55E00", linestyle="--", label="Selected weekday mean")
        axis.plot(reference.target_date, reference.predicted_sales, color="#009E73", linestyle=":", label="Fixed seasonal-naive reference")
        axis.axvline(origin, color="#555555", linestyle=":", linewidth=1)
        axis.set(title=f"SKU {sku} | original training-volume rank {rank} of 100", ylabel="Positive sales units")
        axis.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=mdates.MO, interval=2))
        axis.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
        axis.grid(axis="y", color="#DDDDDD", linewidth=.5)
        axis.spines[["top", "right"]].set_visible(False)
    axes[0].legend(loc="upper left", ncol=2, fontsize=8)
    axes[-1].set_xlabel("2011 dates; issued before 7 November sales; daily bands are not total-sales bounds")
    fig.suptitle("Frozen release: final held-out forecasts", fontsize=14)
    save(fig, "representative_forecasts")

    fig, axes = plt.subplots(1, 2, figsize=(12, 5), layout="constrained")
    weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    for level, color in ((80, "#0072B2"), (95, "#D55E00")):
        week = metrics["by_horizon_week"].loc[metrics["by_horizon_week"].level.eq(level)].sort_values("horizon_week")
        day = metrics["by_target_weekday"].loc[metrics["by_target_weekday"].level.eq(level)].set_index("target_weekday").reindex(weekdays)
        axes[0].plot(week.horizon_week, week.coverage_pct, marker="o", color=color, label=f"{level}% nominal")
        axes[1].plot(range(7), day.coverage_pct, marker="o", color=color)
        for axis in axes:
            axis.axhline(level, color=color, linestyle=":", alpha=.7)
    axes[0].set(title="Final coverage by horizon week", xlabel="Horizon week", xticks=[1, 2, 3, 4])
    axes[1].set(title="Final coverage by target weekday", xlabel="Weekday", xticks=range(7), xticklabels=[d[:3] for d in weekdays])
    for axis in axes:
        axis.set(ylabel="Empirical coverage (%)", ylim=(0, 101))
        axis.grid(color="#DDDDDD", linewidth=.5)
        axis.spines[["top", "right"]].set_visible(False)
    axes[0].legend()
    save(fig, "coverage_diagnostics")
    return {"skus": skus, "training_volume_ranks": ranks, "origin": origin.date().isoformat(), "files": files}


def write_report(root, summary, point_metrics, interval_metrics, validation_points, validation_intervals):
    s = summary
    columns = ["model", "macro_mase", "mae", "wape_pct", "mean_bias_units", "bias_pct"]
    interval_columns = ["level", "coverage_pct", "mean_width", "mean_interval_score", "miss_below_count", "miss_above_count", "missing_interval_count", "zero_width_count"]
    lines = ["# Milestone 7: one frozen final held-out evaluation", "",
        "The first-release point forecaster remains **eight-week weekday mean**. Seasonal naive is a fixed reference, not a model-selection candidate. Unchanged original-training residual intervals are **experimental empirical historical-error daily prediction intervals**. No tuning, model switch, recalibration or preparation change followed final outcomes.", "",
        "[Frozen protocol](proposed-final-evaluation.md), `configs/final-evaluation.json`, and `data/final_evaluation/freeze.json` identify the pre-unblinding specification, source, inputs and calibration by SHA-256. Local source is uncommitted; no commit identity is claimed.", "",
        "## Validation development evidence — saved earlier results", "",
        table(validation_points, columns), "", table(validation_intervals, interval_columns), "",
        "Validation informed point-model development and selection; these values are not a fresh held-out assessment.", "",
        "## Final held-out evidence — one evaluation", "",
        "All 100 SKUs; ten Monday origins **2011-09-05 through 2011-11-07**, each forecasting origin through +27 days. Targets end **2011-12-04**, before 2011-12-05. Each point method has **28,000 origin-specific instances**, representing **9,100 unique SKU/target-date pairs**. The two interval levels produce 56,000 rows, not additional physical sales.", "",
        table(point_metrics["by_model"], columns), "", table(interval_metrics["overall"], interval_columns), "",
        "Signed bias is prediction minus actual. Relative bias and WAPE use pooled actual units. Macro MASE gives each SKU equal weight and uses its unchanged original-training lag-seven scale. Zero denominators are explicit undefined statuses, with no epsilon or silently omitted products. Coverage includes endpoints; interval score penalizes both width and missed-bound distance.", "",
        "### Selected method versus fixed reference", "",
        table(pd.DataFrame(s["reference_comparison"]), ["metric", "selected", "reference", "selected_minus_reference", "relative_change_pct"]), "",
        f"Per-SKU MASE descriptive wins/ties/losses: **{s['sku_mase_wins_ties_losses']}** (absolute tie tolerance 1e-10). Negative error-metric changes indicate lower error; relative changes of signed bias are not an improvement measure. The release choice remains frozen regardless of this comparison.", "",
        "### Point results by horizon week", "",
        table(point_metrics["by_horizon_week"], ["model", "horizon_week", "macro_mase", "mae", "wape_pct", "mean_bias_units", "bias_pct"]), "",
        "### Point results by origin", "",
        table(point_metrics["by_origin"], ["model", "origin", "macro_mase", "mae", "wape_pct", "bias_pct"]), "",
        "### Interval results by horizon week", "",
        table(interval_metrics["by_horizon_week"], ["level", "horizon_week"] + interval_columns[1:]), "",
        "### Interval results by target weekday", "",
        table(interval_metrics["by_target_weekday"], ["level", "target_weekday"] + interval_columns[1:]), "",
        "## Failures and distribution differences", ""]
    selected = point_metrics["by_model"].set_index("model").loc["weekday_mean"]
    validation = validation_points.set_index("model").loc["weekday_mean"]
    for metric in ("macro_mase", "mae", "wape_pct"):
        change = 100 * (selected[metric] / validation[metric] - 1) if validation[metric] else np.nan
        lines.append(f"Selected {metric}: validation {validation[metric]:.6f}, final {selected[metric]:.6f}; descriptive change {change:+.2f}%.")
    lines += ["", "These periods differ in season and realized sales. Differences are descriptive, not causal or statistically significant findings. Forecast instances share targets across origins and overlapping histories; their row count is not an independent sample size.", "",
        "### Predefined point diagnostics", "",
        table(pd.read_csv(root / OUTPUT / "point_diagnostics.csv"), ["model", "subset", "row_count", "actual_mean", "prediction_mean", "absolute_error_units", "absolute_error_contribution_pct"]), "",
        "Zero/positive subsets partition rows; Saturday overlaps those subsets. Error contributions therefore must not all be summed together.", ""]
    sku_metrics = interval_metrics["by_sku"]
    for level in (80, 95):
        group = sku_metrics.loc[sku_metrics.level.eq(level)]
        worst = group.sort_values(["coverage_pct", "sku"]).head(5)
        lines += [f"### Per-SKU {level}% interval failures", "",
            f"Below nominal: **{int(group.coverage_pct.lt(level).sum())}/100 SKUs**; minimum {group.coverage_pct.min():.4f}%, median {group.coverage_pct.median():.4f}%.", "",
            table(worst, ["sku", "coverage_pct", "mean_width", "mean_interval_score", "miss_below_count", "miss_above_count"]), ""]
    worst_points = point_metrics["by_sku"].loc[point_metrics["by_sku"].model.eq("weekday_mean")].sort_values(["macro_mase", "sku"], ascending=[False, True]).head(5)
    lines += ["### Largest selected-method per-SKU MASE (diagnostic table, not plot selection)", "",
        table(worst_points, ["sku", "macro_mase", "mae", "actual_units", "bias_pct"]), "",
        "The saved forecasts retain every zero and extreme order. These descriptive failures do not justify removing observations, changing weekdays or adjusting intervals after evaluation.", "",
        "## Integrity, calibration and execution", "",
        f"Calibration unchanged: {s['calibration_unchanged']}. Missing calibration group/level rows: {s['missing_calibration_group_level_rows']}. Nonfinite point predictions: {s['nonfinite_point_predictions']}. Implementation defects during this run: {s['implementation_defects']}.", "",
        "Each origin receives only strictly prior sales. Already observed validation and earlier final-period sales refresh historical inputs; no future horizon actuals enter issued forecasts. Unscored point forecasts and intervals are saved and hashed before actuals are joined. Quantiles were never refitted; all calibration targets predate 2011-06-06.", "",
        "Calibration retains 185,584 residual instances, 48,496 unique SKU/target dates and 6,628 SKU/origin groups. Per SKU/horizon-week group: 371–469 residuals and unique dates, 53–67 origins. Target dates repeat across horizon-week groups; residuals are not independent. Group counts and quantiles remain in the original calibration artifacts.", "",
        f"Loading {s['load_seconds']:.3f}s; point/interval issuance and saving {s['prediction_and_interval_seconds']:.3f}s; scoring/saving {s['scoring_seconds']:.3f}s; full evaluation before report/manifest {s['total_wall_seconds']:.3f}s. These are local CPU wall times, not general benchmarks.", "",
        "Integrity/leakage checks and outcomes are recorded in the companion verification record. The results manifest hashes every artifact, report and plot. The command refuses overwrite; repeats verify hashes and display saved metrics, without forecasting/scoring again. A started incomplete run is refused. Any post-unblinding correction must preserve originals and receive an explicit defect log; no correction is present in this release.", "",
        "## Representative plots", "",
        f"Predefined original-training volume ranks 1/50/100: **{', '.join(s['plots']['skus'])}**, fixed origin {s['plots']['origin']}. Final error did not select these examples.", "",
        "![Representative final forecasts](../reports/generated/final_evaluation/representative_forecasts.png)", "",
        "![Final interval coverage](../reports/generated/final_evaluation/coverage_diagnostics.png)", "",
        "## What the first release supports", "",
        "A reproducible offline reference for 28-day daily observed-positive-sales forecasts over this bounded historical 100-SKU cohort, with explicit errors, frozen scales, auditable history policy and experimental daily uncertainty bands. It supports honest portfolio demonstrations and a foundation for separately specified inventory scenarios.", "",
        "It does not establish uncensored demand, stock availability, production readiness, causal effects, future-season accuracy, calibrated per-SKU/weekday coverage, or inventory/service/cost benefits. It has no API/dashboard. These intervals are not confidence intervals and have no conformal/finite-sample guarantee. Do not sum daily bounds as a calibrated 28-day total interval; joint/aggregate uncertainty requires another method.", "",
        "The final period is now consumed as evaluation evidence. Future point/uncertainty changes constitute a new development version and need new genuinely held-out evidence. A suitable next milestone is a clearly labelled inventory-policy simulation with explicit lead-time, cost and stock assumptions; it must not turn this consumed test into fresh model-selection evidence.", "",
        "## Commands", "", "```powershell",
        ".\\.venv\\Scripts\\python.exe -m retail_forecasting freeze-final-evaluation",
        ".\\.venv\\Scripts\\python.exe -m retail_forecasting final-evaluation",
        ".\\.venv\\Scripts\\python.exe scripts/validate_final_evaluation.py",
        ".\\.venv\\Scripts\\python.exe -m unittest discover -s tests -v", "```", ""]
    require(not (root / REPORT).exists(), "Refusing to overwrite final report.")
    with (root / REPORT).open("x", encoding="utf-8") as stream:
        stream.write("\n".join(lines))
