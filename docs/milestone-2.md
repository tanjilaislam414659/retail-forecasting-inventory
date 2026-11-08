# Milestone 2: acquisition, audit, and bounded sales data

Completed scope: public workbook acquisition, quality audit, explicit cleaning,
fixed chronological splits, training-only SKU selection, positive sales panels,
a separate returns/adjustments ledger, and data-contract checks. No model training.

## Reproduce on Windows

From the repository root, use the existing environment:

```powershell
.\.venv\Scripts\python.exe -m pip install --disable-pip-version-check -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pip install --disable-pip-version-check --no-build-isolation --no-deps -e .
.\.venv\Scripts\python.exe -m retail_forecasting acquire
.\.venv\Scripts\python.exe -m retail_forecasting prepare
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts\validate_data.py
.\.venv\Scripts\python.exe scripts\verify.py
.\.venv\Scripts\python.exe -m pip check
```

`acquire` downloads the official UCI ZIP only on first acquisition; it caps the
archive and workbook at 75 MiB. It retains both in `data/raw/` and writes
`docs/data-provenance.json`. Repeat runs verify hashes without another download
or a new retrieval time. Changed/unmanifested raw files are not overwritten.

`prepare` verifies the workbook hash and actual headers, then rebuilds outputs in
`data/processed/` and regenerates `docs/data-quality-report.md`. It does not change
the workbook or protocol. Preparation took about two minutes on this CPU; exact
elapsed time is in `quality.json`, without a performance guarantee.

`requirements-lock.txt` captures exact versions on Windows CPython 3.13.5. NumPy
2.3.4 is paired with pandas 2.3.3 to resolve a deprecation warning encountered with
the automatically selected NumPy 2.5.4. Other platforms/Python versions are not
verified. No system settings were changed.

## Protocol fixed before workbook inspection

Configuration: [`configs/preparation.json`](../configs/preparation.json).

| Period | Inclusive start | Exclusive end | Days | Weeks |
| --- | --- | --- | ---: | ---: |
| Training / development | 2009-12-07 | 2011-06-06 | 546 | 78 |
| Validation | 2011-06-06 | 2011-09-05 | 91 | 13 |
| Final test | 2011-09-05 | 2011-12-05 | 91 | 13 |

These are full Monday-to-Sunday weeks, excluding the initial/final partial weeks
independently of SKU performance. Reserve final test for later evaluation after
choices are frozen. Inspecting it for quality and arithmetic must not become tuning.

## Cleaning and audit rules

1. Read the workbook without writing it. Reject unexpected headers; record sheet
   sizes, types, missing cells, and timestamp bounds. Preserve `sheet:Excel-row`
   pointers for every source row.
2. Match full-row cross-sheet copies using SHA-256 of the complete source tuple,
   including customer ID in memory only, plus within-sheet occurrence number.
   Retain the earliest sheet counterpart and maximum multiplicity across sheets.
   Keep unmatched overlap rows and repeated rows within a sheet. Native source
   numeric types are part of the key; near-matches are not deduplicated. SHA-256
   collision risk is negligible but not mathematically zero.
3. Normalize invoice/SKU to stripped uppercase strings. Quantities must be finite
   and integral; timestamp, invoice and SKU must be present.
4. Route every non-copy row with invoice prefix `C` or negative quantity to the
   returns/adjustments ledger, including inconsistent cancellations/adjustments.
   `eligible_product_return` marks negative finite integral product quantities,
   positive finite prices, and present timestamp/invoice. It does not prove an
   actual refund or link the row to an original sale.
5. For positive sales, require SKU pattern `^\d{5}[A-Z]{0,2}$`, positive integral
   quantity, positive finite price, and study dates. This bounded merchandise
   scope excludes postage, fees, manual lines, vouchers and special codes. A
   catalogue is unavailable, so legitimate special codes may be omitted. SKU
   suffixes remain distinct products.
6. Missing description/customer ID does not invalidate otherwise valid sales.
   Customer values support in-memory overlap matching and missingness counts only.
   No generated file contains a customer column or customer fingerprint.
7. Retain repeated transactions and large orders after overlap reconciliation.
   Flag lines at absolute quantity >=1,000 or absolute value >=GBP10,000, and
   summarize invoice totals using the same thresholds. Do not winsorize or delete
   based on size.
