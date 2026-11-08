# Milestone 6: frozen weekday mean with historical-error daily intervals

Weekday mean is frozen as the first-release point forecaster. The fixed empirical
historical-error method was recorded before quantiles or validation coverage were
calculated. No point-model search or post-coverage adjustment was performed.

These are **daily prediction intervals**, with no conformal/finite-sample guarantee.
Validation remains development evidence after point-model selection. Final test
remains unevaluated.

## Reproduce

From the repository root, use the existing environment:

```powershell
.\.venv\Scripts\python.exe -m retail_forecasting uncertainty
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
.\.venv\Scripts\python.exe scripts\validate_uncertainty.py
.\.venv\Scripts\python.exe scripts\validate_boosting.py
.\.venv\Scripts\python.exe scripts\validate_ridge.py
.\.venv\Scripts\python.exe scripts\validate_baselines.py
.\.venv\Scripts\python.exe scripts\validate_data.py
.\.venv\Scripts\python.exe scripts\verify.py
.\.venv\Scripts\python.exe -m pip check
```

No downloads, environment changes, point-model fits or previous-result regeneration
are needed. The command verifies earlier hashes and recreates only uncertainty
artifacts using the unchanged fixed method.

## Specification and first-release freeze

- [`configs/first-release.json`](../configs/first-release.json) freezes weekday mean.
- [`configs/uncertainty.json`](../configs/uncertainty.json) fixes residual sign,
  grouping, quantile levels/method, endpoints, missingness and evaluation conventions.
- [Pre-calculation specification](uncertainty-specification.md) was recorded at
  **2026-11-01 19:49:57 UTC**; calibration completed at **19:57:12 UTC**.
- [Proposed frozen final protocol](proposed-final-evaluation.md) was written before
  validation coverage calculation; it has not been executed.

All existing data, models, results, 100 SKUs, splits, 484-row history mask, SKU
21166 distinction, original scales, origins and saved point predictions are
preserved. The independent validator checks the earlier hashes and exact point
values, not just rounded point metrics.

## Calibration and group counts

Replayed **185,584** historical weekday-mean forecasts on the exact original-training
Ridge grid: **6,628 SKU/origin groups**, covering **48,496 unique SKU/target dates**.
Calibration targets run **2010-02-01 through 2011-06-05**. Each forecast requires
all 56 preceding retained days and uses observations strictly before its origin.
Replayed points equal the existing saved `weekday_mean_8` values exactly.

Residual = **actual − prediction**, opposite to the signed-bias metric. Group by
SKU and horizon week, pooling weekdays. Use NumPy linear residual quantiles:
0.10/0.90 for 80%, and 0.025/0.975 for 95%. Every expected group is present:
**400 SKU/week groups**, **800 group/level rows**, **0 missing groups**.

Per group, there are **371–469 residual rows**, **371–469 unique target dates**,
and **53–67 distinct origins**. Although dates happen to be unique within each
fixed SKU/week group, rolling histories overlap and the same targets recur across
different horizon-week groups. These counts are not independent sample sizes.

Missing-group behavior is implemented and tested: explicit status/counts, no
substitution, and undefined coverage/width/score for affected aggregates. It was
not needed for this dataset.

## Validation results

At each saved point p, lower/upper are `max(0, p + residual_quantile)`. Points are
unchanged; endpoints are not rounded and no point-containment constraint is added.
The 95% bands nest the 80% bands. All endpoints are finite, ordered and nonnegative.

| Nominal | Instances | Coverage | Mean width (units) | Mean interval score | Below misses | Above misses | Zero width |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 80% | 28,000 | 83.8857% | 64.4750 | 156.3246 | 2,183 | 2,329 | 0 |
| 95% | 28,000 | 95.4464% | 149.7092 | 303.2531 | 568 | 707 | 0 |

