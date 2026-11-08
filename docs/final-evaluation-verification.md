# Milestone 7 verification addendum and defect log

Read this with [the preserved final-evaluation report](final-evaluation-report.md).
The one held-out evaluation completed successfully on 2026-11-01. The method,
predictions, endpoints, metrics, original report and completion manifest have
not been changed or regenerated. Weekday mean remains the selected method;
original-training residual intervals remain experimental.

## Freeze and one-evaluation evidence

- Release frozen at **2026-11-01T20:40:26.372927+00:00**, with 163
  code/configuration/input/calibration hashes.
- Outcome-access start recorded at **2026-11-01T20:40:49.536290+00:00**.
- Before unblinding: 51 unit tests, full synthetic 100-SKU end-to-end preflight
  including independent metrics/plots/report checks, environment/console checks,
  dependency checks and previous uncertainty-artifact validation all passed.
- All 100 SKUs, 484-row/10-SKU onset mask, SKU 21166 distinction and original
  training scales are preserved. Predictions and endpoints were saved before
  joining targets. Targets end Dec 4, before Dec 5; each method has 28,000
  instances and 9,100 unique SKU/date pairs. Calibration was not fitted or updated.
- The final-evaluation CLI was then invoked again. It verified saved hashes and
  displayed saved results only. The original manifest and every saved artifact
  remained byte-identical. Synthetic tests additionally block prediction/scoring
  and CSV parsing during the repeat path and check refusal of incomplete runs.

## Genuine post-unblinding verification defect

The original independent verifier failed an exact-equality assertion comparing
saved residual-quantile columns with the original calibration values. Its default
CSV parser did not always recover the exact binary float after reserialization:
**70 lower-quantile rows and 420 upper-quantile rows**, out of 56,000 each, differed
by at most **3.552713678800501e-15**. This was a checker implementation defect,
not evidence of recalibration or a changed interval method.

The original verifier is preserved unchanged at
`scripts/validate_final_evaluation.py`, remains covered by the pre-outcome freeze,
and also has a byte-preserved copy in the correction directory. The separate
`scripts/validate_final_evaluation_v2.py` reads the saved issued/scored interval
floats with `float_precision="round_trip"`. That recovers **exactly** the original
default-parsed calibration floats used by the evaluator: **zero mismatches** for
both quantile columns, without relaxing their equality tolerance. Other checks
are unchanged. No original forecast, bound, score, metric or calibration file was
edited. There was no second evaluation, recalibration, model switch or tuning.

An added synthetic float-regression test initially chose values that also survived
the default parser, so its demonstration-of-loss assertion failed. Its initial
source and failure explanation are retained; the corrected fixture uses
`nextafter(-29, +infinity)`, a concrete lossy default-parser example. This changed
only synthetic checker-test data. The frozen 51 tests remain unchanged.

**Final outcome: all 52 tests pass.** The separate v2 verifier passes all original
input/code/result hashes, issue-before-target-join timestamps, counts/date/grid
checks, unchanged point values and frozen scales/calibration, interval arithmetic,
ordering/nesting, actual-sales alignment and every predefined metric table.
The original report's empty in-run defect list predates this checker discovery;
this addendum documents the later verification defect. No statistical result
correction is present.

Append-only evidence is in
`data/final_evaluation_corrections/001-validator-csv-roundtrip/`: defect record,
original checker, initial regression fixture and note, pre-repeat hashes,
verification outcome, and a correction manifest linking this addendum/new checker
to the unchanged original results manifest. Generated audit files remain ignored
by Git.

## Correct verification command

Use the v2 verifier in place of the original verifier command shown in the frozen
README/protocol/report. Those originals are retained to preserve the freeze.

```powershell
.\.venv\Scripts\python.exe scripts/validate_final_evaluation_v2.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m retail_forecasting final-evaluation
```

The last command reports/verifies saved results only. Do not delete the results
directory to force another evaluation. The final period is now consumed evidence.

## Release interpretation

Final weekday-mean macro MASE **0.865584**, MAE **29.453821**, WAPE **91.519204%**,
mean signed bias **-2.369375 units**, relative bias **-7.362145%**. Against the
fixed seasonal-naive reference, MASE is 16.9520% lower and MAE/WAPE 17.2252%
lower; per-SKU MASE wins/ties/losses are **93/0/7**. These are descriptive results,
not statistical-significance claims from dependent forecast rows.

Final 80%/95% daily interval coverage is **81.214286%/94.128571%**, mean width
**66.080676/152.098475**, and mean interval score **175.148176/345.707805**.
There are no missing groups/intervals or zero-width intervals. Below/above misses
are **2,437/2,823** at 80%, **875/769** at 95%. Conditional failures remain:
Thursday coverage **66.725%/88.15%**; **41/42 SKUs** below nominal 80%/95%
coverage; minima **54.642857%/72.857143%**. Positive-sales instances contribute
**92.1339%** of selected-method absolute error. All 4,000 Saturday actuals and
point forecasts are zero naturally; no Saturday rule was added.

Compared with development validation, final macro MASE is **14.1768% higher**
and MAE **10.0439% higher**, while WAPE is **5.8212% lower**. The repeated-instance
actual-unit denominator is **16.8458% higher**; WAPE therefore need not move with
MAE. Different seasons and dependent origin windows prevent a causal or
independent-sample inference from these differences.

This release supports reproducible offline observed-sales forecasting and an
honest portfolio reference. It does not prove demand/availability, inventory
benefits, production readiness, reliable conditional coverage or aggregate/joint
uncertainty. Inventory-policy simulation with explicit assumptions is a suitable
next milestone; new model development would require new held-out evidence.
