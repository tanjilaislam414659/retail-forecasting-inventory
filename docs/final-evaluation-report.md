# Milestone 7: one frozen final held-out evaluation

The first-release point forecaster remains **eight-week weekday mean**. Seasonal naive is a fixed reference, not a model-selection candidate. Unchanged original-training residual intervals are **experimental empirical historical-error daily prediction intervals**. No tuning, model switch, recalibration or preparation change followed final outcomes.

[Frozen protocol](proposed-final-evaluation.md), `configs/final-evaluation.json`, and `data/final_evaluation/freeze.json` identify the pre-unblinding specification, source, inputs and calibration by SHA-256. Local source is uncommitted; no commit identity is claimed.

## Validation development evidence — saved earlier results

| model | macro_mase | mae | wape_pct | mean_bias_units | bias_pct |
| --- | --- | --- | --- | --- | --- |
| seasonal_naive | 0.9160 | 32.0417 | 116.3319 | -1.7009 | -6.1753 |
| weekday_mean | 0.7581 | 26.7655 | 97.1760 | -0.7121 | -2.5853 |

| level | coverage_pct | mean_width | mean_interval_score | miss_below_count | miss_above_count | missing_interval_count | zero_width_count |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 80 | 83.8857 | 64.4750 | 156.3246 | 2183 | 2329 | 0 | 0 |
| 95 | 95.4464 | 149.7092 | 303.2531 | 568 | 707 | 0 | 0 |

Validation informed point-model development and selection; these values are not a fresh held-out assessment.

## Final held-out evidence — one evaluation

All 100 SKUs; ten Monday origins **2011-09-05 through 2011-11-07**, each forecasting origin through +27 days. Targets end **2011-12-04**, before 2011-12-05. Each point method has **28,000 origin-specific instances**, representing **9,100 unique SKU/target-date pairs**. The two interval levels produce 56,000 rows, not additional physical sales.

| model | macro_mase | mae | wape_pct | mean_bias_units | bias_pct |
| --- | --- | --- | --- | --- | --- |
| seasonal_naive | 1.0423 | 35.5831 | 110.5641 | -2.7385 | -8.5091 |
| weekday_mean | 0.8656 | 29.4538 | 91.5192 | -2.3694 | -7.3621 |

| level | coverage_pct | mean_width | mean_interval_score | miss_below_count | miss_above_count | missing_interval_count | zero_width_count |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 80 | 81.2143 | 66.0807 | 175.1482 | 2437 | 2823 | 0 | 0 |
| 95 | 94.1286 | 152.0985 | 345.7078 | 875 | 769 | 0 | 0 |

Signed bias is prediction minus actual. Relative bias and WAPE use pooled actual units. Macro MASE gives each SKU equal weight and uses its unchanged original-training lag-seven scale. Zero denominators are explicit undefined statuses, with no epsilon or silently omitted products. Coverage includes endpoints; interval score penalizes both width and missed-bound distance.

### Selected method versus fixed reference

| metric | selected | reference | selected_minus_reference | relative_change_pct |
| --- | --- | --- | --- | --- |
| macro_mase | 0.8656 | 1.0423 | -0.1767 | -16.9520 |
| mae | 29.4538 | 35.5831 | -6.1292 | -17.2252 |
| wape_pct | 91.5192 | 110.5641 | -19.0449 | -17.2252 |
| mean_bias_units | -2.3694 | -2.7385 | 0.3691 | -13.4791 |
| bias_pct | -7.3621 | -8.5091 | 1.1469 | -13.4791 |

Per-SKU MASE descriptive wins/ties/losses: **{'win': 93, 'loss': 7}** (absolute tie tolerance 1e-10). Negative error-metric changes indicate lower error; relative changes of signed bias are not an improvement measure. The release choice remains frozen regardless of this comparison.

### Point results by horizon week

