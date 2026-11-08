# Milestone 3: fixed baseline validation

Generated from the preserved 100-SKU daily panel. No final-test evaluation, window tuning or complex ML.

## History adjustment

The first qualifying positive sale is determined from pre-2011-06-06 audit records, including records before the study starts. Modelling history begins at the later of that date and 2009-12-07. The original audit panel is unchanged; no earlier pre-study sales are appended to the original training interval.
Removed **484 leading zero-filled training rows across 10 SKUs** in a separate modelling view: **54,116 training rows** remain, plus **9,100 validation rows**. Scale pairs require both dates to be on/after that SKU's modelling start.
SKU 21166 was first observed on **2009-12-01**, before study start. Its one zero before its first in-window sale is retained. Using in-window first sales alone would remove 485 rows across 11 SKUs; that is not the modelling rule.
This onset rule is a modelling assumption based on the first qualifying recorded sale, not proof of listing or availability. Other zeros and large orders remain unchanged.

## Fixed definitions and walk-forward validation

- Seasonal naive repeats the last available seven calendar days four times.
- Recent mean uses the previous 28 calendar days, including observed zero-sales days.
- Weekday mean uses the eight prior occurrences of each target weekday (56-day lookback). Its four forecast weeks repeat the same weekday means.
Ten Monday origins run weekly from **2011-06-06 through 2011-08-08**. Each origin issues all 28 daily predictions before observing that day's sales. Later origins may use validation sales already observed before their own issue date; no method consumes actuals from inside its forecast horizon. Definitions never change.
All targets lie in **2011-06-06 through 2011-09-04**. There are **84,000 forecast rows** (28,000 per model), but only **9,100 distinct SKU/target-date pairs**. Overlapping horizons score some dates up to four times at different origins; metrics weight issued forecasts and are not independent daily samples.

## Metrics

MAE is mean absolute error in units per SKU/day forecast. Pooled WAPE is 100 x sum absolute error / sum actual units. Signed bias is mean(prediction - actual), positive for overforecasting; relative bias uses the same actual-unit denominator as WAPE.
For each SKU, the MASE scale is mean absolute lag-7 difference over adjusted **original training dates only**. It is frozen before validation, never updated at later origins. Per-SKU MASE is validation MAE / that scale; macro MASE averages all 100 SKU values equally. A value below one means errors are below the historical seasonal-naive scale, not necessarily below the validation seasonal-naive baseline.
Zero actual totals make WAPE/relative bias undefined; zero training scales make SKU MASE undefined. CSVs retain the rows with empty metric values and explicit status/count columns. A macro MASE containing any undefined SKU is itself undefined; no epsilon and no silent product removal.
Actual zero training scales: **0**. Undefined WAPE groups by output: `{'by_model': 0, 'by_sku': 0, 'by_origin': 0, 'by_horizon_week': 0, 'by_sku_origin': 21, 'by_sku_origin_week': 171}`. Undefined MASE groups: `{'by_model': 0, 'by_sku': 0, 'by_origin': 0, 'by_horizon_week': 0, 'by_sku_origin': 0, 'by_sku_origin_week': 0}`.
Metric definitions follow the [primary forecasting textbook's scaled-error discussion](https://otexts.com/fpp3/toolbox.html#scaled-errors); the denominator/aggregation conventions above specify this experiment.

| Model | MAE (units) | Pooled WAPE | Mean signed bias (units) | Relative bias | Macro MASE |
| --- | ---: | ---: | ---: | ---: | ---: |
| recent_mean | 28.5122 | 103.52% | -1.1487 | -4.17% | 0.8042 |
| seasonal_naive | 32.0417 | 116.33% | -1.7009 | -6.18% | 0.9160 |
| weekday_mean | 26.7655 | 97.18% | -0.7121 | -2.59% | 0.7581 |

### By forecast-horizon week

| Model | Week | MAE | WAPE | Signed bias | Macro MASE |
| --- | ---: | ---: | ---: | ---: | ---: |
| recent_mean | 1 | 27.8673 | 101.94% | -0.9417 | 0.8073 |
| recent_mean | 2 | 28.5067 | 103.72% | -1.0889 | 0.8026 |
| recent_mean | 3 | 28.8166 | 103.61% | -1.4180 | 0.8030 |
| recent_mean | 4 | 28.8580 | 104.78% | -1.1464 | 0.8039 |
| seasonal_naive | 1 | 31.3136 | 114.55% | -1.4939 | 0.9207 |
| seasonal_naive | 2 | 31.7433 | 115.50% | -1.6410 | 0.9037 |
| seasonal_naive | 3 | 32.4056 | 116.51% | -1.9701 | 0.9177 |
| seasonal_naive | 4 | 32.7043 | 118.75% | -1.6986 | 0.9218 |
| weekday_mean | 1 | 26.2249 | 95.93% | -0.5051 | 0.7652 |
| weekday_mean | 2 | 26.7844 | 97.46% | -0.6522 | 0.7559 |
| weekday_mean | 3 | 26.9452 | 96.88% | -0.9813 | 0.7534 |
| weekday_mean | 4 | 27.1075 | 98.43% | -0.7098 | 0.7579 |

## Measured variation and failure patterns

Lowest per-SKU MAE counts (ties broken by model name): `{'weekday_mean': 81, 'recent_mean': 14, 'seasonal_naive': 5}`. The pooled winner need not win every SKU.
- seasonal_naive: origin WAPE ranges from 100.12% (2011-07-18) to 140.58% (2011-07-11). Largest aggregate absolute-error SKU: 84879, 39,426.0 units of absolute error.
- recent_mean: origin WAPE ranges from 94.24% (2011-07-18) to 117.00% (2011-06-20). Largest aggregate absolute-error SKU: 22197, 39,071.6 units of absolute error.
- weekday_mean: origin WAPE ranges from 91.07% (2011-07-18) to 108.18% (2011-06-20). Largest aggregate absolute-error SKU: 22197, 41,437.5 units of absolute error.
These comparisons are descriptive; overlapping horizons and SKU dependence preclude treating 28,000 forecasts as independent evidence. The baselines cannot anticipate unobserved promotions, wholesale spikes or stock availability. Plots below show selected examples without choosing them by validation error.

## Representative plots and saved evidence

Plot SKUs are training-volume ranks **1, 50, 100**, ties by SKU ascending: **21212, 21791, 21533**. All use the last prescribed origin, **2011-08-08**, and show 56 preceding days plus the 28-day forecast. The selection rule was fixed in `configs/baselines.json` before evaluation.
![Representative validation forecasts](../reports/generated/baselines/representative_forecasts.png)

`data/baselines/` contains forecasts with model/SKU/origin/target/horizon/actual/prediction, the separate modelling view, first-sale reconciliation and frozen scales, metrics by model/SKU/origin/horizon week and joint combinations, a summary, and a hash/version manifest. All generated data and plots are ignored by Git.
This run took 11.035 wall seconds / 9.516 CPU seconds, including data loading, reports and plots; it is not a model-only timing benchmark.

## Reproduce and next milestone

Run `.\.venv\Scripts\python.exe -m retail_forecasting baselines`, then `.\.venv\Scripts\python.exe -m unittest discover -s tests -v` and `.\.venv\Scripts\python.exe scripts\validate_baselines.py`. Detailed protocol: [Milestone 3](milestone-3.md).
Next proposed modelling milestone: one modest pooled, regularized lag/calendar model using origin-available features and the same validation protocol. Compare with the strongest fixed baseline, report SKU/horizon failures and runtime, and keep final test sealed until the modelling plan is frozen. No API/dashboard or inventory-savings claims yet.
