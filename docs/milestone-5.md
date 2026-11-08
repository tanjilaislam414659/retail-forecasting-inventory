# Milestone 5: one fixed pooled Poisson boosting experiment

**Do not replace weekday mean.** The fixed candidate's primary validation macro
MASE is **0.778805**, versus **0.758109** for weekday mean (**2.73% worse**).
It improves on Ridge's **0.826062**, but MAE/WAPE remain **2.60% worse** than weekday
mean. The [complete measured report](boosting-comparison.md) contains all origin,
horizon-week, training/validation and diagnostic tables.

This is **validation-informed model development**: prior Ridge validation results
informed the model/loss choice. Validation is not an untouched final assessment.
No final-test evaluation, parameter search, second candidate, Saturday-zero rule,
hurdle model, manual target transformation or reweighting was performed.

## Fixed specification and reproduction

The [specification](boosting-experiment-spec.md) and
[`configs/boosting.json`](../configs/boosting.json) were recorded at **2026-11-01
19:11:38 UTC**. The single fit completed at **19:16:36 UTC**. A specification
snapshot and hashes are saved with the experiment.

From the repository root, using the unchanged project environment:

```powershell
.\.venv\Scripts\python.exe -m retail_forecasting boosting
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
.\.venv\Scripts\python.exe scripts\validate_boosting.py
.\.venv\Scripts\python.exe scripts\validate_ridge.py
.\.venv\Scripts\python.exe scripts\validate_baselines.py
.\.venv\Scripts\python.exe scripts\validate_data.py
.\.venv\Scripts\python.exe scripts\verify.py
.\.venv\Scripts\python.exe -m pip check
```

No downloads or dependency additions are required; sklearn **1.7.2** and the
existing lock/environment are reused. The actual-data candidate was fitted once.
Later `boosting` invocations reuse a matching model after signature/hash/version
checks; a mismatch is rejected instead of silently refitting. Synthetic test fits
use toy data only and are not additional retail experiments.

## Preserved data and categorical handling

The experiment reads the exact saved Ridge tables: **185,584 training examples**
and **28,000 validation feature rows**. No sales feature is recalculated or added.
The 100 SKUs, 484-row onset exclusion, SKU 21166 distinction, splits, original
training-only MASE scales, ten Monday validation origins and 28-day horizon remain
unchanged. Every numeric feature value matches the saved Ridge feature value.
Zeros, extreme orders and uniform sample weights are retained.

The seven numeric features are used without scaling. SKU, target weekday and
target month are unordered pandas categoricals. `TrainingCategories` learns only
training labels (100/7/12 categories), preserves numeric columns unchanged, and
rejects unknown labels without extending the dictionaries. HistGradientBoosting's
`categorical_features='from_dtype'` marks those three fields for native categorical
splits. SKU codes are category labels, not ordered numeric measurements.

The exact estimator parameters are loss=poisson, learning_rate=0.05, max_iter=200,
max_leaf_nodes=15, min_samples_leaf=50, l2_regularization=1.0,
early_stopping=False, random_state=42. Other defaults are pinned by sklearn 1.7.2.
No early-stopping holdout or validation refit occurs. The fit uses one local thread.
Poisson's internal log link is part of the estimator; targets remain sales units.
No clipping or rounding is applied.

## Evaluation meaning and observed tradeoffs

The candidate, saved Ridge and saved weekday mean use exactly the same validation
keys/actuals. Each model has 28,000 scored instances, covering **9,100 unique
SKU/target-day pairs**. Overlapping horizons repeat some dates up to four times;
errors are dependent, and no independent-sample significance claim is made.

Primary per-SKU MASE result versus weekday mean: **37 wins / 0 ties / 63 losses**.
Versus Ridge: **74 wins / 0 ties / 26 losses**. Ties use absolute tolerance 1e-10
for numerical equality only. Frozen scales and undefined-denominator conventions
are unchanged; no epsilon or dropped SKU.

The candidate loses to weekday mean in all four horizon weeks on macro MASE.
It improves the primary metric at **3 of 10 origins** (27 June, 4 July and 11 July),
but not overall. Relative bias is **+11.06%**, compared with weekday mean's **−2.59%**.
The full origin tables report MAE, WAPE and bias as well as primary MASE.

On **8,699 zero-sales instances**, prediction means are **12.1667** candidate,
**15.0657** Ridge and **9.2812** weekday mean. Candidate zero-sales absolute error
is **105,837.83 units**, **13.76%** of its total absolute error. On **19,301 positive
sales instances**, candidate mean prediction is **38.8932** against actual mean
**39.9572**; absolute error is **663,098.40 units**, **86.24%** of its total.