| model | horizon_week | macro_mase | mae | wape_pct | mean_bias_units | bias_pct |
| --- | --- | --- | --- | --- | --- | --- |
| seasonal_naive | 1 | 1.0316 | 34.9961 | 111.2351 | -2.0167 | -6.4101 |
| seasonal_naive | 2 | 1.0419 | 35.7813 | 110.6615 | -2.8893 | -8.9358 |
| seasonal_naive | 3 | 1.0548 | 36.1451 | 111.1391 | -3.0777 | -9.4634 |
| seasonal_naive | 4 | 1.0407 | 35.4097 | 109.2387 | -2.9703 | -9.1633 |
| weekday_mean | 1 | 0.8596 | 29.0881 | 92.4565 | -1.6476 | -5.2369 |
| weekday_mean | 2 | 0.8682 | 29.5252 | 91.3133 | -2.5202 | -7.7942 |
| weekday_mean | 3 | 0.8732 | 29.7274 | 91.4058 | -2.7086 | -8.3284 |
| weekday_mean | 4 | 0.8614 | 29.4746 | 90.9287 | -2.6012 | -8.0246 |

### Point results by origin

| model | origin | macro_mase | mae | wape_pct | bias_pct |
| --- | --- | --- | --- | --- | --- |
| seasonal_naive | 2011-09-05 00:00:00 | 0.9081 | 30.3943 | 95.7236 | -41.6822 |
| seasonal_naive | 2011-09-12 00:00:00 | 1.1296 | 37.7300 | 111.0733 | -9.3364 |
| seasonal_naive | 2011-09-19 00:00:00 | 1.2001 | 38.3871 | 119.4134 | -0.7621 |
| seasonal_naive | 2011-09-26 00:00:00 | 1.2222 | 38.7818 | 134.0191 | 35.5335 |
| seasonal_naive | 2011-10-03 00:00:00 | 0.8898 | 29.6107 | 100.1474 | -15.1423 |
| seasonal_naive | 2011-10-10 00:00:00 | 1.2393 | 42.1354 | 154.2592 | 45.2073 |
| seasonal_naive | 2011-10-17 00:00:00 | 0.8959 | 30.0646 | 97.5096 | -20.1724 |
| seasonal_naive | 2011-10-24 00:00:00 | 0.9344 | 34.1614 | 100.1298 | -22.6656 |
| seasonal_naive | 2011-10-31 00:00:00 | 0.9589 | 37.0329 | 103.8457 | -22.5814 |
| seasonal_naive | 2011-11-07 00:00:00 | 1.0443 | 37.5325 | 99.9943 | -18.3345 |
| weekday_mean | 2011-09-05 00:00:00 | 0.8319 | 27.6878 | 87.1997 | -13.4204 |
| weekday_mean | 2011-09-12 00:00:00 | 0.9111 | 30.1960 | 88.8939 | -14.4961 |
| weekday_mean | 2011-09-19 00:00:00 | 0.8828 | 29.0167 | 90.2641 | -8.5902 |
| weekday_mean | 2011-09-26 00:00:00 | 0.8380 | 28.1205 | 97.1768 | 7.3755 |
| weekday_mean | 2011-10-03 00:00:00 | 0.8496 | 29.0193 | 98.1471 | 0.6982 |
| weekday_mean | 2011-10-10 00:00:00 | 0.8167 | 27.7491 | 101.5906 | 12.1945 |
| weekday_mean | 2011-10-17 00:00:00 | 0.8452 | 29.5941 | 95.9835 | -3.0157 |
| weekday_mean | 2011-10-24 00:00:00 | 0.8612 | 30.5567 | 89.5641 | -13.4652 |
| weekday_mean | 2011-10-31 00:00:00 | 0.9009 | 31.0502 | 87.0694 | -14.0258 |
| weekday_mean | 2011-11-07 00:00:00 | 0.9186 | 31.5479 | 84.0500 | -18.3645 |

### Interval results by horizon week

| level | horizon_week | coverage_pct | mean_width | mean_interval_score | miss_below_count | miss_above_count | missing_interval_count | zero_width_count |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 80 | 1 | 81.4429 | 65.5135 | 173.3514 | 618 | 681 | 0 | 0 |
| 80 | 2 | 81.2143 | 65.5548 | 176.1582 | 611 | 704 | 0 | 0 |
| 80 | 3 | 80.8143 | 66.4909 | 176.3028 | 622 | 721 | 0 | 0 |
| 80 | 4 | 81.3857 | 66.7635 | 174.7803 | 586 | 717 | 0 | 0 |
| 95 | 1 | 94.3571 | 152.0834 | 344.2633 | 215 | 180 | 0 | 0 |
| 95 | 2 | 94.1857 | 151.6985 | 350.7899 | 222 | 185 | 0 | 0 |
| 95 | 3 | 93.9857 | 152.2500 | 344.1843 | 222 | 199 | 0 | 0 |
| 95 | 4 | 93.9857 | 152.3619 | 343.5938 | 216 | 205 | 0 | 0 |

