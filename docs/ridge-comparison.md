# Milestone 4: one pooled Ridge regression

**Primary outcome: Ridge loses versus saved weekday mean on macro MASE.** This is one predefined experiment, not a hyperparameter search. Final test remains unevaluated.
The [fixed experiment specification](ridge-experiment-spec.md) and `configs/ridge.json` were recorded before fitting. The cohort, onset mask, frequency, splits, frozen scales and validation instances are unchanged.

## Training and availability

Training uses **185,584 supervised rows / 6,628 SKU-origin groups / 100 SKUs**, with 53–67 Monday origins per SKU. Origins span **2010-02-01 through 2011-05-09**; all targets lie in **2010-02-01 through 2011-06-05**, strictly before 2011-06-06.
Each origin has 56 consecutive retained historical days. Every sales feature comes from before the origin, including for horizon days 8–28. Features are SKU, horizon day, target weekday/month, means over 7/28/56 days, population standard deviation and zero share over 28 days, and the target weekday's preceding-eight-occurrence mean.
Numeric StandardScaler and categorical OneHotEncoder are fitted inside the pipeline on training rows only. Ridge uses alpha=1.0, Cholesky solver, intercept, untransformed targets and equal row weights. One actual-data fit is persisted; repeated commands reuse it after signature checks. Later validation origins refresh observed-history features without refitting the estimator or preprocessors.
Ridge optimizes **sum of squared errors + alpha × squared coefficient norm**, while macro MASE, MAE and WAPE use absolute errors. Large wholesale spikes therefore have disproportionate training influence, and shared numeric slopes plus SKU intercepts do not model SKU-specific seasonal interactions.

## Validation outcome and tradeoffs

Same **28,000** validation instances per model, ten origins from 2011-06-06 through 2011-08-08, and targets through 2011-09-04. Signed bias is prediction minus actual; positive means overforecast. Main Ridge scores use the predefined zero-clipped predictions, without rounding.

| Model | Macro MASE (primary) | MAE | Pooled WAPE | Signed bias (units) | Relative bias |
| --- | ---: | ---: | ---: | ---: | ---: |
| ridge | 0.826062 | 27.8381 | 101.07% | +3.2685 | +11.87% |
| weekday_mean | 0.758109 | 26.7655 | 97.18% | -0.7121 | -2.59% |

Relative changes use 100 × (Ridge / baseline − 1); negative means lower error.
- Macro MASE: **+8.96%**.
- MAE: **+4.01%**; pooled WAPE: **+4.01%**.
- Signed bias change: **+3.9806 units**; relative-bias difference: **+14.45 percentage points**. Absolute bias magnitude changes **+359.00%**. A sign change is not interpreted as an error-ratio improvement.
- SKU primary-metric win/tie/loss counts: **{'loss': 70, 'win': 30}**, out of 100. Ties use absolute tolerance 1e-10 only for numerical equality.
- Negative predictions clipped: **3,089/28,000 (11.03%)**. Raw predictions range -25.0329 to 240.1723 units; raw values and clipping flags are saved.

### Horizon-week results

| Model | Horizon week | Macro MASE | MAE | WAPE | Signed bias |
| --- | ---: | ---: | ---: | ---: | ---: |
| ridge | 1 | 0.83868 | 27.5253 | 100.69% | +3.6716 |
| ridge | 2 | 0.82727 | 27.9644 | 101.75% | +3.3778 |
| ridge | 3 | 0.81834 | 27.9057 | 100.34% | +2.8970 |
| ridge | 4 | 0.81996 | 27.9568 | 101.51% | +3.1277 |
| weekday_mean | 1 | 0.76524 | 26.2249 | 95.93% | -0.5051 |
| weekday_mean | 2 | 0.75589 | 26.7844 | 97.46% | -0.6522 |
| weekday_mean | 3 | 0.75341 | 26.9452 | 96.88% | -0.9813 |
| weekday_mean | 4 | 0.75789 | 27.1075 | 98.43% | -0.7098 |

## Major failures and variation

