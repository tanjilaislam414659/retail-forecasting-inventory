# Fixed specification: pooled histogram gradient boosting with Poisson loss

Recorded **2026-11-01 19:11:38 UTC**, before fitting. Configuration:
[`configs/boosting.json`](../configs/boosting.json).

This is **validation-informed model development** following the documented Ridge
failures. The existing validation set has already informed the choice of model
class/loss; its results are not an untouched final assessment. Final test remains
unevaluated. No other candidate or parameter search is authorized.

## Fixed data and features

Load the exact saved `data/ridge/training_examples.csv.gz` and
`validation_features.csv.gz`, verifying their hashes. Preserve all **185,584**
original-training examples, **28,000** validation instances, 100 SKUs, onset mask,
feature definitions/values, original training-only MASE scales, ten origins and
28-day horizon. No feature regeneration, observation removal or reweighting.
Zeros and extreme orders remain in the original sales-unit target.

Use the same seven numeric fields (horizon day; means over 7/28/56 days; 28-day
population standard deviation and zero share; preceding-eight-occurrence weekday
mean), without scaling. SKU, target weekday and target month are **unordered
categoricals**, using labels/categories learned from training rows only. Use a
saved sklearn-compatible transformer to enforce those category dictionaries and
`categorical_features='from_dtype'` for native histogram-boosting splits. Category
codes are internal labels, never ordered SKU measurements. Reject unknown labels
rather than silently changing categories at prediction time.

## Fixed estimator and fitting policy

```text
HistGradientBoostingRegressor(
    loss="poisson", learning_rate=0.05, max_iter=200,
    max_leaf_nodes=15, min_samples_leaf=50, l2_regularization=1.0,
    early_stopping=False, random_state=42,
    categorical_features="from_dtype"
)
```

Other parameters retain sklearn 1.7.2 defaults. Fit once on the saved original
training examples with uniform weights (`sample_weight=None`) and one local
thread. No validation fit, early-stopping split, Saturday-zero rule, hurdle stage,
manual target transform, sample weighting or hyperparameter search. No clipping
or rounding is added. Persist the fitted pipeline/fit record and reuse a matching
saved fit on later command invocations.

Poisson loss is the **training objective**. Its internal log link is part of the
estimator, not a manual transformation of sales targets. It does not directly
optimize equal-SKU macro MASE. Changing the model class and loss together does not
identify which change causes any gain. The chosen estimator supports native
categoricals and Poisson loss: [official sklearn documentation](https://scikit-learn.org/1.7/modules/generated/sklearn.ensemble.HistGradientBoostingRegressor.html).

## Evaluation, diagnostics and timing

Primary: **macro MASE**. Secondary: MAE, pooled WAPE, signed bias (prediction minus
actual), relative bias. Reuse existing zero-denominator conventions: retain
undefined metric rows/statuses, with no epsilon or dropped SKU. Compare saved
weekday mean and saved Ridge on the identical 28,000 keys and actuals. Report
relative changes against weekday mean; per-SKU MASE wins/ties/losses use absolute
tolerance 1e-10 for ties only. Report by origin and horizon week, plus detailed
SKU/joint tables. Overlapping horizons repeat targets and create dependent errors.

Report zero-actual, positive-actual, Saturday and weekday groups with counts,
actual/prediction means, absolute-error sums and each group's percentage of total
absolute error. These are retrospective diagnostics, not rules used for prediction.

Report **in-sample training** metrics separately from walk-forward validation
metrics. Training predictions are made by the fully fitted estimator on its own
training examples; they are not held-out performance. Training-origin inputs remain
past-only, but the estimator itself has seen the full original training set.

No new sales-feature construction is needed: existing Ridge values are reused.
Record feature-row loading/checking, train-category preparation, fitting, training
prediction and validation prediction times separately, and cite original Ridge
feature-construction times as historical timings rather than new work. Count and
report warnings, numerical failures, nonfinite predictions and nonpositive values;
do not hide or repair them by changing the model specification.

Save the model, config/specification, forecasts, training predictions, metrics,
relative comparisons, diagnostics, version/hash provenance and plots. Plot the
same training-volume ranks 1/50/100 at the last prescribed validation origin, plus
origin/horizon comparisons. Verify native unordered category handling, future-sales
invariance, finite positive predictions and saved-model reload consistency.