### Interval results by target weekday

| level | target_weekday | coverage_pct | mean_width | mean_interval_score | miss_below_count | miss_above_count | missing_interval_count | zero_width_count |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 80 | Friday | 80.0750 | 68.9195 | 198.1817 | 271 | 526 | 0 | 0 |
| 80 | Monday | 78.6750 | 69.3985 | 214.2181 | 289 | 564 | 0 | 0 |
| 80 | Saturday | 100.0000 | 42.5732 | 42.5732 | 0 | 0 | 0 | 0 |
| 80 | Sunday | 91.4000 | 59.2023 | 82.9313 | 77 | 267 | 0 | 0 |
| 80 | Thursday | 66.7250 | 76.9960 | 278.5602 | 802 | 529 | 0 | 0 |
| 80 | Tuesday | 77.6500 | 73.0680 | 203.7095 | 467 | 427 | 0 | 0 |
| 80 | Wednesday | 73.9750 | 72.4073 | 205.8633 | 531 | 510 | 0 | 0 |
| 95 | Friday | 93.9750 | 154.7174 | 390.4309 | 110 | 131 | 0 | 0 |
| 95 | Monday | 93.5750 | 154.0111 | 402.0734 | 43 | 214 | 0 | 0 |
| 95 | Saturday | 100.0000 | 124.4253 | 124.4253 | 0 | 0 | 0 | 0 |
| 95 | Sunday | 97.8750 | 141.3521 | 153.4755 | 42 | 43 | 0 | 0 |
| 95 | Thursday | 88.1500 | 170.1789 | 561.7465 | 335 | 139 | 0 | 0 |
| 95 | Tuesday | 92.8000 | 159.9364 | 421.3930 | 176 | 112 | 0 | 0 |
| 95 | Wednesday | 92.5250 | 160.0681 | 366.4101 | 169 | 130 | 0 | 0 |

## Failures and distribution differences

Selected macro_mase: validation 0.758109, final 0.865584; descriptive change +14.18%.
Selected mae: validation 26.765509, final 29.453821; descriptive change +10.04%.
Selected wape_pct: validation 97.176040, final 91.519204; descriptive change -5.82%.

These periods differ in season and realized sales. Differences are descriptive, not causal or statistically significant findings. Forecast instances share targets across origins and overlapping histories; their row count is not an independent sample size.

### Predefined point diagnostics

| model | subset | row_count | actual_mean | prediction_mean | absolute_error_units | absolute_error_contribution_pct |
| --- | --- | --- | --- | --- | --- | --- |
| seasonal_naive | zero_actual | 7081 | 0.0000 | 9.1284 | 64638.0000 | 6.4876 |
| seasonal_naive | positive_actual | 20919 | 43.0771 | 36.3217 | 931688.0000 | 93.5124 |
| seasonal_naive | Saturday | 4000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| weekday_mean | zero_actual | 7081 | 0.0000 | 9.1615 | 64872.2500 | 7.8661 |
| weekday_mean | positive_actual | 20919 | 43.0771 | 36.8046 | 759834.7500 | 92.1339 |
| weekday_mean | Saturday | 4000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |

Zero/positive subsets partition rows; Saturday overlaps those subsets. Error contributions therefore must not all be summed together.

### Per-SKU 80% interval failures

Below nominal: **41/100 SKUs**; minimum 54.6429%, median 82.1429%.

| sku | coverage_pct | mean_width | mean_interval_score | miss_below_count | miss_above_count |
| --- | --- | --- | --- | --- | --- |
| 22386 | 54.6429 | 130.6625 | 570.9634 | 75 | 52 |
| 22147 | 55.0000 | 37.0665 | 462.8424 | 88 | 38 |
| 21790 | 57.1429 | 79.5385 | 354.9608 | 58 | 62 |
| 21166 | 60.0000 | 65.2787 | 271.5840 | 62 | 50 |
| 22149 | 60.0000 | 37.0080 | 407.4786 | 77 | 35 |

### Per-SKU 95% interval failures

