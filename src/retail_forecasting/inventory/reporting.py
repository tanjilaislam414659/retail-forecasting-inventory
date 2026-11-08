"""All-grid scenario reporting; no outcome-selected policies or examples."""

import os

import pandas as pd


def table(frame, columns):
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
    for values in frame[columns].itertuples(index=False, name=None):
        lines.append("| " + " | ".join(f"{v:.3f}" if isinstance(v, float) else str(v) for v in values) + " |")
    return "\n".join(lines)


def make_plot(root, metrics):
    os.environ.setdefault("MPLCONFIGDIR", str(root / ".cache/matplotlib"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    path = root / "reports/generated/inventory_simulation/sensitivity-v0.1.0.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(2, 2, figsize=(12, 9), layout="constrained")
    selected = metrics.loc[metrics.shortage_cost_per_unit.eq(1.)]
    for policy, color in (("static_reference", "#555555"), ("weekday_mean", "#0072B2"), ("buffered_weekday_mean", "#D55E00")):
        physical = selected.loc[selected.policy.eq(policy)].sort_values("lead_time_days")
        axes[0, 0].plot(physical.lead_time_days, physical.fulfilled_unit_rate_pct, color=color, marker="o", label=policy)
        axes[0, 1].plot(physical.lead_time_days, physical.average_total_closing_inventory, color=color, marker="o")
        for axis, price in zip(axes[1], [1., 5.]):
            group = metrics.loc[metrics.policy.eq(policy) & metrics.shortage_cost_per_unit.eq(price)].sort_values("lead_time_days")
            axis.plot(group.lead_time_days, group.total_simulated_cost, color=color, marker="o")
    axes[0, 0].set(title="Fulfilled-unit rate (same for either shortage price)", ylabel="Scenario units fulfilled (%)")
    axes[0, 1].set(title="Average total daily closing inventory", ylabel="Synthetic on-hand units summed over SKUs")
    for axis, price in zip(axes[1], [1, 5]):
        axis.set(title=f"Cost with shortage price {price} per lost unit", ylabel="Synthetic total cost units")
    for axis in axes.flat:
        axis.set_xlabel("Synthetic calendar-day lead time")
        axis.set_xticks([1, 3, 7])
        axis.grid(color="#DDDDDD", linewidth=.5)
        axis.spines[["top", "right"]].set_visible(False)
    axes[0, 0].legend(fontsize=8)
    fig.suptitle("Fixed inventory policies: validation scenario sensitivity, not real business savings")
    with path.open("xb") as stream:
        fig.savefig(stream, format="png", dpi=150)
    plt.close(fig)
    return path.relative_to(root).as_posix()


def write_report(root, summary, metrics):
    s = summary
    path = root / "docs/milestone-10.md"
    physical = metrics.loc[metrics.shortage_cost_per_unit.eq(1.)].copy()
    higher_cost = metrics.loc[metrics.shortage_cost_per_unit.eq(5.), ["lead_time_days", "policy", "total_simulated_cost"]].rename(columns={"total_simulated_cost": "cost_at_shortage_5"})
    physical = physical.merge(higher_cost, on=["lead_time_days", "policy"], validate="one_to_one").rename(columns={"total_simulated_cost": "cost_at_shortage_1"})
    lines = ["# Milestone 10 — bounded validation inventory-policy simulation", "",
        "**These are simulated scenario outcomes, not real business savings, uncensored-demand estimates or a new held-out assessment.** The original forecaster, calibration, cohort, scales and consumed final-test artifacts remain unchanged. No model, interval or preparation rule was tuned.", "",
        "[Fixed pre-execution specification](inventory-simulation-spec.md) and `configs/inventory-simulation.json` define all policies, stock, cost assumptions and daily timing. `data/inventory_simulation/v0.1.0/specification-record.json` records their code/input hashes and UTC time before execution.", "",
        "## Replay and assumptions", "",
        f"Replay **{s['unique_sku_date_inputs']:,} unique SKU/date inputs**, 100 SKUs over **2011-06-06 through 2011-09-04**. Each physical policy/lead alternative sees **{s['observed_positive_sales_units_per_physical_alternative']:,} observed positive-sales units once**. Overlapping forecast horizons are not counted as additional sales.", "",
        "Observed positive sales are only an exogenous scenario input; historical stockouts, availability and lost demand are unknown. The modelled lost units therefore are not measured business shortages. Returns, procurement, variable transport, capacity, case packs, spoilage and in-transit costs are excluded.", "",
        "Three fixed policies: static reference from the original pre-validation 56-day mean; weekly weekday-mean order-up-to; and its fixed 1.5 multiplier variant. All receive identical synthetic initial stock per SKU/lead time, `ceil(training mean × (L+7))`, and no initial pipeline/backlog. Reference means/targets use exact rational arithmetic over integer training totals; forecast sums preserve the saved floating-point point values.", "",
        "Lead times are 1, 3 and 7 calendar days. On each day, receive old orders first; review/order on Mondays before observing that day's sales; fulfill up to available stock; lose remaining units without backlog; charge end-of-day inventory. Order quantity is max(0, target minus on-hand-plus-pipeline). No order arrives on its placement date.", "",
        "Synthetic holding cost is 0.01 per closing on-hand unit/day, positive SKU-order setup cost is 1, and shortage prices are 1 and 5 per lost unit. These are artificial cost units, not an estimated currency. Purchase cost and salvage credit are absent. Initial stock is not charged as a purchase.", "",
        f"There are **{s['physical_trajectories']:,} continuous SKU/policy/lead trajectories**, **{s['ledger_rows']:,} daily rows**, **{s['order_rows']:,} positive orders**, **{s['economic_sku_rows']:,} per-SKU economic rows**, and **{s['aggregate_scenario_rows']} aggregate comparison rows**. Each physical ledger is priced twice; different shortage prices never cause a second replay or different decisions.", "",
        "## Actual fixed-grid outcomes", "",
        "Fulfilled-unit rate pools fulfilled/replayed units across SKUs. Shortages are unfulfilled scenario units. Average inventory below is mean daily closing inventory summed over all 100 SKUs, not physical volume/value. Order count counts positive SKU orders, not consolidated truck deliveries. Costs include holding + lost-unit penalty + positive-order setup.", "",
        table(physical, ["lead_time_days", "policy", "fulfilled_unit_rate_pct", "unfulfilled_units", "shortage_sku_days", "average_total_closing_inventory", "order_count", "cost_at_shortage_1", "cost_at_shortage_5"]), "",
        "### Cost components and reference-relative differences", "",
        table(metrics, ["lead_time_days", "shortage_cost_per_unit", "policy", "holding_cost", "order_setup_cost", "shortage_cost", "total_simulated_cost", "simulated_cost_difference_pct", "fulfilled_rate_difference_pp"]), "",
        "Negative simulated cost differences mean lower cost under these particular invented assumptions, not verified savings. No winner is automatically selected, and no parameters change after this table. More buffer can reduce lost units while increasing stock/holding cost; shortage-price sensitivity changes the accounting weight of those tradeoffs without changing physical trajectories.", "",
        f"![All predefined scenario sensitivities](../{s['plot']})", "",
        "## Timing, forecast aging and terminal limitations", "",
        "Each SKU has one 91-day chronological ledger per policy/lead, with no reset at an overlapping forecast origin. Saved forecasts are used only at or after their issue date, and every protection target remains inside the chosen issue's 28-day horizon. No actual-sales columns from saved forecasts are loaded.", "",
        f"There are **{s['forecast_reviews']:,} forecast-policy review rows**; ages in days and counts are **{s['aged_forecast_review_counts']}**. The last three Mondays use the Aug 8 issue aged 7, 14 and 21 days. These stale final-week forecasts and a fixed static reference are deliberate bounded-development choices, not an updated weekly forecasting service.", "",
        f"Protection windows are truncated at Sep 4. Orders arriving on/after Sep 5 are disallowed: **{s['late_arrival_ineligible_reviews']} review rows** have ineligible arrival dates; **{s['positive_suggested_orders_suppressed_at_terminal']}** would otherwise suggest a positive order. Terminal truncation/order suppression affects comparisons and is not a recommended continuing-business policy.", "",
        table(physical, ["lead_time_days", "policy", "starting_stock", "ending_stock", "ending_pipeline_units", "ordered_units", "received_units"]), "",
        "Ending stock is reported with no salvage credit or later-period penalty. Service/cost results are sensitive to common starting stock, finite-horizon handling and omitted costs, in addition to lead time and shortage penalty. Aggregated SKU units are economically heterogeneous; uniform synthetic unit costs are a simplifying assumption.", "",
        "No uncertainty bound is used. In particular, no daily 80%/95% bounds are summed or described as calibrated lead-time/aggregate intervals. The 50% point-forecast buffer has no coverage interpretation.", "",
        "## Integrity and reproducibility", "",
        "Synthetic arithmetic/timing tests cover receipts, pipeline position, lost sales, target ceilings, holding/setup/shortage costs, stale/future issues, missing horizons, terminal rules, zero denominators and current/future-sales mutation invariance. The run audits source-date/key cardinality, daily and total stock/pipeline/unit conservation, exact order/receipt lead-time matching, one replay per date, forecast availability and unchanged prior artifact hashes. Companion validation records verify saved metrics and repeat-run behavior.", "",
        f"Loading/initialization **{s['load_seconds']:.3f}s**; physical simulation **{s['simulation_seconds']:.3f}s**; full run before report/manifest **{s['wall_seconds']:.3f}s**. These are local CPU wall times, not a performance benchmark. Implementation defects recorded during execution: **{s['implementation_defects']}**.", "",
        "Artifacts: initialization, single-date scenario inputs, compressed daily inventory ledger, order/receipt audit, per-SKU/aggregate/weekly metrics, summary, specification record and hash manifest under ignored `data/inventory_simulation/v0.1.0/`. Figure output is ignored under `reports/generated/inventory_simulation/`. Authored code/specification/report belong in the repository.", "",
        "```powershell", ".\\.venv\\Scripts\\python.exe -m unittest discover -s tests -p test_inventory.py -v",
        ".\\.venv\\Scripts\\python.exe -m retail_forecasting.inventory --freeze-only",
        ".\\.venv\\Scripts\\python.exe -m retail_forecasting.inventory",
        ".\\.venv\\Scripts\\python.exe scripts/validate_inventory.py", "```", "",
        "The freeze-only command is for the first execution and refuses replacement. A repeat completed simulation command verifies/reports saved artifacts without replaying or overwriting them. Partial started runs are preserved and refused. No final-period sales or performance metrics enter this milestone; validation remains development evidence after point-model selection. Consumed final-test results cannot become a fresh held-out inventory assessment.", ""]
    with path.open("x", encoding="utf-8") as stream:
        stream.write("\n".join(lines))
    return path.relative_to(root).as_posix()
