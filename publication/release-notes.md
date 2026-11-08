# v0.1.0 — historical forecasting portfolio

**First public historical-demonstration release.** Release identity is distinct from
the frozen scientific/configuration snapshot and API/runtime component versions.

- Audited public UCI Online Retail II; documented overlap, returns, exclusions,
  extreme orders and training-only cohort selection.
- Daily forecasts for 100 SKUs/28 days, with a modelling-history mask and frozen
  seasonal MASE scales. Fixed validation baselines, one Ridge and one Poisson
  boosting candidate; weekday mean selected on validation macro MASE.
- One consumed final assessment: weekday mean macro MASE 0.8656, MAE 29.45,
  WAPE 91.52%, relative bias −7.36%; fixed seasonal-naive macro MASE 1.0423.
- Experimental historical-error daily intervals: final coverage 81.21%/94.13%
  at nominal 80%/95%; Thursday coverage 66.73%/88.15%. No conditional, joint,
  conformal or total-horizon coverage guarantee.
- Eighteen saved synthetic inventory comparisons over validation dates, with
  service/stock/cost trade-offs and one chronological ledger per physical policy.
- Typed local API, three-view demonstration, non-root/read-only Docker packaging,
  artifact integrity and synthetic core/API/demo test preparation.

Runtime artifacts are separate from Git; attribution and checksums accompany the
licensed runtime bundle. Raw/customer-level data and fitted candidates do not
ship. Project code is MIT, copyright (c) 2026 Tanjila Islam; UCI data is CC BY 4.0.
Hosted CI and download verification are linked from the README. Real-world retail integration is not claimed.

Milestone 12 changes documentation, publication checks and test/package preparation
only. It does not rerun acquisition, training, calibration, evaluation or inventory
simulation, and does not make the consumed test fresh selection evidence.

Publication starts with a fresh history; no original development commits were imported.
License notices are added outside the unchanged frozen runtime bundle directory.
