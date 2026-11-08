# Milestone 6: frozen weekday-mean uncertainty estimates

These are **empirical historical-error daily prediction intervals**. They are not confidence intervals and carry no conformal/finite-sample coverage guarantee. Validation is development evidence after model selection. Final test remains unevaluated.
Weekday mean is frozen as the first-release point forecaster. [Specification recorded before calculation](uncertainty-specification.md); `configs/first-release.json` records the release choice. All previous artifacts, scales and point predictions remain unchanged.

## Calibration and dependence

Replayed **185,584 historical forecasts** on the exact original-training Ridge grid: **6,628 SKU/origin groups**, with **48,496 unique SKU/target dates**. Calibration targets run **2010-02-01 through 2011-06-05**, strictly before 2011-06-06. Each forecast requires 56 complete retained days before its origin and matches the saved origin-available weekday-mean feature.
Residual is **actual − prediction**, opposite to signed bias. For each SKU/horizon-week group, pool weekdays and use NumPy `method='linear'` quantiles: 0.10/0.90 for 80%, 0.025/0.975 for 95%. Bounds are max(0, point + residual quantile); endpoints are not rounded and point predictions are not forced inside.
Quantile table: **800 group/level rows**; missing: **0**. Per defined group, residual counts range **[371, 469]**, unique target-date counts **[371, 469]**, and distinct origins **[53, 67]**. Counts are not independent sample sizes: rolling histories overlap, errors are serially dependent, and target dates recur across horizon-week groups.
Missing groups are recorded explicitly without substitution. A metric aggregate containing missing intervals is undefined, with missing counts retained; rows/products are not silently dropped. Original-training quantiles are frozen before reading validation outcomes and never updated at later validation origins.

## Validation results

Same **28,000 validation point instances per level**, ten origins, targets before 2011-09-05. The 56,000 interval rows represent two levels, not new physical sales. Forecast horizons repeat target dates across origins: 9,100 unique SKU/target pairs, dependent errors.
Coverage includes endpoints. Interval score = width + (2/alpha) × distance below/above the interval when missed. Alpha is 0.20 or 0.05. Scores balance width and misses for each nominal level; no method adjustment follows the measured result.

| Nominal | Coverage | Mean width | Mean interval score | Below misses | Above misses | Zero width | Point outside |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 80% | 83.89% | 64.4750 | 156.3246 | 2,183 | 2,329 | 0 | 0 |
| 95% | 95.45% | 149.7092 | 303.2531 | 568 | 707 | 0 | 0 |

### By horizon week

| Nominal | Week | Coverage | Mean width | Interval score | Below | Above | Zero width |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 80% | 1 | 83.79% | 63.873 | 151.825 | 536 | 599 | 0 |
| 80% | 2 | 83.87% | 63.963 | 156.261 | 541 | 588 | 0 |
| 80% | 3 | 83.99% | 64.889 | 158.760 | 553 | 568 | 0 |
| 80% | 4 | 83.90% | 65.175 | 158.452 | 553 | 574 | 0 |
| 95% | 1 | 95.46% | 149.731 | 296.110 | 147 | 171 | 0 |
| 95% | 2 | 95.37% | 149.343 | 303.427 | 145 | 179 | 0 |
| 95% | 3 | 95.50% | 149.853 | 308.275 | 137 | 178 | 0 |
| 95% | 4 | 95.46% | 149.910 | 305.200 | 139 | 179 | 0 |

### By target weekday

| Nominal | Weekday | Coverage | Mean width | Interval score | Below | Above | Zero width |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 80% | Monday | 83.35% | 64.089 | 156.028 | 327 | 339 | 0 |
| 80% | Tuesday | 75.20% | 72.754 | 178.917 | 514 | 478 | 0 |
| 80% | Wednesday | 78.70% | 71.854 | 154.573 | 376 | 476 | 0 |
| 80% | Thursday | 69.28% | 74.269 | 322.016 | 640 | 589 | 0 |
| 80% | Friday | 89.10% | 66.096 | 135.143 | 205 | 231 | 0 |
| 80% | Saturday | 100.00% | 42.573 | 42.573 | 0 | 0 | 0 |
| 80% | Sunday | 91.58% | 59.689 | 105.023 | 121 | 216 | 0 |
| 95% | Monday | 94.58% | 149.254 | 329.649 | 141 | 76 | 0 |
| 95% | Tuesday | 94.88% | 160.811 | 282.002 | 85 | 120 | 0 |
| 95% | Wednesday | 95.10% | 157.074 | 256.386 | 61 | 135 | 0 |
| 95% | Thursday | 88.90% | 162.834 | 679.727 | 177 | 267 | 0 |
| 95% | Friday | 96.95% | 151.528 | 247.736 | 74 | 48 | 0 |
| 95% | Saturday | 100.00% | 124.425 | 124.425 | 0 | 0 | 0 |
| 95% | Sunday | 97.72% | 142.038 | 202.846 | 30 | 61 | 0 |

## Limitations and representative plots

The quantiles pool weekdays, so overall nominal coverage does not imply weekday-specific coverage. Saturday intervals are not forced to zero. Counts reflect observed sales, not latent demand or known stock availability. Original-training errors may differ from later-season errors; overlapping residuals and forecast instances invalidate simple independent-sample interpretations. Wide intervals or high coverage alone do not establish useful inventory decisions.
No total-28-day uncertainty is estimated. **Do not sum these daily lower/upper endpoints and label that a calibrated total-sales interval.** Joint/aggregate uncertainty needs a separate method.
Plot selection retains original training-volume ranks 1, 50 and 100 (**21212, 21791, 21533**) at origin 2011-08-08, without using coverage for example selection.
![Representative daily intervals](../reports/generated/uncertainty/representative_intervals.png)

![Coverage diagnostics](../reports/generated/uncertainty/coverage_diagnostics.png)

## Evidence, reproduction and proposed final evaluation

`data/uncertainty/` contains historical forecasts/residuals, all group counts/quantiles and missing groups, scored validation intervals, metrics overall/by SKU/week/weekday/origin/joint groups, calibration record, summary and hash/version manifest. No prior dataset/model result is regenerated. Generated data and plots are ignored by Git.
Historical replay and quantile work took **14.591s** wall time; full command **18.694s wall / 18.297s CPU**. Timings include data/plot work rather than a general performance benchmark.
Run `.\.venv\Scripts\python.exe -m retail_forecasting uncertainty`, then the tests and `scripts/validate_uncertainty.py`. [Milestone 6 protocol](milestone-6.md).
[Proposed frozen final-evaluation protocol](proposed-final-evaluation.md): ten Monday origins 2011-09-05 through 2011-11-07, targets ending 2011-12-04; frozen point definition, original-training quantiles/scales/cohort; strictly prior observed-history updates only. Report all predefined point/interval metrics once after explicit authorization, with no post-final tuning. It has not been executed.
