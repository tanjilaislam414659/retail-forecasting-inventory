"""Scientific plots and a measured report for fixed empirical daily intervals."""

import os
from pathlib import Path

import pandas as pd


def make_plots(root, history, scored, scales, metrics):
    os.environ.setdefault("MPLCONFIGDIR", str(root / ".cache/matplotlib"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    output = root / "reports/generated/uncertainty"
    output.mkdir(parents=True, exist_ok=True)
    ranked = scales.sort_values(["training_positive_units", "sku"], ascending=[False, True]).reset_index(drop=True)
    skus = ranked.iloc[[0, 49, 99]].sku.tolist()
    origin = pd.Timestamp("2011-08-08")
    files = []

    def save(fig, stem):
        for extension in ("png", "svg"):
            path = output / f"{stem}.{extension}"
            fig.savefig(path, dpi=150)
            files.append(path.relative_to(root).as_posix())
        plt.close(fig)

    fig, axes = plt.subplots(3, 1, figsize=(12, 10), layout="constrained")
    for axis, sku, rank in zip(axes, skus, [1, 50, 100]):
        past = history.loc[history.sku.eq(sku) & history.date.ge(origin - pd.Timedelta(days=28)) & history.date.lt(origin)]
        subset = scored.loc[scored.sku.eq(sku) & scored.origin.eq(origin)].sort_values("target_date")
        wide = subset.loc[subset.level.eq(95)]
        narrow = subset.loc[subset.level.eq(80)]
        axis.plot(past.date, past.sales_units, color="#999999", linewidth=1, label="Observed before origin")
        axis.fill_between(wide.target_date, wide.lower, wide.upper, color="#0072B2", alpha=0.15, label="95% empirical interval")
        axis.fill_between(narrow.target_date, narrow.lower, narrow.upper, color="#0072B2", alpha=0.3, label="80% empirical interval")
        axis.plot(wide.target_date, wide.actual_sales, color="#111111", linewidth=1.5, label="Validation actuals")
        axis.plot(wide.target_date, wide.point_prediction, color="#D55E00", linestyle="--", linewidth=1.5, label="Frozen weekday mean")
        axis.axvline(origin, color="#555555", linestyle=":", linewidth=1)
        axis.set(title=f"SKU {sku} | original training-volume rank {rank} of 100", ylabel="Positive sales units",
                 xlim=(origin - pd.Timedelta(days=28), origin + pd.Timedelta(days=27)))
        axis.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=mdates.MO, interval=2))
        axis.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
        axis.grid(axis="y", color="#DDDDDD", linewidth=0.5)
        axis.spines[["top", "right"]].set_visible(False)
    axes[0].legend(loc="upper left", ncol=2, fontsize=8)
    axes[-1].set_xlabel("2011 dates; issued before sales on 8 August; bands are daily, not 28-day total bounds")
    fig.suptitle("Empirical historical-error daily prediction intervals", fontsize=14)
    save(fig, "representative_intervals")

    fig, axes = plt.subplots(1, 2, figsize=(12, 5), layout="constrained")
    weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    for level, color in ((80, "#0072B2"), (95, "#D55E00")):
        week = metrics["by_horizon_week"].loc[metrics["by_horizon_week"].level.eq(level)].sort_values("horizon_week")
        day = metrics["by_target_weekday"].loc[metrics["by_target_weekday"].level.eq(level)].set_index("target_weekday").reindex(weekdays)
        axes[0].plot(week.horizon_week, week.coverage_pct, marker="o", color=color, label=f"{level}% nominal")
        axes[1].plot(range(7), day.coverage_pct, marker="o", color=color, label=f"{level}% nominal")
        for axis in axes:
            axis.axhline(level, color=color, linestyle=":", alpha=0.7)
    axes[0].set(title="Validation coverage by horizon week", xlabel="Horizon week", xticks=[1, 2, 3, 4])
    axes[1].set(title="Validation coverage by target weekday", xlabel="Target weekday", xticks=range(7),
                xticklabels=[name[:3] for name in weekdays])
    for axis in axes:
        axis.set_ylabel("Empirical coverage (%)")
        axis.set_ylim(0, 101)
        axis.grid(color="#DDDDDD", linewidth=0.5)
        axis.spines[["top", "right"]].set_visible(False)
    axes[0].legend()
    save(fig, "coverage_diagnostics")
    return {"skus": skus, "training_volume_ranks": [1, 50, 100], "origin": "2011-08-08", "files": files}