On **8,699 zero-actual forecast instances**, Ridge predicts **15.0657 units on average**, versus **9.2812** for weekday mean. On **4,000 Saturday instances**, all actual sales are zero; Ridge still predicts **6.5886 units on average**, versus **0.0000** for weekday mean. These are observed validation sales, not proof of closure or inventory availability.
The additive model permits a positive SKU-level intercept even when a particular SKU/weekday should have near-zero observed sales. Shared slopes and global weekday effects cannot represent every SKU-specific pattern. Squared-error training emphasizes spikes rather than equal-SKU absolute error; these are plausible contributors, not a causal diagnosis established by this single experiment.
Clipping adds **30,279.17 units** to the aggregate raw forecasts, moving mean signed bias from **+2.1871** before clipping to **+3.2685** after clipping. Clipping was fixed before evaluation, and was not changed in response to this outcome.

Largest SKU MASE increases (positive is worse):

| SKU | Weekday-mean MASE | Ridge MASE | Difference |
| --- | ---: | ---: | ---: |
| 21034 | 0.52397 | 1.45324 | +0.92927 |
| 21533 | 1.26483 | 1.77382 | +0.50899 |
| 85150 | 0.31170 | 0.80310 | +0.49140 |
| 21755 | 0.47380 | 0.93345 | +0.45965 |
| 21754 | 0.43398 | 0.88078 | +0.44679 |

ridge origin macro MASE ranges **0.76427** (2011-07-11) to **0.88638** (2011-06-13).

weekday_mean origin macro MASE ranges **0.71269** (2011-08-08) to **0.79189** (2011-07-25).

The plots expose missed spikes, persistent level errors and the additive model's limitations. Those are descriptive patterns; they do not identify causal effects of price, stockouts or promotions. Large orders were retained. Good signed bias can conceal offsetting over- and underforecasts.
Overlapping horizons repeat targets at up to four origins; 28,000 scored forecasts correspond to 9,100 distinct SKU/target-date pairs. Metric differences are descriptive and not based on independent forecast samples.
Undefined WAPE groups: `{'by_model': 0, 'by_sku': 0, 'by_origin': 0, 'by_horizon_week': 0, 'by_sku_origin': 14, 'by_sku_origin_week': 114}`; undefined MASE groups: `{'by_model': 0, 'by_sku': 0, 'by_origin': 0, 'by_horizon_week': 0, 'by_sku_origin': 0, 'by_sku_origin_week': 0}`. Existing zero-denominator conventions are preserved, with explicit statuses and no dropped SKUs or epsilon.

## Timing and evidence

Original pipeline fit, including training-only preprocessing: **0.6034 wall / 0.5938 CPU seconds**. Validation pipeline prediction: **0.1717 wall / 0.1719 CPU seconds**. One BLAS thread; feature building and report work are excluded from those figures.
Training feature construction: 23.037 wall seconds; validation features: 4.129. Full command: 39.029 wall / 38.859 CPU seconds. Pipeline reused in this invocation: True.
`models/ridge/pipeline.joblib` and its fit record preserve the single fitted pipeline. `data/ridge/` contains its exact specification, train/validation features, raw/clipped forecasts, preprocessing statistics, coefficients, all metric tables, relative comparisons, summary and integrity manifest. Generated data/models/plots are ignored by Git.

Forecast plot selection uses original training-volume ranks 1, 50 and 100: **21212, 21791, 21533**, at origin 2011-08-08. No validation-error selection.
![Representative forecasts](../reports/generated/ridge/representative_forecasts.png)

![Per-SKU and horizon comparison](../reports/generated/ridge/validation_comparison.png)

## Reproduce and decision

Run `.\.venv\Scripts\python.exe -m retail_forecasting ridge`, then the test suite and `scripts/validate_ridge.py`. See [Milestone 4](milestone-4.md) for contracts and checks. Repeating the command reuses a matching saved fit; it does not refit on validation data.
Ridge does not improve the primary metric; retain weekday mean as the reference. The next milestone should investigate the documented failure patterns and specify one targeted alternative before fitting it, rather than expanding a model search. Keep final test sealed.
