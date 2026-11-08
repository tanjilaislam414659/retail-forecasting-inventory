# Milestone 10 — bounded validation inventory-policy simulation

**These are simulated scenario outcomes, not real business savings, uncensored-demand estimates or a new held-out assessment.** The original forecaster, calibration, cohort, scales and consumed final-test artifacts remain unchanged. No model, interval or preparation rule was tuned.

[Fixed pre-execution specification](inventory-simulation-spec.md) and `configs/inventory-simulation.json` define all policies, stock, cost assumptions and daily timing. `data/inventory_simulation/v0.1.0/specification-record.json` records their code/input hashes and UTC time before execution.

## Replay and assumptions

Replay **9,100 unique SKU/date inputs**, 100 SKUs over **2011-06-06 through 2011-09-04**. Each physical policy/lead alternative sees **246,299 observed positive-sales units once**. Overlapping forecast horizons are not counted as additional sales.

Observed positive sales are only an exogenous scenario input; historical stockouts, availability and lost demand are unknown. The modelled lost units therefore are not measured business shortages. Returns, procurement, variable transport, capacity, case packs, spoilage and in-transit costs are excluded.

Three fixed policies: static reference from the original pre-validation 56-day mean; weekly weekday-mean order-up-to; and its fixed 1.5 multiplier variant. All receive identical synthetic initial stock per SKU/lead time, `ceil(training mean × (L+7))`, and no initial pipeline/backlog. Reference means/targets use exact rational arithmetic over integer training totals; forecast sums preserve the saved floating-point point values.

Lead times are 1, 3 and 7 calendar days. On each day, receive old orders first; review/order on Mondays before observing that day's sales; fulfill up to available stock; lose remaining units without backlog; charge end-of-day inventory. Order quantity is max(0, target minus on-hand-plus-pipeline). No order arrives on its placement date.

Synthetic holding cost is 0.01 per closing on-hand unit/day, positive SKU-order setup cost is 1, and shortage prices are 1 and 5 per lost unit. These are artificial cost units, not an estimated currency. Purchase cost and salvage credit are absent. Initial stock is not charged as a purchase.

There are **900 continuous SKU/policy/lead trajectories**, **81,900 daily rows**, **10,107 positive orders**, **1,800 per-SKU economic rows**, and **18 aggregate comparison rows**. Each physical ledger is priced twice; different shortage prices never cause a second replay or different decisions.

## Actual fixed-grid outcomes

Fulfilled-unit rate pools fulfilled/replayed units across SKUs. Shortages are unfulfilled scenario units. Average inventory below is mean daily closing inventory summed over all 100 SKUs, not physical volume/value. Order count counts positive SKU orders, not consolidated truck deliveries. Costs include holding + lost-unit penalty + positive-order setup.

| lead_time_days | policy | fulfilled_unit_rate_pct | unfulfilled_units | shortage_sku_days | average_total_closing_inventory | order_count | cost_at_shortage_1 | cost_at_shortage_5 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | buffered_weekday_mean | 87.683 | 30337 | 585 | 19366.967 | 1204 | 49164.940 | 170512.940 |
| 1 | static_reference | 74.992 | 61595 | 1331 | 10743.451 | 1179 | 72550.540 | 318930.540 |
| 1 | weekday_mean | 75.359 | 60690 | 1230 | 10294.209 | 1158 | 71215.730 | 313975.730 |
| 3 | buffered_weekday_mean | 88.733 | 27750 | 509 | 25064.681 | 1138 | 51696.860 | 162696.860 |
| 3 | static_reference | 73.814 | 64495 | 1318 | 13018.857 | 1156 | 77498.160 | 335478.160 |
| 3 | weekday_mean | 76.394 | 58141 | 1141 | 13631.560 | 1165 | 71710.720 | 304274.720 |
| 7 | buffered_weekday_mean | 89.813 | 25090 | 509 | 28701.022 | 1053 | 52260.930 | 152620.930 |
| 7 | static_reference | 75.824 | 59545 | 1246 | 15647.220 | 1066 | 74849.970 | 313029.970 |
| 7 | weekday_mean | 75.732 | 59773 | 1253 | 14799.692 | 988 | 74228.720 | 313320.720 |

### Cost components and reference-relative differences

| lead_time_days | shortage_cost_per_unit | policy | holding_cost | order_setup_cost | shortage_cost | total_simulated_cost | simulated_cost_difference_pct | fulfilled_rate_difference_pp |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1.000 | buffered_weekday_mean | 17623.940 | 1204.000 | 30337.000 | 49164.940 | -32.234 | 12.691 |
| 1 | 1.000 | static_reference | 9776.540 | 1179.000 | 61595.000 | 72550.540 | 0.000 | 0.000 |
| 1 | 1.000 | weekday_mean | 9367.730 | 1158.000 | 60690.000 | 71215.730 | -1.840 | 0.367 |
| 1 | 5.000 | buffered_weekday_mean | 17623.940 | 1204.000 | 151685.000 | 170512.940 | -46.536 | 12.691 |
| 1 | 5.000 | static_reference | 9776.540 | 1179.000 | 307975.000 | 318930.540 | 0.000 | 0.000 |
| 1 | 5.000 | weekday_mean | 9367.730 | 1158.000 | 303450.000 | 313975.730 | -1.554 | 0.367 |
| 3 | 1.000 | buffered_weekday_mean | 22808.860 | 1138.000 | 27750.000 | 51696.860 | -33.293 | 14.919 |
| 3 | 1.000 | static_reference | 11847.160 | 1156.000 | 64495.000 | 77498.160 | 0.000 | 0.000 |
| 3 | 1.000 | weekday_mean | 12404.720 | 1165.000 | 58141.000 | 71710.720 | -7.468 | 2.580 |
| 3 | 5.000 | buffered_weekday_mean | 22808.860 | 1138.000 | 138750.000 | 162696.860 | -51.503 | 14.919 |
| 3 | 5.000 | static_reference | 11847.160 | 1156.000 | 322475.000 | 335478.160 | 0.000 | 0.000 |
| 3 | 5.000 | weekday_mean | 12404.720 | 1165.000 | 290705.000 | 304274.720 | -9.301 | 2.580 |
| 7 | 1.000 | buffered_weekday_mean | 26117.930 | 1053.000 | 25090.000 | 52260.930 | -30.179 | 13.989 |
| 7 | 1.000 | static_reference | 14238.970 | 1066.000 | 59545.000 | 74849.970 | 0.000 | 0.000 |
| 7 | 1.000 | weekday_mean | 13467.720 | 988.000 | 59773.000 | 74228.720 | -0.830 | -0.093 |
| 7 | 5.000 | buffered_weekday_mean | 26117.930 | 1053.000 | 125450.000 | 152620.930 | -51.244 | 13.989 |
| 7 | 5.000 | static_reference | 14238.970 | 1066.000 | 297725.000 | 313029.970 | 0.000 | 0.000 |
| 7 | 5.000 | weekday_mean | 13467.720 | 988.000 | 298865.000 | 313320.720 | 0.093 | -0.093 |