def write_report(root, summary, metrics):
    s = summary
    lines = ["# Milestone 6: frozen weekday-mean uncertainty estimates", "",
        "These are **empirical historical-error daily prediction intervals**. They are not confidence intervals and carry no conformal/finite-sample coverage guarantee. Validation is development evidence after model selection. Final test remains unevaluated.",
        "Weekday mean is frozen as the first-release point forecaster. [Specification recorded before calculation](uncertainty-specification.md); `configs/first-release.json` records the release choice. All previous artifacts, scales and point predictions remain unchanged.", "",
        "## Calibration and dependence", "",
        f"Replayed **{s['calibration_rows']:,} historical forecasts** on the exact original-training Ridge grid: **{s['calibration_sku_origin_groups']:,} SKU/origin groups**, with **{s['calibration_unique_sku_target_dates']:,} unique SKU/target dates**. Calibration targets run **{s['calibration_first_target']} through {s['calibration_last_target']}**, strictly before 2011-06-06. Each forecast requires 56 complete retained days before its origin and matches the saved origin-available weekday-mean feature.",
        "Residual is **actual − prediction**, opposite to signed bias. For each SKU/horizon-week group, pool weekdays and use NumPy `method='linear'` quantiles: 0.10/0.90 for 80%, 0.025/0.975 for 95%. Bounds are max(0, point + residual quantile); endpoints are not rounded and point predictions are not forced inside.",
        f"Quantile table: **{s['calibration_group_level_rows']} group/level rows**; missing: **{s['missing_calibration_group_level_rows']}**. Per defined group, residual counts range **{s['sample_count_range']}**, unique target-date counts **{s['unique_target_count_range']}**, and distinct origins **{s['origin_count_range']}**. Counts are not independent sample sizes: rolling histories overlap, errors are serially dependent, and target dates recur across horizon-week groups.",
        "Missing groups are recorded explicitly without substitution. A metric aggregate containing missing intervals is undefined, with missing counts retained; rows/products are not silently dropped. Original-training quantiles are frozen before reading validation outcomes and never updated at later validation origins.", "",
        "## Validation results", "",
        "Same **28,000 validation point instances per level**, ten origins, targets before 2011-09-05. The 56,000 interval rows represent two levels, not new physical sales. Forecast horizons repeat target dates across origins: 9,100 unique SKU/target pairs, dependent errors.",
        "Coverage includes endpoints. Interval score = width + (2/alpha) × distance below/above the interval when missed. Alpha is 0.20 or 0.05. Scores balance width and misses for each nominal level; no method adjustment follows the measured result.", "",
        "| Nominal | Coverage | Mean width | Mean interval score | Below misses | Above misses | Zero width | Point outside |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in metrics["overall"].itertuples():
        lines.append(f"| {row.level}% | {row.coverage_pct:.2f}% | {row.mean_width:.4f} | {row.mean_interval_score:.4f} | {row.miss_below_count:,} | {row.miss_above_count:,} | {row.zero_width_count:,} | {row.point_outside_count:,} |")
    lines += ["", "### By horizon week", "",
        "| Nominal | Week | Coverage | Mean width | Interval score | Below | Above | Zero width |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for row in metrics["by_horizon_week"].itertuples():
        lines.append(f"| {row.level}% | {row.horizon_week} | {row.coverage_pct:.2f}% | {row.mean_width:.3f} | {row.mean_interval_score:.3f} | {row.miss_below_count:,} | {row.miss_above_count:,} | {row.zero_width_count:,} |")
    lines += ["", "### By target weekday", "",
        "| Nominal | Weekday | Coverage | Mean width | Interval score | Below | Above | Zero width |",
        "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    by_day = metrics["by_target_weekday"].copy()
    by_day["target_weekday"] = pd.Categorical(by_day.target_weekday, categories=days, ordered=True)
    for row in by_day.sort_values(["level", "target_weekday"]).itertuples():
        lines.append(f"| {row.level}% | {row.target_weekday} | {row.coverage_pct:.2f}% | {row.mean_width:.3f} | {row.mean_interval_score:.3f} | {row.miss_below_count:,} | {row.miss_above_count:,} | {row.zero_width_count:,} |")
    lines += ["", "## Limitations and representative plots", "",
        "The quantiles pool weekdays, so overall nominal coverage does not imply weekday-specific coverage. Saturday intervals are not forced to zero. Counts reflect observed sales, not latent demand or known stock availability. Original-training errors may differ from later-season errors; overlapping residuals and forecast instances invalidate simple independent-sample interpretations. Wide intervals or high coverage alone do not establish useful inventory decisions.",
        "No total-28-day uncertainty is estimated. **Do not sum these daily lower/upper endpoints and label that a calibrated total-sales interval.** Joint/aggregate uncertainty needs a separate method.",
        f"Plot selection retains original training-volume ranks 1, 50 and 100 (**{', '.join(s['plots']['skus'])}**) at origin 2011-08-08, without using coverage for example selection.",
        "![Representative daily intervals](../reports/generated/uncertainty/representative_intervals.png)", "",
        "![Coverage diagnostics](../reports/generated/uncertainty/coverage_diagnostics.png)", "",
        "## Evidence, reproduction and proposed final evaluation", "",
        "`data/uncertainty/` contains historical forecasts/residuals, all group counts/quantiles and missing groups, scored validation intervals, metrics overall/by SKU/week/weekday/origin/joint groups, calibration record, summary and hash/version manifest. No prior dataset/model result is regenerated. Generated data and plots are ignored by Git.",
        f"Historical replay and quantile work took **{s['calibration_wall_seconds']:.3f}s** wall time; full command **{s['total_wall_seconds']:.3f}s wall / {s['total_cpu_seconds']:.3f}s CPU**. Timings include data/plot work rather than a general performance benchmark.",
        "Run `.\\.venv\\Scripts\\python.exe -m retail_forecasting uncertainty`, then the tests and `scripts/validate_uncertainty.py`. [Milestone 6 protocol](milestone-6.md).",
        "[Proposed frozen final-evaluation protocol](proposed-final-evaluation.md): ten Monday origins 2011-09-05 through 2011-11-07, targets ending 2011-12-04; frozen point definition, original-training quantiles/scales/cohort; strictly prior observed-history updates only. Report all predefined point/interval metrics once after explicit authorization, with no post-final tuning. It has not been executed.", "",
    ]
    (root / "docs/uncertainty-results.md").write_text("\n".join(lines), encoding="utf-8")
