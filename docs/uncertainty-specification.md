# Fixed uncertainty specification: first-release weekday mean

Recorded **2026-11-01 19:49:57 UTC**, before quantile or validation-coverage
calculation. The first-release point model is frozen in
[`configs/first-release.json`](../configs/first-release.json). Exact method:
[`configs/uncertainty.json`](../configs/uncertainty.json).

These are **empirical historical-error prediction intervals for daily sales**,
not confidence intervals. They have no claimed conformal or finite-sample coverage
guarantee. Validation remains development evidence after point-model selection.

## Historical forecast calibration

Use exactly the saved Ridge original-training SKU/origin/horizon grid, retaining
the same 100 SKUs, modelling mask, Monday origins and complete 28-day target
windows. Require a full 56-day retained history strictly before every origin.
Every calibration target must precede **2011-06-06**.

Replay weekday mean from the retained training history: for each target weekday,
average its eight previous occurrences before the issue origin. Generate all 28
predictions together. Match the saved training-grid targets/actuals and verify
that predictions equal the existing `weekday_mean_8` feature values.

Define **residual = actual − prediction**, opposite to the existing signed-bias
metric (prediction − actual). Calibration uses no validation outcomes. Keep zeros,
extreme orders and original weights. There is no fitted point-model search.

## Fixed residual quantiles and endpoints

Group by **SKU and horizon week** (days 1–7, 8–14, 15–21, 22–28); pool target
weekdays within each group. Compute unweighted empirical residual quantiles using
`numpy.quantile(..., method='linear')`:

| Nominal level | Lower residual quantile | Upper residual quantile | alpha |
| --- | ---: | ---: | ---: |
| 80% | 0.10 | 0.90 | 0.20 |
| 95% | 0.025 | 0.975 | 0.05 |

Save residual-row count, unique target-date count and distinct origin count for
every SKU/week group. Overlapping historical horizons repeat target dates across
groups and reuse histories; counts are **not independent sample sizes**. Even
when dates within one group are unique, serial dependence and shared histories
remain. Linear interpolation follows [NumPy's documented method](https://numpy.org/doc/2.3/reference/generated/numpy.quantile.html).

For each saved validation point forecast p:

```text
lower = max(0, p + lower_residual_quantile)
upper = max(0, p + upper_residual_quantile)
```

Preserve p exactly. Do not round endpoints, force p into its interval, introduce
weekday-specific rules, substitute for missing groups, or change the method after
seeing validation coverage. Missing groups receive explicit statuses and an audit
file; affected aggregate coverage/width/score are undefined rather than silently
calculated on a subset. Quantiles remain fixed across validation origins.

## Evaluation

Score the same **28,000 validation instances per interval level**. Actuals are
attached for evaluation only. Coverage includes equality with either bound.
Report coverage, mean width, mean interval score, below/above miss counts, zero-width
counts and missing-interval counts overall and by SKU, horizon week, target
weekday, and useful origin/joint views.

For nominal level 1−alpha, interval score is:

```text
(upper-lower)
+ (2/alpha)*(lower-actual) * I(actual < lower)
+ (2/alpha)*(actual-upper) * I(actual > upper)
```

Lower score balances width and misses for the given nominal level. It does not
establish a coverage guarantee. Forecast instances overlap across origins; they
are not independent daily observations. Endpoints for separate days are marginal
daily quantities: **never sum them and label the result a calibrated interval for
total 28-day sales**. Aggregate uncertainty requires a separate method.

## Artifacts and tests

Save historical forecasts/residuals, all group counts/quantiles including missing
groups, validation point forecasts with both levels' endpoints, scored rows,
metrics, first-release/calibration records, dependency/input/output/code hashes and
representative plots. Plots retain original training-volume ranks 1/50/100 at the
last prescribed validation origin; example selection does not use coverage.

Test quantile arithmetic, residual sign, sample-count semantics, bounds/nesting,
nonnegative endpoints, exact point preservation, no forced point containment,
inclusive coverage and interval-score arithmetic, missing-group behavior, complete
history and strict calibration-date boundaries. Mutating validation outcomes must
not change calibration quantiles or already-issued intervals.

Final test is not evaluated here. A separately proposed final-evaluation protocol
will retain the frozen point method and original-training quantiles, allow only
past-observed history updates, and forbid post-final method changes.
