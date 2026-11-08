# Employer-facing copy (draft)

## Repository description

Reproducible historical retail forecasting: audited UCI sales, leakage-tested
baselines, experimental intervals, synthetic inventory scenarios and a FastAPI/Docker demo.

## Short project description

An AI-assisted, CPU-based Data Science and ML Engineering portfolio project built
around UCI Online Retail II. It audits 1,067,371 source rows, selects 100 SKUs from
training data and forecasts daily observed positive sales over 28 days. Fixed
walk-forward validation retained eight-week weekday mean over pooled Ridge and
Poisson boosting; one consumed final test compared it with seasonal naive.
Frozen inference, experimental historical-error intervals and transparent synthetic
inventory scenarios are exposed through a local FastAPI demonstration with Docker
packaging and dataset-free engineering checks. It is not a live retail service,
uncensored-demand estimate or claim of business savings.

## Two CV bullets

- Developed an AI-assisted, reproducible retail forecasting study over 1.07M
  public transaction rows and 100 SKUs, with chronological validation, pre-origin
  leakage tests and a frozen 28-day forecaster; weekday mean achieved final-test
  macro MASE **0.8656**, **16.95% lower** than the fixed seasonal-naive reference.
- Packaged frozen inference and experimental daily prediction intervals in a
  typed FastAPI/Docker historical demo with hash-verified read-only artifacts,
  non-root execution and synthetic core/API/demo CI checks; documented inventory
  service/stock trade-offs across **18 synthetic scenarios**, without claiming
  real business savings.

The relative MASE figure is descriptive, from the single saved final assessment.
Overlapping forecast instances are dependent; it is not a significance claim.
Do not imply hosted CI, a public deployment, personal implementation without AI
assistance, real client adoption or live operational impact.

## Two-minute demo walkthrough

1. **Context (15 s):** explain the 100-SKU historical scope, 28-day horizon and
   observed-sales target. Mention CPU/free-tool constraints and AI-assisted work.
2. **Forecast explorer (35 s):** select SKU 21212, origin 2011-11-07; show the
   strictly pre-origin cutoff, frozen release/calibration IDs and daily table.
   Explain that intervals are experimental and cannot be summed into a calibrated
   total-horizon interval. A verified runtime bundle is required for this view.
3. **Evaluation (40 s):** compare validation macro MASE 0.7581 with Ridge 0.8261
   and boosting 0.7788; explain why a simpler seasonal method won. Point to the
   separate consumed final-test card (0.8656 versus reference 1.0423). Highlight
   Thursday undercoverage: 66.73%/88.15% at nominal 80%/95%.
4. **Inventory (25 s):** show lead 3/penalty 1. The 50% buffer increases fulfillment
   to 88.73% while average stock rises to 25,064.68 units. Explain synthetic costs,
   lost sales, initial-stock assumptions and reused late-validation forecasts.
5. **Engineering (15 s):** describe shared inference, strict schemas, integrity
   failures, no request-time training and dataset-free CI. Say hosted Actions is
   pending, and show the documented commands rather than claiming public hosting.