All **4,000 Saturday instances** have zero recorded sales. Candidate mean prediction
is **0.015009**, with **60.03 units** of absolute error (**0.0078%** of its total),
versus Ridge **6.5886 / 26,354.30 units** and weekday mean **0 / 0 units**. Saturdays
are a subset of zero-sales cases; do not add their errors again. These observations
do not prove closure or availability. Native interactions improve this documented
Ridge failure without an explicit rule, but other zero-sales errors remain.

Changing both model class and training loss does **not** isolate why errors change.
Poisson loss does not directly optimize equal-SKU macro MASE. Preserve these
results rather than inferring a causal benefit of a particular component.

## Training performance and numerical behavior

Training results are **in-sample** predictions from the fully fitted estimator on
its own examples; they are not held-out performance. They use a different target
date distribution and repeated-origin weights from validation.

| Evaluation | Macro MASE | MAE | WAPE | Relative bias |
| --- | ---: | ---: | ---: | ---: |
| Original-training in-sample | 0.745918 | 26.4884 | 85.10% | +0.017% |
| Walk-forward validation | 0.778805 | 27.4620 | 99.70% | +11.06% |

Fit/prediction warnings: **none**. Nonfinite predictions: **0**. Nonpositive
predictions: **0**. Training predictions range **0.012068–923.067173**; validation
predictions **0.013154–527.423005**. These are unmodified predictions. No numerical
repair or alternative fit was needed.

## Separate timing measurements

All values are wall seconds from this run, with one local thread:

| Operation | Seconds |
| --- | ---: |
| New sales-feature construction | None performed; saved values reused |
| Loading saved feature rows | 0.406 |
| Learning/applying training category dictionaries | 0.096 |
| Single estimator fit | 2.849 |
| Validation prediction, including category conversion | 0.368 |
| Training in-sample prediction | 2.594 |
| Full command, including metrics/plots/checks | 11.714 |

Historical Ridge feature-construction times were **23.037s training / 4.129s
validation**; those are previous-run measurements, not recomputation in this run.
CPU times and original fit timing remain in the summary/fit record. These are
observed timings, not a hardware-independent benchmark.

## Saved artifacts and checks

| Location | Contents |
| --- | --- |
| `models/boosting/pipeline.joblib` | Saved training-category transformer and single native-categorical Poisson estimator. |
| `models/boosting/fit-record.json` | Fit count/timestamp, config/input/code/version signatures, original fit/category times, warnings and model hash. |
| `data/boosting/experiment-specification.json` | Exact pre-fit configuration snapshot. |
| `data/boosting/validation_forecasts.csv.gz` | 28,000 candidate model/SKU/origin/target/horizon/actual/predicted rows. |
| `data/boosting/training_in_sample_predictions.csv.gz` | 185,584 clearly labelled in-sample predictions. |
| `data/boosting/metrics_*.csv` | All three models by model, SKU, origin, horizon week and joint combinations. |
| `data/boosting/comparison_to_weekday_*.csv` | Relative changes, bias differences and SKU-MASE outcomes against saved weekday mean. |
| `data/boosting/comparison_to_ridge_by_sku.csv` | Per-SKU comparison against saved Ridge. |
| `data/boosting/diagnostics_*.csv` | Zero/positive-sales and weekday counts, means, absolute-error sums and contribution shares. |
| `data/boosting/training_vs_validation.csv` | In-sample training and walk-forward validation metrics with explicit evaluation labels. |
| `data/boosting/categories.json`, `numerical-status.json` | Training dictionaries, native categorical mask, iteration count, prediction ranges/counts and warnings. |
| `data/boosting/summary.json`, `manifest.json` | Measured totals/timings and input/output/code/config/version hashes. |
| `reports/generated/boosting/` | Representative forecasts and origin/horizon comparisons in PNG/SVG. |

All generated data, models and plots are ignored by Git. Forecast examples retain
original training-volume ranks 1/50/100, SKUs 21212/21791/21533, at 2011-08-08;
examples are not selected by validation errors.

**35 tests passed**, including the existing leakage/calendar/preprocessing tests
and six targeted tests for exact parameters/no early stopping, unordered native
categories with unchanged numerics, training-only category dictionaries, finite
positive predictions with retained zeros, saved-model reload consistency and
future-sales mutation invariance for the new estimator.

The independent candidate validator passes: preserved-artifact hashes, exact
saved feature rows, train-defined categories, native mask, all 200 iterations,
model reload predictions, matched comparison instances, training/validation metrics,
and diagnostic absolute-error contributions. Original validators are also run;
none fits a model or scores final test.

Final checks recorded on 2026-11-01: **35/35 tests passed**; candidate, Ridge,
baseline and original data validators passed; installation smoke checks passed;
`pip check` reported no broken requirements. Git ignore checks cover the saved
model, training/validation predictions and plots. All previous result hashes match.

**Decision: retain weekday mean.** This candidate improves on Ridge but does not
meet the predefined primary comparison criterion. No second model was tried.
