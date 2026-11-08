# Milestone 5: one fixed pooled Poisson boosting experiment

**Validation-informed model development**, following documented Ridge failures. The model class and loss were selected after viewing prior validation results. This is not an untouched final assessment; final test remains unevaluated.
Primary comparison versus saved weekday mean: **loss**, macro MASE relative change **+2.73%**. Exactly one candidate fit; no hyperparameter search or automatic replacement model.
The [fixed specification](boosting-experiment-spec.md) and `configs/boosting.json` were recorded before fitting. All prior results and saved feature rows are hash-verified and unchanged.

## Fixed inputs and estimator

Same **185,584 original-training examples**, **28,000 validation instances**, 100 SKUs, onset mask, ten origins, daily frequency, 28-day horizon and frozen seven-day MASE scales. Training targets end before 2011-06-06; validation targets end on 2011-09-04. Existing Ridge feature values are loaded verbatim, including zeros and extreme orders.
HistGradientBoostingRegressor uses loss=poisson, learning_rate=0.05, max_iter=200, max_leaf_nodes=15, min_samples_leaf=50, l2_regularization=1.0, early_stopping=False and random_state=42. Other estimator defaults are pinned by sklearn 1.7.2. Unordered SKU/weekday/month categories are learned from training rows only, with native categorical splits; numeric scaling is absent. Targets retain original units and uniform weights.
No Saturday rule, hurdle stage, manual target transformation, weighting, clipping or prediction rounding. Later origins use sales already observed before their issue date through the preserved feature rows, without refitting. The saved model is reused on matching future invocations.
Poisson loss is the training objective, not macro MASE. Its internal log link belongs to the estimator; no manual log target is added. Changing model class and loss together does **not** identify which change causes any gain. [Official estimator documentation](https://scikit-learn.org/1.7/modules/generated/sklearn.ensemble.HistGradientBoostingRegressor.html).

## Walk-forward validation results

| Model | Macro MASE (primary) | MAE | WAPE | Mean signed bias | Relative bias |
| --- | ---: | ---: | ---: | ---: | ---: |
| hist_poisson | 0.778805 | 27.4620 | 99.70% | +3.0465 | +11.06% |
| ridge | 0.826062 | 27.8381 | 101.07% | +3.2685 | +11.87% |
| weekday_mean | 0.758109 | 26.7655 | 97.18% | -0.7121 | -2.59% |

Relative changes are 100 × (candidate / weekday mean − 1); negative means lower error.
Macro MASE: **+2.73%**; MAE: **+2.60%**; WAPE: **+2.60%**. Relative-bias shift: **+13.65 percentage points**. Absolute bias magnitude change: **+327.83%**.
Per-SKU MASE versus weekday mean: **{'win': 37, 'tie': 0, 'loss': 63, 'undefined': 0}**. Versus Ridge: **{'win': 74, 'tie': 0, 'loss': 26, 'undefined': 0}**. Ties use absolute tolerance 1e-10 only for equality.
The score pools 28,000 forecast instances per model, corresponding to 9,100 distinct SKU/target dates. Overlapping horizons repeat some dates at up to four origins; these errors are dependent. Frozen scales and all undefined-denominator conventions are preserved, without epsilon or dropped SKUs.

### Forecast origins

| Origin | Model | Macro MASE | MAE | WAPE | Relative bias |
| --- | --- | ---: | ---: | ---: | ---: |
| 2011-06-06 | hist_poisson | 0.79389 | 27.095 | 110.17% | +37.62% |
| 2011-06-06 | ridge | 0.87988 | 27.176 | 110.50% | +37.17% |
| 2011-06-06 | weekday_mean | 0.74112 | 25.288 | 102.82% | +13.15% |
| 2011-06-13 | hist_poisson | 0.81050 | 28.166 | 109.55% | +25.57% |
| 2011-06-13 | ridge | 0.88638 | 28.401 | 110.46% | +26.23% |
| 2011-06-13 | weekday_mean | 0.77357 | 26.891 | 104.59% | +9.20% |
| 2011-06-20 | hist_poisson | 0.76166 | 26.690 | 112.28% | +29.07% |
| 2011-06-20 | ridge | 0.81215 | 26.670 | 112.19% | +28.04% |
| 2011-06-20 | weekday_mean | 0.74099 | 25.715 | 108.18% | +14.74% |
| 2011-06-27 | hist_poisson | 0.75026 | 25.672 | 99.67% | +9.97% |
| 2011-06-27 | ridge | 0.79484 | 26.032 | 101.07% | +11.61% |
| 2011-06-27 | weekday_mean | 0.75854 | 25.898 | 100.55% | +8.74% |
| 2011-07-04 | hist_poisson | 0.74014 | 24.382 | 91.29% | +0.87% |
| 2011-07-04 | ridge | 0.77859 | 25.294 | 94.71% | +5.88% |
| 2011-07-04 | weekday_mean | 0.75818 | 25.488 | 95.44% | +3.54% |
| 2011-07-11 | hist_poisson | 0.72778 | 25.468 | 93.68% | +3.63% |
| 2011-07-11 | ridge | 0.76427 | 26.353 | 96.93% | +8.59% |
| 2011-07-11 | weekday_mean | 0.74547 | 26.554 | 97.67% | -0.27% |
| 2011-07-18 | hist_poisson | 0.77732 | 27.527 | 89.47% | -6.84% |
| 2011-07-18 | ridge | 0.80641 | 27.990 | 90.98% | -5.97% |
| 2011-07-18 | weekday_mean | 0.77159 | 28.019 | 91.07% | -16.76% |
| 2011-07-25 | hist_poisson | 0.81554 | 29.697 | 95.45% | +0.08% |
| 2011-07-25 | ridge | 0.85017 | 30.101 | 96.75% | -0.21% |
| 2011-07-25 | weekday_mean | 0.79189 | 28.578 | 91.86% | -20.76% |
| 2011-08-01 | hist_poisson | 0.82469 | 31.254 | 97.56% | +2.15% |
| 2011-08-01 | ridge | 0.85806 | 31.402 | 98.02% | +0.47% |
| 2011-08-01 | weekday_mean | 0.78704 | 29.210 | 91.18% | -19.93% |
| 2011-08-08 | hist_poisson | 0.78628 | 28.669 | 103.14% | +19.18% |
| 2011-08-08 | ridge | 0.82988 | 28.962 | 104.20% | +17.95% |
| 2011-08-08 | weekday_mean | 0.71269 | 26.014 | 93.59% | -4.84% |

### Horizon weeks

| Week | Model | Macro MASE | MAE | WAPE | Relative bias |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1 | hist_poisson | 0.78869 | 27.254 | 99.70% | +12.75% |
| 1 | ridge | 0.83868 | 27.525 | 100.69% | +13.43% |
| 1 | weekday_mean | 0.76524 | 26.225 | 95.93% | -1.85% |
| 2 | hist_poisson | 0.78086 | 27.662 | 100.65% | +11.52% |
| 2 | ridge | 0.82727 | 27.964 | 101.75% | +12.29% |
| 2 | weekday_mean | 0.75589 | 26.784 | 97.46% | -2.37% |
| 3 | hist_poisson | 0.77386 | 27.544 | 99.03% | +9.73% |
| 3 | ridge | 0.81834 | 27.906 | 100.34% | +10.42% |
| 3 | weekday_mean | 0.75341 | 26.945 | 96.88% | -3.53% |
| 4 | hist_poisson | 0.77181 | 27.389 | 99.45% | +10.26% |
| 4 | ridge | 0.81996 | 27.957 | 101.51% | +11.36% |
| 4 | weekday_mean | 0.75789 | 27.108 | 98.43% | -2.58% |

## Zero-sales, positive-sales and Saturday diagnostics

These retrospective groups describe errors; no group-specific prediction rule was introduced. Absolute-error shares use each model's total validation absolute error.

| Group | Model | Instances | Actual mean | Prediction mean | Absolute-error sum | Share of model error |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Positive sales | hist_poisson | 19,301 | 39.9572 | 38.8932 | 663,098.40 | 86.24% |
| Zero sales | hist_poisson | 8,699 | 0.0000 | 12.1667 | 105,837.83 | 13.76% |
| Positive sales | ridge | 19,301 | 39.9572 | 37.9086 | 648,408.96 | 83.19% |
| Zero sales | ridge | 8,699 | 0.0000 | 15.0657 | 131,056.89 | 16.81% |
| Positive sales | weekday_mean | 19,301 | 39.9572 | 34.7411 | 668,697.50 | 89.23% |
| Zero sales | weekday_mean | 8,699 | 0.0000 | 9.2812 | 80,736.75 | 10.77% |
| Saturday (subset of zeros) | hist_poisson | 4,000 | 0.0000 | 0.015009 | 60.03 | 0.01% |
| Saturday (subset of zeros) | ridge | 4,000 | 0.0000 | 6.588576 | 26,354.30 | 3.38% |
| Saturday (subset of zeros) | weekday_mean | 4,000 | 0.0000 | 0.000000 | 0.00 | 0.00% |

Saturday rows overlap the zero-sales group, so their errors must not be added again. Observed Saturday zeros do not prove closure or availability. The model can learn category interactions, but any causal interpretation of changed errors would require a separate design.

## Training versus validation: different evaluation meanings

| Evaluation | Rows | Macro MASE | MAE | WAPE | Relative bias |
| --- | ---: | ---: | ---: | ---: | ---: |
| original-training in-sample | 185,584 | 0.745918 | 26.4884 | 85.10% | +0.02% |
| walk-forward validation | 28,000 | 0.778805 | 27.4620 | 99.70% | +11.06% |

Training is **in-sample**, using the fully fitted estimator on its own original-training examples. It is not held out or rolling-origin model evaluation, and it has different target-date weights/seasonal coverage from validation. A train/validation difference alone is not a causal measure of overfitting.

## Numerical behavior and timing

Numerical status: `{'training_nonfinite_predictions': 0, 'validation_nonfinite_predictions': 0, 'training_nonpositive_predictions': 0, 'validation_nonpositive_predictions': 0, 'training_prediction_min': 0.012067719609161443, 'training_prediction_max': 923.0671726055813, 'validation_prediction_min': 0.013153822393873913, 'validation_prediction_max': 527.4230048896894}`. Fit warnings: `[]`. Prediction warnings: `[]`. Predictions are not clipped or repaired; nonfinite/nonpositive values cause the experiment to stop.
New sales-feature calculations: **0**, because existing rows are reused. The historical Ridge construction timings were 23.037s for training and 4.129s for validation; those are prior-run measurements, not time spent recomputing features here.
Current saved-row loading: **0.406s wall / 0.406s CPU**. Original training-category preparation: **0.096s wall / 0.078s CPU**.
Single estimator fit: **2.849s wall / 2.781s CPU**. Validation prediction including category conversion: **0.368s wall / 0.375s CPU**. Training in-sample prediction: **2.594s wall / 2.578s CPU**. One local thread; no validation refit or early stopping.
Total command: 11.714s wall / 11.406s CPU. Saved fit reused in this invocation: False.

## Artifacts, plots and decision

Forecast examples retain original training-volume ranks 1, 50, 100: **21212, 21791, 21533**, at 2011-08-08. No validation-error-based example selection.
![Representative forecasts](../reports/generated/boosting/representative_forecasts.png)

![Origin and horizon comparisons](../reports/generated/boosting/validation_comparison.png)

`models/boosting/` contains the model and single-fit record. `data/boosting/` contains config snapshot, training in-sample and validation predictions, all metric/comparison tables, diagnostic sums/shares, category metadata, numerical status, summary and version/hash manifest. All generated artifacts are ignored by Git. [Protocol and reproducible commands](milestone-5.md).

**Recommendation: retain weekday mean as the current reference**, because this candidate does not improve primary validation macro MASE. Preserve the negative result; no alternate model was automatically tried.
