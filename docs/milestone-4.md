# Milestone 4: one pooled Ridge experiment

The single predefined Ridge **loses** to saved weekday mean on primary macro MASE:
**0.826062 versus 0.758109 (+8.96%)**. MAE/WAPE worsen **4.01%**. This result is
retained; no tuning or replacement experiment was run. See the generated
[comparison, tradeoffs and plots](ridge-comparison.md).

## Reproduce

Use the existing environment from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pip install --disable-pip-version-check -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pip install --disable-pip-version-check --no-build-isolation --no-deps -e .
.\.venv\Scripts\python.exe -m retail_forecasting ridge
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts\validate_ridge.py
.\.venv\Scripts\python.exe scripts\validate_baselines.py
.\.venv\Scripts\python.exe scripts\validate_data.py
.\.venv\Scripts\python.exe scripts\verify.py
.\.venv\Scripts\python.exe -m pip check
```

No acquisition, preparation or baseline regeneration is required. Dependencies
remain isolated in `.venv`, with scikit-learn 1.7.2 and exact dependencies added
to `requirements-lock.txt`. No global system settings were changed.

The actual retail-data pipeline was fitted **once**, on original-training examples.
The fitted artifact and signature record are preserved. Repeating `ridge` rebuilds
feature/report evidence and **reuses the saved fit**, after checking its config,
training examples, feature/model code, versions and pipeline hash. A mismatched
fit is rejected rather than silently overwritten or retrained. Synthetic test
fits use toy arrays only and are not additional retail experiments.

## Specification recorded before fitting

The [specification document](ridge-experiment-spec.md) and
[`configs/ridge.json`](../configs/ridge.json) were recorded at **2026-11-01
18:29:46 UTC**. The original fit completed at **18:35:47 UTC**. A snapshot is saved
under `data/ridge/experiment-specification.json`, with config/document hashes in
the experiment manifest. Primary metric is macro MASE; other metrics and clipping
were fixed before the result was known.

## Preserved data and examples

- Same 100 SKUs and original study dates; the audit panel is unchanged.
- Same onset mask: 484 leading zeros excluded across 10 SKUs; SKU 21166's
  2009-12-07 zero remains because it first qualified on 2009-12-01.
- Same frozen training-only seven-day MASE scales. No new scaling interval.
- Same ten validation Monday origins, 2011-06-06 through 2011-08-08, horizon 28
  days, targets ending 2011-09-04. Final test remains unevaluated.

Training uses **185,584 supervised rows**: **6,628 SKU/origin groups × 28 horizon
days**, across 100 SKUs. Each SKU contributes **53–67** eligible Monday origins,
depending on its retained history. The earliest origin is **2010-02-01**; the last
is **2011-05-09**, whose last target is **2011-06-05**. All 56 preceding calendar
days must be retained and available; the entire target window must be in original
training. No origin is selected using validation errors.

Each row is keyed by SKU, origin and horizon day; target date is origin + day − 1.
Target is untransformed positive sales units. All examples have equal row weight;
overlapping training windows repeat some targets. This is not equal-SKU MASE
weighting and may favor products/periods with more or larger training observations.

## Features, preprocessing, model and clipping

Numeric features: horizon day; origin-available mean sales over 7, 28 and 56 days;
28-day population standard deviation (`ddof=0`); 28-day zero share; target weekday's
mean over its eight occurrences in the preceding 56 days. Categoricals: SKU,
target weekday and target month. Future calendar fields are known at issue time.

Every sales-derived feature uses dates **strictly before origin**, even for days
8–28. A missing required calendar day is an error. No realized future price,
target-period sales, additional interactions, target transforms, sample weights
or outlier removal is introduced.

The scikit-learn Pipeline contains a ColumnTransformer with numeric StandardScaler
and dense OneHotEncoder (`drop=None`, `handle_unknown='ignore'`), followed by
Ridge (`alpha=1.0`, `solver='cholesky'`, intercept enabled). Preprocessors learn
from training feature rows only. The fitted transform has **126 columns**: seven
numeric features, 100 SKU indicators, seven weekday indicators and 12 month indicators.
The solver uses one BLAS thread via a process-local context.

Ridge minimizes sum squared error plus alpha times squared coefficient norm;
the intercept is not penalized. Evaluation uses absolute error and equal-SKU macro
MASE. Large orders therefore receive more influence in the fitted objective than
in equal-SKU absolute-error evaluation. This mismatch is documented, not tuned away.

Predictions stay fractional in original units. Raw negatives are clipped to zero,
as specified beforehand. **3,089/28,000 (11.03%)** validation predictions are clipped.
Raw values and clipping flags remain available for audit. Clipping raises aggregate
predictions by **30,279.17 units** and mean bias from **+2.1871** to **+3.2685** units.

## Comparison and failure analysis

Exactly **28,000 Ridge forecasts** are matched one-to-one against the saved
weekday-mean SKU/origin/target keys and actuals. The comparator is not refitted or
recalculated. Earlier validation sales update later origins' features, without
updating pipeline coefficients, preprocessing or MASE scales.

Relative error change = 100 × (Ridge / baseline − 1); negative is better. Signed
bias uses prediction − actual. Bias comparisons report signed differences,
percentage-point changes and changes in absolute magnitude, so a sign reversal
is not misleadingly presented as an ordinary relative error reduction.

SKU MASE result: **30 wins, 0 ties, 70 losses**, using absolute tie tolerance
1e-10 solely for floating-point equality. Ridge also loses in all four horizon
weeks. Mean relative bias shifts from **−2.59%** to **+11.87%**. There is no overall
secondary-metric benefit that offsets the primary loss; there are gains for some
individual SKUs. Per-SKU/origin/week tables preserve those differences.

Observed failure: on **8,699** zero-actual forecast instances, average prediction
is **15.07 units for Ridge versus 9.28 for weekday mean**. All **4,000 Saturday
instances** have zero actual sales, but Ridge averages **6.59 units** versus zero
for weekday mean. This is not proof of closure or availability. The additive
structure permits positive SKU offsets despite near-zero weekday activity;
squared-error training and shared slopes are plausible contributors. The single
experiment does not isolate causal explanations.

Overlapping horizons repeat targets at up to four issue dates. Each model's 28,000
instances cover 9,100 unique SKU/target-day pairs; differences are descriptive and
do not assume independent forecast errors. Undefined WAPE rows remain present:
14 model/SKU/origin rows and 114 model/SKU/origin/week rows across both models.
All original scales are positive, so no MASE group is undefined. No epsilon or
SKU dropping is used.

## Saved artifacts

| Location | Contents |
| --- | --- |
| `models/ridge/pipeline.joblib` | The single fitted preprocessing + Ridge pipeline. Load only this locally generated artifact with its recorded matching dependencies. |
| `models/ridge/fit-record.json` | Fit count, timestamp, original fit wall/CPU time, training/config/code/version signatures and pipeline hash. |
| `data/ridge/experiment-specification.json` | Exact configuration snapshot. |
| `data/ridge/training_examples.csv.gz` | All 185,584 supervised rows, targets and historical-window boundaries. |
| `data/ridge/validation_features.csv.gz` | All 28,000 validation feature rows and matched actuals. |
| `data/ridge/validation_forecasts.csv.gz` | Ridge origin/target/horizon/actual, raw prediction, clipped prediction and clipping flag. |
| `data/ridge/metrics_*.csv` | Both models, by model/SKU/origin/horizon week and joint combinations, with explicit undefined/clipping counts. |
| `data/ridge/comparison_*.csv` | Paired values, differences, relative changes and primary-metric win/tie/loss. |
| `data/ridge/diagnostics_*.csv` | Measured errors on zero/nonzero actuals and by target weekday. |
| `data/ridge/preprocessing.json`, `coefficients.csv` | Fitted training means/scales/categories and transformed-feature coefficients; coefficients are not causal effects. |
| `data/ridge/summary.json`, `manifest.json` | Measured counts/times, diagnostics, config/code/version and input/output hashes. |
| `reports/generated/ridge/` | PNG/SVG representative forecasts and SKU-MASE/horizon comparisons. |

All generated data, models and plots are ignored by Git. Forecast examples use
the unchanged training-volume rank rule (1, 50, 100), SKUs **21212, 21791, 21533**,
at origin 2011-08-08, without validation-error-based example selection.

## Checks and decision

**29 tests passed**, including nine new Ridge tests for hand-calculated features,
date alignment, zero share/std conventions, SKU-specific training eligibility,
target boundaries, train-only preprocessing and unknown categories, walk-forward
refresh, relative metric conventions, and future-sales mutation. Changing sales
on or after an origin leaves its features and fitted-pipeline predictions unchanged.

The independent validator reconstructs every training/validation sales feature,
checks all eligible origins and training targets, verifies scaler/encoder statistics
against training rows only, reproduces saved predictions from the persisted fit,
checks clipping and metrics, and verifies protected data hashes without fitting.
Original baseline/data validators remain available and final test is not scored.

Observed final checks on 2026-11-01: **29/29 tests pass**, independent Ridge and
baseline validators pass, original raw/prepared-data validation passes, installation
smoke checks pass, and `pip check` reports no broken requirements. Git ignore checks
cover generated examples/forecasts, the fitted model and plots. Replaying the Ridge
command reused the original fit with unchanged checksum and fit count one.

Retain **weekday mean** as the current reference. A next milestone should first
formalize the observed weekday/zero-sales and SKU-level failure patterns, then
predefine one targeted modelling change. No additional candidate has been fitted
in this milestone, and no final-test or deployment work is authorized yet.