Negative simulated cost differences mean lower cost under these particular invented assumptions, not verified savings. No winner is automatically selected, and no parameters change after this table. More buffer can reduce lost units while increasing stock/holding cost; shortage-price sensitivity changes the accounting weight of those tradeoffs without changing physical trajectories.

![All predefined scenario sensitivities](../reports/generated/inventory_simulation/sensitivity-v0.1.0.png)

## Timing, forecast aging and terminal limitations

Each SKU has one 91-day chronological ledger per policy/lead, with no reset at an overlapping forecast origin. Saved forecasts are used only at or after their issue date, and every protection target remains inside the chosen issue's 28-day horizon. No actual-sales columns from saved forecasts are loaded.

There are **7,800 forecast-policy review rows**; ages in days and counts are **{'0': 6000, '7': 600, '14': 600, '21': 600}**. The last three Mondays use the Aug 8 issue aged 7, 14 and 21 days. These stale final-week forecasts and a fixed static reference are deliberate bounded-development choices, not an updated weekly forecasting service.

Protection windows are truncated at Sep 4. Orders arriving on/after Sep 5 are disallowed: **300 review rows** have ineligible arrival dates; **69** would otherwise suggest a positive order. Terminal truncation/order suppression affects comparisons and is not a recommended continuing-business policy.

| lead_time_days | policy | starting_stock | ending_stock | ending_pipeline_units | ordered_units | received_units |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | buffered_weekday_mean | 22306 | 15888 | 0 | 209544 | 209544 |
| 1 | static_reference | 22306 | 7937 | 0 | 170335 | 170335 |
| 1 | weekday_mean | 22306 | 7312 | 0 | 170615 | 170615 |
| 3 | buffered_weekday_mean | 27873 | 18126 | 0 | 208802 | 208802 |
| 3 | static_reference | 27873 | 9161 | 0 | 163092 | 163092 |
| 3 | weekday_mean | 27873 | 8928 | 0 | 169213 | 169213 |
| 7 | buffered_weekday_mean | 38995 | 24729 | 0 | 206943 | 206943 |
| 7 | static_reference | 38995 | 12795 | 0 | 160554 | 160554 |
| 7 | weekday_mean | 38995 | 10368 | 0 | 157899 | 157899 |

Ending stock is reported with no salvage credit or later-period penalty. Service/cost results are sensitive to common starting stock, finite-horizon handling and omitted costs, in addition to lead time and shortage penalty. Aggregated SKU units are economically heterogeneous; uniform synthetic unit costs are a simplifying assumption.

No uncertainty bound is used. In particular, no daily 80%/95% bounds are summed or described as calibrated lead-time/aggregate intervals. The 50% point-forecast buffer has no coverage interpretation.

## Integrity and reproducibility

Synthetic arithmetic/timing tests cover receipts, pipeline position, lost sales, target ceilings, holding/setup/shortage costs, stale/future issues, missing horizons, terminal rules, zero denominators and current/future-sales mutation invariance. The run audits source-date/key cardinality, daily and total stock/pipeline/unit conservation, exact order/receipt lead-time matching, one replay per date, forecast availability and unchanged prior artifact hashes. Companion validation records verify saved metrics and repeat-run behavior.

Loading/initialization **0.747s**; physical simulation **6.536s**; full run before report/manifest **9.796s**. These are local CPU wall times, not a performance benchmark. Implementation defects recorded during execution: **[]**.

Artifacts: initialization, single-date scenario inputs, compressed daily inventory ledger, order/receipt audit, per-SKU/aggregate/weekly metrics, summary, specification record and hash manifest under ignored `data/inventory_simulation/v0.1.0/`. Figure output is ignored under `reports/generated/inventory_simulation/`. Authored code/specification/report belong in the repository.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_inventory.py -v
.\.venv\Scripts\python.exe -m retail_forecasting.inventory --freeze-only
.\.venv\Scripts\python.exe -m retail_forecasting.inventory
.\.venv\Scripts\python.exe scripts/validate_inventory.py
```

The freeze-only command is for the first execution and refuses replacement. A repeat completed simulation command verifies/reports saved artifacts without replaying or overwriting them. Partial started runs are preserved and refused. No final-period sales or performance metrics enter this milestone; validation remains development evidence after point-model selection. Consumed final-test results cannot become a fresh held-out inventory assessment.
