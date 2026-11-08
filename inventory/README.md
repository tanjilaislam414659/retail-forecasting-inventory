# Fixed inventory-policy replay — simulation 0.1.0

This is a **synthetic inventory scenario on validation dates**, not measured
business service/cost, verified demand, real savings or a new held-out assessment.
[Pre-execution specification](../docs/inventory-simulation-spec.md) and
[full results](../docs/milestone-10.md). Original forecasting/calibration,
evaluation results, API/runtime code and archived snapshots remain unchanged.

From the repository root in Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_inventory.py -v
# Initial execution only; the existing run is already frozen and complete:
.\.venv\Scripts\python.exe -m retail_forecasting.inventory --freeze-only
.\.venv\Scripts\python.exe -m retail_forecasting.inventory
.\.venv\Scripts\python.exe scripts/validate_inventory.py
```

A completed repeat verifies saved hashes and reports existing outcomes without
replaying/overwriting ledgers. Do not delete results to force a new execution.
The freeze-only command refuses replacement. Initialization, one-date scenario
inputs, daily ledger, order/receipt audit, per-SKU/weekly/scenario metrics and
hash manifests live under ignored `data/inventory_simulation/v0.1.0/`.

The fixed grid is lead time 1/3/7 calendar days and shortage price 1/5 synthetic
cost units per unfulfilled unit, with holding 0.01 per closing unit/day and setup
1 per positive SKU order. Three policies are compared: a constant pre-validation
56-day-mean reference, weekday-mean point-forecast order-up-to, and its fixed 1.5
buffer. Policies have common starting stock per SKU/lead time, no initial pipeline,
Monday reviews, receipts before sales, no same-day arrivals and lost sales rather
than backlogs. No operational optimum or coverage level is implied by the buffer.

Actual scope: **100 SKUs, June 6–September 4 2011**, **9,100 unique SKU/date inputs**
and **246,299 observed positive-sales units per physical alternative**. There are
**900 continuous trajectories / 81,900 daily rows / 10,107 positive SKU orders**.
Each physical ledger is priced twice, yielding **18 economic comparisons** without
replaying overlapping horizon targets as separate sales.

The buffered variant fulfilled 87.68%/88.73%/89.81% at lead times 1/3/7, versus
the reference's 74.99%/73.81%/75.82%. Its average total closing inventory was
19,366.97/25,064.68/28,701.02 units, substantially above the reference's
10,743.45/13,018.86/15,647.22. It had lower simulated cost at both chosen shortage
prices, while still losing 25,090–30,337 scenario units. This is conditional on
the invented costs, not evidence of real savings or an optimal buffer.

The unbuffered forecast policy is not uniformly better than the reference. At
lead time 7 it fulfilled **75.7315% versus 75.8241%**, losing 228 more units. Its
lower inventory/setup costs made total simulated cost lower by 0.8300% at shortage
price 1 but higher by 0.0929% at price 5. Price changes affect accounting only.

Important interpretation limits:

- Initial stock rises with lead time: total initial units are 22,306/27,873/38,995
  for lead times 1/3/7. Policy targets also cover more days as lead time rises.
  Therefore rising fulfillment for the buffered policy does **not** show that
  longer physical delivery delays improve service with other quantities fixed.
- Forecasts are frozen external inputs, not recomputed from hypothetical fulfilled
  sales. This is not a closed-loop model of sales censoring or demand observation.
  Historical positive sales are not verified uncensored demand.
- The last three reviews use the Aug 8 forecast aged 7/14/21 days. There is no
  extrapolation. Terminal windows are clipped; 300 late-arrival review rows are
  ineligible, suppressing 69 otherwise-positive suggested orders. This is an
  explicitly finite-horizon experiment, with no terminal salvage or future penalty.
- Cost/inventory totals combine heterogeneous SKU units with identical artificial
  prices. Purchasing, returns, capacity, case packs, transport and in-transit costs
  are excluded. There is no real inventory/lead-time/cost dataset here.
- Daily uncertainty bounds are never used or summed. The multiplier is a heuristic,
  not a calibrated lead-time interval or service guarantee.

Checks: **15 synthetic tests pass**, plus a full synthetic 100-SKU preflight and
independent actual saved-output audit of forecast availability/targets, receipts,
stock/pipeline/unit conservation, unique dates, initialization and cost summaries.
Repeat execution was tested with simulation and CSV parsing blocked; every saved
output byte stayed unchanged. The specification protects **321 prior artifacts**.
The actual physical replay took **6.536 seconds**; the full command before
report/manifest took **9.796 seconds**, local CPU wall time.

The comparison figure and verification record are in ignored
`reports/generated/inventory_simulation/`. The final-test results are preserved
as consumed evidence, not re-evaluated. Nothing is published, and no inventory
feature was added to the API, Docker runtime or dashboard.