Below nominal: **42/100 SKUs**; minimum 72.8571%, median 96.0714%.

| sku | coverage_pct | mean_width | mean_interval_score | miss_below_count | miss_above_count |
| --- | --- | --- | --- | --- | --- |
| 22149 | 72.8571 | 88.2942 | 1219.1853 | 61 | 15 |
| 22386 | 75.0000 | 293.1468 | 1081.5218 | 54 | 16 |
| 82583 | 75.3571 | 109.6919 | 807.0812 | 53 | 16 |
| 22147 | 79.2857 | 79.6326 | 1515.1362 | 50 | 8 |
| 22138 | 82.8571 | 50.2586 | 385.7050 | 18 | 30 |

### Largest selected-method per-SKU MASE (diagnostic table, not plot selection)

| sku | macro_mase | mae | actual_units | bias_pct |
| --- | --- | --- | --- | --- |
| 22147 | 3.2883 | 57.5304 | 10729 | -8.7939 |
| 22149 | 2.9740 | 52.0973 | 8795 | -3.1097 |
| 22138 | 1.9737 | 21.5125 | 8303 | -43.0025 |
| 82583 | 1.9503 | 40.6661 | 10734 | -28.3399 |
| 21790 | 1.7379 | 57.3768 | 19936 | -23.0212 |

The saved forecasts retain every zero and extreme order. These descriptive failures do not justify removing observations, changing weekdays or adjusting intervals after evaluation.

## Integrity, calibration and execution

Calibration unchanged: True. Missing calibration group/level rows: 0. Nonfinite point predictions: 0. Implementation defects during this run: [].

Each origin receives only strictly prior sales. Already observed validation and earlier final-period sales refresh historical inputs; no future horizon actuals enter issued forecasts. Unscored point forecasts and intervals are saved and hashed before actuals are joined. Quantiles were never refitted; all calibration targets predate 2011-06-06.

Calibration retains 185,584 residual instances, 48,496 unique SKU/target dates and 6,628 SKU/origin groups. Per SKU/horizon-week group: 371–469 residuals and unique dates, 53–67 origins. Target dates repeat across horizon-week groups; residuals are not independent. Group counts and quantiles remain in the original calibration artifacts.

Loading 0.175s; point/interval issuance and saving 4.241s; scoring/saving 2.541s; full evaluation before report/manifest 8.550s. These are local CPU wall times, not general benchmarks.

Integrity/leakage checks and outcomes are recorded in the companion verification record. The results manifest hashes every artifact, report and plot. The command refuses overwrite; repeats verify hashes and display saved metrics, without forecasting/scoring again. A started incomplete run is refused. Any post-unblinding correction must preserve originals and receive an explicit defect log; no correction is present in this release.

## Representative plots

Predefined original-training volume ranks 1/50/100: **21212, 21791, 21533**, fixed origin 2011-11-07. Final error did not select these examples.

![Representative final forecasts](../reports/generated/final_evaluation/representative_forecasts.png)

![Final interval coverage](../reports/generated/final_evaluation/coverage_diagnostics.png)

## What the first release supports

A reproducible offline reference for 28-day daily observed-positive-sales forecasts over this bounded historical 100-SKU cohort, with explicit errors, frozen scales, auditable history policy and experimental daily uncertainty bands. It supports honest portfolio demonstrations and a foundation for separately specified inventory scenarios.

It does not establish uncensored demand, stock availability, production readiness, causal effects, future-season accuracy, calibrated per-SKU/weekday coverage, or inventory/service/cost benefits. It has no API/dashboard. These intervals are not confidence intervals and have no conformal/finite-sample guarantee. Do not sum daily bounds as a calibrated 28-day total interval; joint/aggregate uncertainty requires another method.

The final period is now consumed as evaluation evidence. Future point/uncertainty changes constitute a new development version and need new genuinely held-out evidence. A suitable next milestone is a clearly labelled inventory-policy simulation with explicit lead-time, cost and stock assumptions; it must not turn this consumed test into fresh model-selection evidence.

## Commands

```powershell
.\.venv\Scripts\python.exe -m retail_forecasting freeze-final-evaluation
.\.venv\Scripts\python.exe -m retail_forecasting final-evaluation
.\.venv\Scripts\python.exe scripts/validate_final_evaluation.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