Missing validation intervals: **0**. Point predictions outside their interval:
**0** in the actual results; tests verify that such points would not be forced
inside. Coverage is inclusive of endpoints. Interval score adds width plus a
distance penalty for misses, weighted by 2/alpha (10 for 80%, 40 for 95%).
This is the [Winkler interval score](https://otexts.com/fpp3/toolbox.html#winkler-score).

Detailed metrics include every SKU, horizon week, target weekday and origin, plus
joint group tables. The generated [results report](uncertainty-results.md) includes
all horizon/weekday tables and representative plots.

## Conditional coverage limitations

Overall nominal coverage is not a guarantee for every product or weekday:

| Level | SKU coverage minimum | Median | Maximum | SKUs below nominal |
| ---: | ---: | ---: | ---: | ---: |
| 80% | 57.14% | 86.07% | 98.57% | 26/100 |
| 95% | 78.21% | 96.79% | 100.00% | 33/100 |

At 80%, the lowest-coverage SKU is **47566 (57.14%)**, followed by **84978 (59.29%)**
and **48187 (61.79%)**. At 95%, **20685 and 47566 each have 78.21% coverage**.
No SKU is removed or assigned a fallback method because of these findings.

Thursday coverage is **69.275% / 88.90%** for nominal 80%/95%, while Saturday
coverage is **100% at both levels**. Saturday mean widths remain **42.5732 /
124.4253 units**, despite zero observed Saturday sales, because weekdays were
pooled and no zero rule was introduced. These are observed-sales diagnostics,
not proof of store opening, listing or stock availability.

Original-training residual distributions can differ from validation/future errors.
Counts include overlapping forecast instances and serial dependence, so simple
independent-sample confidence claims are inappropriate. Levels apply to daily
outcomes, not joint coverage of all 28 days. **Never sum daily endpoints and call
them calibrated bounds for total 28-day sales.** Aggregate uncertainty needs a
separate method. This milestone preserves the specified method after seeing these
limitations, rather than tuning it to validation coverage.

## Saved evidence and timing

All generated data live under ignored `data/uncertainty/`:

| File | Contents |
| --- | --- |
| `historical_forecasts_residuals.csv.gz` | 185,584 past-only historical point forecasts, actuals, residuals and grid keys. |
| `calibration_quantiles.csv` | 800 group/level rows with residual/date/origin counts and linear quantiles. |
| `missing_calibration_groups.csv` | Explicit missing-group record, empty with headers in this run. |
| `calibration-record.json`, `experiment-specification.json` | Calibration time, input/config/output hashes and exact fixed method snapshot. |
| `validation_intervals.csv.gz` | 56,000 scored interval rows: 28,000 per level, unchanged points, actuals, quantiles/bounds, coverage/misses, width and score. |
| `metrics_overall.csv`, `metrics_by_*.csv` | Overall, SKU, horizon-week, weekday, origin and joint group metrics, with explicit missing counts/statuses. |
| `summary.json`, `manifest.json` | Measured totals, timing, release/config/code/version and prior/output hashes. |

PNG/SVG plots live in ignored `reports/generated/uncertainty/`. Representative
SKUs are the unchanged training-volume ranks 1/50/100: **21212, 21791, 21533**,
at the last validation origin **2011-08-08**. No example is selected by coverage.

Historical replay/calibration took **14.591 wall seconds**. Full command took
**18.694 wall / 18.297 CPU seconds**, including loading, metrics and plots. These
are measured timings for this machine, not general performance guarantees.

## Checks and proposed final evaluation

**44 tests passed**, including nine new uncertainty tests for linear interpolation,
residual sign, count semantics, strict dates/complete history, bounds and nesting,
nonnegativity, point preservation/no forced containment, inclusive score arithmetic,
explicit missing groups and validation-outcome mutation invariance.

The independent validator replays each historical mean and checks the exact grid,
residuals, quantiles/counts, unchanged points, all endpoints, nesting, all metric
tables and prior-result hashes. It does not recalibrate the method or score final
test. Earlier data/model validators remain available.

Final checks recorded on 2026-11-01: **44/44 tests passed**. The independent
uncertainty validator and every earlier data/baseline/Ridge/boosting validator
passed. Installation smoke checks passed; `pip check` found no broken requirements.
Git ignore checks cover calibration/interval data and plots. Prior hashes and all
28,000 saved weekday-mean point values remain unchanged.

Proposed final assessment, pending separate authorization: freeze all current
artifacts and use ten Monday origins **2011-09-05 through 2011-11-07**, with targets
through **2011-12-04**. Refresh only strictly past observed history; keep point
definition, original-training quantiles and scales fixed. Report all predefined
point/daily-interval metrics once, including failure slices, with no post-final
tuning. The [full proposal](proposed-final-evaluation.md) defines dates and policies.
