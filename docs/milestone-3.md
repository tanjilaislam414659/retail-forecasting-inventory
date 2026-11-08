# Milestone 3: fixed forecasting baselines and validation

This milestone evaluates three fixed baselines on validation only. The original
100-SKU cohort, daily frequency, study splits, 28-day horizon, raw workbook and
Milestone 2 generated files are preserved. No window search, complex ML model,
final-test evaluation, API or dashboard was performed.

## Reproduce

Use the existing project environment from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pip install --disable-pip-version-check -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pip install --disable-pip-version-check --no-build-isolation --no-deps -e .
.\.venv\Scripts\python.exe -m retail_forecasting baselines
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts\validate_baselines.py
.\.venv\Scripts\python.exe scripts\validate_data.py
.\.venv\Scripts\python.exe scripts\verify.py
.\.venv\Scripts\python.exe -m pip check
```

There is no acquisition or preparation command here: existing files are reused
after integrity checks. Matplotlib is added to the same isolated environment for
static plots; the complete dependency lock is updated. The experiment requires
the exact origins/windows in `configs/baselines.json` and rejects changes to the
preserved preparation protocol or input files.

## Modelling history and frozen scales

Find each selected SKU's first qualifying positive transaction using only audit
rows timestamped before **2011-06-06**, including otherwise qualifying sales before
the **2009-12-07** study start. Cross-sheet copies, cancellations, returns, invalid
prices and out-of-scope codes do not define this date. Missing customer IDs do not
invalidate an otherwise qualifying sale.

The modelling view starts at `max(study_start, first_qualifying_sale_date)` for
each SKU. Earlier study dates are excluded from modelling and metric scales, but
remain in the unchanged audit panel. This removes **484 zero-filled training rows
across 10 SKUs**, leaving **54,116 training rows** and all **9,100 validation rows**.
No pre-study sales are appended to the original training interval, and no future
last sale is used to trim history.

SKU **21166** first qualified on **2009-12-01**. Its **2009-12-07** zero is retained,
although its first positive sale inside the study occurs on **2009-12-08**. A rule
based only on in-study first sales would instead exclude 485 rows across 11 SKUs;
that rule is not used. First sale indicates an observed transaction, not proven
listing, availability or an uncensored demand start.

For SKU i with n retained original-training dates, freeze the seasonal scale:

```text
q_i = sum(|y[t] - y[t-7]|, t=8..n) / (n-7)
```

Both members of each lag pair must lie in the retained modelling interval. Scales
end on **2011-06-05**, do not include earlier excluded zeros, and never incorporate
validation observations. All 100 actual scales are positive. Dates, counts, scale
pairs and values are saved in `data/baselines/history_and_scales.csv`.

## Baselines and information availability

At origin O, only values dated before O are available:

| Method | All 28 predictions issued at O |
| --- | --- |
| Seasonal naive | Repeat values O-7 through O-1 four times. |
| Recent mean | Every prediction equals mean of O-28 through O-1, including zero days. |
| Weekday mean | For each target weekday, average its eight occurrences in O-56 through O-1; repeat that weekday pattern for four weeks. |

Predictions remain fractional when a mean is fractional; there is no rounding or
post-hoc adjustment. Missing required calendar days cause an error instead of
compressing time or silently shortening a window. Predictions are created before
joining target actuals. Future actuals are never used recursively inside a horizon.

| Origin | Last target date |
| --- | --- |
| 2011-06-06 | 2011-07-03 |
| 2011-06-13 | 2011-07-10 |
| 2011-06-20 | 2011-07-17 |
| 2011-06-27 | 2011-07-24 |
| 2011-07-04 | 2011-07-31 |
| 2011-07-11 | 2011-08-07 |
| 2011-07-18 | 2011-08-14 |
| 2011-07-25 | 2011-08-21 |
| 2011-08-01 | 2011-08-28 |
| 2011-08-08 | 2011-09-04 |

This is walk-forward validation: for example, the 13 June origin may use observed
sales through 12 June, including validation dates. It cannot use 13 June or later
actuals. The definitions and MASE scales stay fixed at all ten origins.

There are **84,000 forecast rows**, **28,000 per model**, spanning **9,100 distinct
SKU/target-date pairs**. Overlapping horizons repeat a date at different issue
times, up to four per model. Metrics score forecast instances; the observed-unit
denominator across those repeated instances is **771,213 units per model**, not
the **246,299 unique validation units** in the original panel. Do not interpret
these forecasts as independent samples or sum model actuals as new physical sales.

## Metrics and undefined denominators

With error defined as `prediction - actual`:

- MAE = sum absolute error / number of forecast rows.
- Pooled WAPE (%) = 100 x sum absolute error / sum actual sales.
- Mean signed bias = sum error / number of forecast rows; positive is overforecast.
  Relative bias (%) = 100 x sum error / sum actual sales.
- SKU MASE = SKU MAE / frozen q_i. Macro MASE averages SKU MASE equally, without
  weighting by sales volume or recomputing scale from validation. Within a
  SKU/origin/week slice the same original-training q_i is used.

A zero actual-unit denominator makes WAPE and relative bias **undefined**, even
for zero predictions. A zero q_i makes SKU MASE undefined, even for zero error.
Empty CSV metric values are accompanied by explicit status/count columns. Macro
MASE is undefined if any constituent SKU is undefined; no epsilon, infinity
substitution or silent SKU removal is used. MAE and unnormalised signed bias remain
defined when actuals are all zero.

Observed: no zero training scales and no undefined macro MASE groups. WAPE is
undefined for **21 model/SKU/origin groups** (7 SKU/origin combinations x 3 models)
and **171 model/SKU/origin/week groups** (57 combinations x 3). All are retained.

See the generated [baseline comparison](baseline-comparison.md) for model and
horizon results, per-SKU winner counts, origin variation and plots.

## Outputs

Under ignored `data/baselines/`:

| File | Contract |
| --- | --- |
| `validation_forecasts.csv.gz` | model, SKU, origin, target date, horizon day 1–28, horizon week 1–4, actual sales and predicted sales. All targets precede final test. |
| `modelling_history.csv.gz` | Separate onset-adjusted view of original training and validation rows; no final-test rows. |
| `history_and_scales.csv` | 100 first-sale/onset reconciliations, excluded-day counts, training-only MASE scales and scale-pair counts. |
| `metrics_by_model.csv` | 3 overall model rows. |
| `metrics_by_sku.csv` | 300 model/SKU rows. |
| `metrics_by_origin.csv` | 30 model/origin rows. |
| `metrics_by_horizon_week.csv` | 12 model/week rows. |
| `metrics_by_sku_origin.csv` | 3,000 joint rows. |
| `metrics_by_sku_origin_week.csv` | 12,000 joint rows. |
| `summary.json`, `manifest.json` | Measured totals, undefined counts, timings, plot rule, config/code/input/output hashes and dependency versions. |

Representative PNG/SVG plots live under ignored `reports/generated/baselines/`.
They show training-volume ranks **1, 50 and 100**, breaking ties by SKU ascending,
at the final prescribed validation origin. The selected SKUs are **21212, 21791
and 21533**. This rule was recorded before evaluation and does not use validation
errors. Plots show 56 preceding days and the 28 issued predictions alongside actuals.

## Verification and limits

**20 tests passed**, including the original eight and twelve new tests covering
hand-calculated forecasts, weekday/date alignment, complete calendar windows,
pre-study observations, retained SKU 21166 zeros, lag-pair exclusion, frozen scales,
metric arithmetic, undefined denominators and leakage. Mutating all sales on or
after an origin leaves that origin's predictions unchanged for every method.
Another test confirms that a later origin may use newly observed validation sales.

`validate_baselines.py` independently checks preserved inputs, the 484-row
reconciliation, every saved prediction and actual against its calendar window,
the training scales, all overall metrics, detailed-table dimensions, target
boundaries and undefined-status consistency. It does not evaluate final test.

These are point forecasts of observed positive sales, not latent demand. Large
orders remain in the target, stockouts/opening hours are unknown, and overlapping
forecasts are dependent. The validation winner is a benchmark, not proof of future
performance or inventory benefit.
