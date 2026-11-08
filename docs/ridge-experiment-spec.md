# Fixed specification: one pooled Ridge regression

Recorded **2026-11-01 18:29:46 UTC**, before fitting or measuring Ridge validation
performance. Machine-readable specification: [`configs/ridge.json`](../configs/ridge.json).

The primary comparison metric is **macro per-SKU MASE**, using the saved original
training scales. Secondary measures are MAE, pooled WAPE and signed/relative bias.
The comparator is the **saved weekday-mean forecast**, not a newly recomputed or
retuned baseline. Report the outcome even if Ridge loses.

## Data and supervised examples

Preserve the 100 selected SKUs, daily data, onset mask (484 leading rows excluded,
with SKU 21166's distinction retained), chronological splits, frozen scales, ten
validation origins and 28-day horizon. Read `data/baselines/modelling_history.csv.gz`
and `history_and_scales.csv`; do not regenerate preparation or baseline artifacts.

Use all eligible Monday origins separately for each SKU. An origin must have all
56 preceding retained calendar dates and all 28 target dates; the final target must
be before **2011-06-06**. Create 28 supervised rows per SKU/origin, one target day's
positive sales per row. All rows have equal weight. Later-established SKUs may
contribute fewer origins. Overlapping training horizons repeat some target dates.

## Fixed features

| Feature | Definition/type |
| --- | --- |
| SKU | Categorical identity; no customer or price information. |
| Horizon day | Numeric, 1–28; target = origin + horizon_day - 1. |
| Target weekday | Categorical Monday=0 through Sunday=6, known at origin. |
| Target month | Categorical month 1–12, known at origin. |
| Sales means | Numeric means of the preceding 7, 28 and 56 calendar days. |
| Sales standard deviation | Previous 28 days, population convention `ddof=0`. |
| Zero share | Fraction of the preceding 28 days with zero observed sales. |
| Target-weekday mean | Average the eight occurrences of that weekday in the 56 days strictly before origin. |

Every sales-derived feature is calculated once from the origin's past, then reused
across the relevant horizon rows. In particular, days 8–28 never use target-period
sales. Calendar fields can describe future dates because they are known at origin.
No additional interactions, lag features, scaling of the target, winsorization,
sample weights or target transformations are introduced.

## Pipeline and fit

Use scikit-learn `Pipeline(ColumnTransformer(...), Ridge(...))`. Numeric columns
use `StandardScaler`; categorical columns use dense `OneHotEncoder(drop=None,
handle_unknown='ignore')`. Both learn exclusively from supervised original-training
rows. Pass no validation rows to `fit` or `fit_transform`.

Fit **once** with `alpha=1.0`, `solver='cholesky'`, `fit_intercept=True`, and one
BLAS thread. This deterministic solver avoids a convergence/window search. Ridge
minimizes **sum of squared training errors + alpha × squared coefficient norm**;
the intercept is unpenalized. See [official Ridge documentation](https://scikit-learn.org/1.7/modules/generated/sklearn.linear_model.Ridge.html).
Squared error gives large orders more influence and is not the same objective as
our absolute-error MAE/WAPE/MASE evaluation. Pooled training is not SKU-MASE-weighted.

Predictions stay in original units. **Clip negative raw predictions to zero**,
without rounding, and record the raw value, clipping indicator and clipping rate.
No parameter selection, additional fit on actual retail data, or validation refit.
Persist the pipeline and fit provenance; reruns reuse the fitted pipeline when its
specification, training examples, code and dependency versions match.

## Validation and reporting

Use the same 28,000 SKU/origin/target instances as saved weekday mean: weekly
Monday origins **2011-06-06 through 2011-08-08**, each with 28 predictions. Last
target is **2011-09-04**. Refresh input histories with validation sales already
observed before each origin, without fitting anything on validation targets.

Use the existing zero-denominator conventions: undefined WAPE/relative bias when
actual total is zero; undefined SKU MASE when its frozen scale is zero; no epsilon
or silent SKU removal. Report by model, SKU, origin, horizon week and joint groups.
Relative error change = `100*(Ridge/baseline - 1)`; negative means improvement.
For signed bias, report signed/unit and percentage-point differences plus relative
change in absolute bias magnitude, avoiding misleading sign-crossing ratios.
SKU win/tie/loss uses per-SKU MASE and absolute equality tolerance **1e-10** solely
for floating-point ties, not for metric denominators.

Overlapping validation horizons repeat some target dates at up to four origins;
these are dependent forecast instances, not independent observations. Plot the
same training-volume ranks **1, 50, 100** at origin **2011-08-08**, alongside saved
weekday mean; also show per-SKU MASE and horizon-week results. No example selection
based on flattering validation results.

Save training/validation feature rows, raw/clipped forecasts, all metrics and
comparisons, fitted pipeline, fit/experiment manifests and relevant plots. Measure
feature-build, pipeline-fit and prediction wall/CPU times separately. Keep final
test sealed. Major failures and metric tradeoffs must be reported before proposing
another modelling milestone.
