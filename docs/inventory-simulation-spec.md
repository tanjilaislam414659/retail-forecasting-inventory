# Fixed inventory simulation specification — Milestone 10, version 0.1.0

This specification is saved **before simulation execution**. It describes a
bounded validation development exercise with synthetic inventory assumptions.
The machine-readable definition is `configs/inventory-simulation.json`. No
parameter, policy, lead time or price is selected after reading simulation results.
The forecaster/calibration and consumed final evaluation remain unchanged.

## Scenario inputs and chronological scope

Replay the existing 100-SKU processed positive-sales panel for **2011-06-06 through
2011-09-04 inclusive**, 91 calendar days. Use exactly one input value per SKU/date:
9,100 unique SKU/date rows. Overlapping forecast horizons are alternative forecasts
of those dates, never additional scenario sales. Observed sales are **not verified
uncensored demand**: availability, lost historical demand and listing information
are unknown. Here, the observed numbers are only an exogenous scenario input.

Use the **saved weekday-mean forecasts** at the ten existing validation origins,
2011-06-06 through 2011-08-08. Do not create new forecasts, recalibrate intervals,
score models or read final-period sales. Load the preserved
`data/baselines/modelling_history.csv.gz`, which already contains only retained
original-training and validation rows. Its original onset mask remains intact.
The full processed panel is hashed for preservation checks but never parsed for
this exercise; final-test sales are not loaded.

## Fixed physical and economic scenario grid

Use deterministic calendar-day lead times **1, 3 and 7 days** and synthetic shortage
prices **1 and 5 cost units per unfulfilled unit**: six predefined economic
scenarios. Holding is **0.01 synthetic cost units per end-of-day on-hand unit per
day**, and each positive SKU order has a **1 cost-unit setup charge**. These are
not estimated costs, currencies, business savings, service targets or calibrated
operating parameters. Purchasing/transport/spoilage/in-transit costs, capacity,
case packs, minimum orders and cross-SKU consolidation are excluded.

All policies for a SKU/lead-time start with the same synthetic stock:
`ceil(mean of its 56 calendar days before 2011-06-06 * (lead time + 7))`.
Include observed zero-sales days and preserve the original modelling-history mask.
Start with no pipeline or backlog. Initial stock has no purchase charge; no policy
gets extra initial stock because it uses a buffer.
Reference means/ceilings use exact rational arithmetic from integer training
totals and 56 days; no epsilon or premature rounding changes the target.

Shortage price changes affect accounting, not ordering. Therefore simulate only
**nine physical policy/lead-time alternatives**, each with 100 continuous SKU
ledgers, and price each ledger twice. Expect **81,900 daily ledger rows**, 900
SKU/policy/lead-time trajectories and **18 aggregate economic comparison rows**.
Do not pool alternative scenarios together as if they were additional sales.

## Three fixed policies

Review on all thirteen Mondays in the scenario. Let `H` be protection days,
normally `lead time + 7`; near the terminal date use
`min(lead time + 7, remaining scenario calendar days)`.

1. **static_reference:** target stock = `ceil(pre-validation 56-day mean * H)`.
   The mean stays fixed throughout validation. This simple reference uses no
   validation outcomes to update its demand estimate.
2. **weekday_mean:** target stock = `ceil(sum of available point forecasts for
   the H dates beginning at the review date))`.
3. **buffered_weekday_mean:** target stock = `ceil(1.5 * that point-forecast sum)`.
   The 50% buffer is a fixed heuristic, not a quantile or coverage guarantee.

After receipts and before today's sales, inventory position is on-hand plus all
outstanding pipeline units. Order `max(0, target - inventory position)` integer
units. Orders have no capacity limit and arrive at the start of `order day + L`.
For this finite experiment, do not order if arrival would be outside the scenario.

The forecast policy uses the **latest saved issue date <= review date**; every
required target date must exist in that issued 28-day horizon. The last three
reviews (Aug 15, 22, 29) consequently use the Aug 8 issue aged 7, 14 and 21 days.
No unseen later issue or extrapolation is allowed. Terminal clipping ensures the
protection window stays inside the saved horizon and validation dates. Staleness,
terminal-aware truncation and suppression of orders arriving after Sep 4 are
explicit limitations of this bounded exercise, not recommended perpetual-business
operating rules. They apply consistently across the comparison.

## Daily event order and lost sales

For each SKU/policy/lead-time, keep one continuous ledger, never reset stock at a
new forecast origin. Each day:

1. Record opening stock; receive prior orders scheduled for today and remove them
   from pipeline. Receipts are available before sales or a new ordering decision.
2. On review Mondays, compute the target/order using only the pre-origin forecast,
   pre-validation reference mean and current inventory/pipeline. Today's observed
   sales have not yet entered the decision. No same-day arrival is possible.
3. Fulfill `min(available stock, scenario input)` units. Treat remaining units as
   lost sales; they are neither backlogged nor added to future input.
4. Record closing on-hand stock and pipeline. Accrue holding cost on closing
   stock, shortage price once per lost unit, and setup cost once per positive order.

End with remaining stock/pipeline reported explicitly. No salvage credit, purchase
cost, future service penalty or future cost beyond Sep 4 is introduced. This
finite-horizon accounting can influence policy comparisons and is not an economic
optimum. All receipts must match previously placed orders with exact lead-time
timing; no order placed today can fulfill today's sales.

## Metrics, checks and reporting

Report all eighteen fixed scenario/policy combinations, including service/cost
tradeoffs; do not automatically choose or tune a winner. Main service metric:
`fulfilled units / replayed observed-sales units`, pooled across SKUs. Also report
unfulfilled units, shortage SKU-days, mean daily closing inventory summed over
SKUs, average per-SKU closing inventory, positive SKU-order count, holding/setup/
shortage/total simulated costs, and terminal stock/pipeline. Report costs as
**simulated cost units**; relative differences from the static reference are
scenario comparisons, never real business savings. Zero unit denominators make
fulfilled-unit rate undefined, with no epsilon or silent exclusions.

Verify hand-calculable receipts/ordering/lost-sales/cost cases, stock and pipeline
conservation, exact date/key cardinality, one sales replay per trajectory/date,
forecast issue/target availability, no future-issue selection and decision
invariance when current/future scenario sales change. The original frozen
forecasts remain read-only; actual-sales columns in their saved evaluation file
are not loaded as ordering inputs. The separate sales-panel reader supplies the
single chronological replay. No interval table is used and no summed daily bound
is described as calibrated lead-time or total-sales uncertainty.

Save the fixed specification/code/input hashes before the first actual run, daily
ledger, order/receipt audit, per-SKU and aggregate metrics, initialization values,
comparison report, sensitivity figure, timings and integrity manifest. Generated
data/figures remain ignored. Repeating a completed command should verify saved
artifacts rather than overwrite them. Use validation only: this is development
evidence after model selection, and the consumed final-test results are not a new
held-out assessment. User authorization for this milestone supersedes the older
AGENTS.md milestone scope without modifying its frozen bytes.

Reproducible command: `.\.venv\Scripts\python.exe -m retail_forecasting.inventory`.
