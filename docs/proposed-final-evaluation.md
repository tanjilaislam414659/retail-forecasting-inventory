# Frozen final-evaluation specification — Milestone 7

Finalized before final-outcome access under the user's Milestone 7 authorization.
This document replaces the earlier proposal. `configs/final-evaluation.json` is
its executable configuration. The selected first-release point method is the
existing eight-week weekday mean. Seasonal naive is a fixed reference, never a
test-based model-selection option. Unchanged original-training empirical
historical-error daily prediction intervals are **experimental**.

## Data and issue policy

Preserve all 100 SKUs, preparation rules, daily frequency, 28-day horizon,
training-only onset mask (484 leading dates across 10 SKUs) and original-training
lag-seven MASE scales. SKU 21166 retains 2009-12-07 because its qualifying Dec 1
sale predates the study, although its first positive sale within the study is
Dec 8. Onset dates are modelling assumptions, not verified listing/availability.

Use ten Monday origins from **2011-09-05 through 2011-11-07**, seven days apart.
Each forecasts origin through origin + 27 days. Last targets are respectively
Oct 2, 9, 16, 23, 30; Nov 6, 13, 20, 27; Dec 4. All targets precede
**2011-12-05**. Expect **28,000 instances per point method**, **9,100 unique
SKU/target pairs** and 28,000 daily intervals per nominal level.

At each issue date use only observations strictly before that origin, including
already observed validation and earlier test sales. Require complete preceding
56-day retained history for weekday mean. Seasonal naive repeats the last seven
calendar days. Generate all predictions at origin without recursive updates.
Save point forecasts and interval endpoints without actuals, then join targets
for scoring. No calibration fitting function is called. Quantiles from calibration
targets strictly before 2011-06-06 remain unchanged.

## Frozen reporting and examples

Primary point metric: equal-SKU macro MASE using original-training scales.
Secondary: MAE, pooled WAPE, signed bias in units (prediction minus actual), and
relative bias = 100 times summed signed error divided by summed actual sales.
Report both methods overall, by SKU, origin and horizon week; descriptive relative
changes and per-SKU MASE wins/ties/losses (absolute tie tolerance 1e-10).
Zero actual totals make WAPE/relative bias undefined. Any zero MASE scale makes
the containing macro metric undefined. No epsilon or silent product exclusion.

For 80% and 95% daily intervals report inclusive coverage, mean width, mean interval
score, below/above misses, missing counts, zero-width and point-outside counts.
Report overall, by SKU, horizon week, weekday and origin. Score = width +
(2/alpha) times distance outside bounds. Missing groups have explicit statuses;
aggregates containing missing intervals are undefined. Preserve max(0, point +
residual quantile), without rounding, weekday rules or forced point containment.

Show saved validation and final results separately. Predefined diagnostic subsets
are zero sales, positive sales and Saturday, with mean predictions and absolute
error contributions. Representative plots use original-training positive-volume
ranks **1, 50 and 100**, ties by SKU ascending, at fixed origin **2011-11-07**,
with 28 preceding days, selected/reference forecasts, actuals and both daily bands.
Coverage plots show all horizon weeks and weekdays. No example is chosen by final
error. All forecast and metric tables retain units and denominator status fields.

## Known limitations frozen before evaluation

Validation weekday mean: macro MASE 0.7581087857, MAE 26.76550893, WAPE 97.17603956%,
relative bias -2.58534283%. Interval coverage 83.8857%/95.4464% masks Thursday
coverage 69.275%/88.90%; 26/33 SKUs under nominal 80%/95% coverage. Minimum per-SKU
coverage is 57.1429%/78.2143%. The 95% mean width is 149.7092 units. Broad bands or
high marginal coverage do not establish useful inventory decisions. Weekdays are
pooled; overlapping horizons and residuals are dependent; later-season sales may
differ. Final outcomes cannot change model, quantiles, scales, cohort or protocol.

Observed sales are not latent demand: stockouts, listing and availability are
unknown. These are experimental historical-error prediction intervals, never
confidence intervals or conformal/finite-sample guarantees. Do not sum daily
endpoints and claim calibrated total-28-day or joint uncertainty. Dependent rows
do not support significance claims based on their count.

## Freeze, one execution and integrity

`freeze-final-evaluation` creates an exclusive results directory and records UTC
time, config/document hashes, project code/tests/check scripts, inputs, calibration,
earlier outputs and software versions before reading final sales. Byte hashing
does not inspect outcomes. Git is local and uncommitted: content hashes, not an
invented commit, identify the release. The completion manifest hashes the freeze.

`final-evaluation` verifies the freeze, exclusively creates a start record, reads
the sales panel, and performs one evaluation. Every output uses exclusive creation.
A complete repeat verifies inputs/code and all saved artifacts and reports saved
summaries without forecasting or scoring again. An interrupted started run is
refused rather than overwritten. Genuine defects discovered after unblinding must
be logged, their impact explained, and original artifacts preserved before any
separate correction. Exceptions are recorded without silent retries. No tuning,
model switching, recalibration, preparation changes or deployment work is allowed.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m retail_forecasting freeze-final-evaluation
.\.venv\Scripts\python.exe -m retail_forecasting final-evaluation
.\.venv\Scripts\python.exe scripts/validate_final_evaluation.py
```

Repeat execution verifies/reports only. Generated data, manifests and plots remain
outside Git; specifications, code and the authored final report belong in Git.