8. Select products from training only: >=26 positive weeks and >=365 elapsed days
   between first training sale and training end. Rank by positive sale days
   descending, then positive units descending, then SKU ascending; take at most
   100. Freeze this cohort across all splits.
9. Build all 728 study days per SKU, without future-last-sale trimming. Sum observed
   positive units and never net returns. Where no accepted sale line exists, use
   zero with `zero_filled=True`. This does not assert latent demand, availability,
   store opening, product listing, or inactivity. Retain each SKU in held-out data.
10. Assess sparsity on selected SKUs' training grid only. Choose weekly if median
    daily zero share is >=50%, otherwise daily. Weekly starts Monday and sums
    seven complete days. The horizon is 28 days / four weeks, a planning scenario
    rather than a measured lead time.

`row_audit.csv.gz` accounts for every source row. Issue flags can overlap; exclusive
disposition precedence is: cross-sheet copy, returns ledger, malformed required
values, non-product code, invalid/nonpositive price, zero quantity, outside study
window, eligible but unselected SKU, selected positive sale. Every excluded row
has reasons. Copy rows identify their retained counterpart.

## Outputs and contracts

All files below are in ignored `data/processed/`:

| File | Meaning |
| --- | --- |
| `sales_daily.csv.gz` | SKU/day target `sales_units`, retrospective `sales_lines`/`zero_filled`, and date-based `split`. Audit fields are not future-known covariates. |
| `sales_weekly.csv.gz` | Monday-start sums of the same cohort; includes zero-filled-day count and days per period. |
| `sku_selection.csv` | Fixed cohort/rank and training-only selection statistics. |
| `returns_ledger.csv.gz` | Non-copy negative/cancellation rows from the full source, including dates/codes outside panel scope. Never netted from sales. |
| `row_audit.csv.gz` | Source pointers, normalized non-customer values, flags, disposition, reasons and copy pointers. |
| `large_invoices.csv`, `extreme_lines.csv.gz` | Extreme-order evidence retained for review. |
| `boundary_dates.csv`, `quality.json` | Boundary times, sheet types/missingness, overlap, quality counts, missing source days and training sparsity. |
| `preparation-manifest.json` | Source/config/code/output hashes, byte counts, package versions and chosen forecasting file. |

See the [quality report](data-quality-report.md) for measured results and limitations.
Both frequencies are saved for audit; the preparation manifest chooses **daily**.
Forecast panels contain no prices, customer identifiers or future activity features.

## Verification

Eight synthetic tests cover split boundaries, weekly completeness, cross-sheet
matching/multiplicity, cancellation routing, invalid values, large-order retention,
held-out perturbations, zero filling, conservation, byte-preserving acquisition,
idempotence, tamper detection, size caps, and preservation of existing raw files.
Tests do not contact the network.

`scripts/validate_data.py` independently reads saved files and checks raw/output
hashes, exhaustive accounting, copy pointers, exclusion reasons, per-SKU/day sums,
fixed-cohort coverage, split bounds, weekly completeness, returns separation, and
absence of customer columns. `scripts/verify.py` retains the installation smoke check.

Observed on 2026-11-01: all **8 tests passed**; saved-data validation passed;
installation smoke checks passed; `pip check` reported no broken requirements.
Repeat acquisition verified both raw hashes without another download. Git ignore
checks confirmed that the raw ZIP/workbook, sales panel, audit and returns ledger
are excluded. The repository remains local with no remote or publication.

The source workbook contains 45,622,278 bytes, about 43.51 MiB; this reconciles the
publisher's approximate 43.5 MB display. UCI's overall missing-value indicator says
yes, while its placeholder variable table is incomplete. Actual missing-field
counts in the quality report take precedence over that placeholder table.

## Proposed milestone 3

Implement last-value, training-mean, and weekly seasonal-naive baselines. A 28-day
seasonal-naive forecast must repeat the last available seven days, without using
actuals inside its forecast window. Use rolling origins within development and
validation; report per-SKU and pooled MAE/WAPE, zero-denominator handling and CPU
runtime. Freeze choices before final-test evaluation. Specify inventory simulation
separately before making any cost/service claim.
