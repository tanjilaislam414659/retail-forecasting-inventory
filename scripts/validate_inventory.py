"""Read-only reconciliation of saved inventory ledgers and economic summaries."""

from io import StringIO
import json
from pathlib import Path
import math

import numpy as np
import pandas as pd

from retail_forecasting.inventory.experiment import audit, verify_completed
from retail_forecasting.inventory.simulation import summarize


def main(root=None):
    root = Path(__file__).resolve().parents[1] if root is None else root
    output = root / "data/inventory_simulation/v0.1.0"
    summary = verify_completed(root, output)
    spec = json.loads((output / "specification-record.json").read_text())
    started = json.loads((output / "started.json").read_text())
    assert pd.Timestamp(spec["specified_before_execution_at_utc"]) < pd.Timestamp(started["executed_at_utc"])
    ledger = pd.read_csv(output / "daily_inventory_ledger.csv.gz", dtype={"sku": str},
        parse_dates=["date", "forecast_origin", "order_due_date"])
    orders = pd.read_csv(output / "orders_receipts.csv.gz", dtype={"sku": str}, parse_dates=["order_date", "due_date", "received_date"])
    inputs = pd.read_csv(output / "validation_scenario_input.csv.gz", dtype={"sku": str}, parse_dates=["date"])
    audit(ledger, orders, inputs)
    np.testing.assert_allclose(ledger.holding_cost, ledger.closing_stock * .01, rtol=1e-12, atol=1e-9)
    np.testing.assert_array_equal(ledger.order_setup_cost, ledger.order_units.gt(0).astype(float))
    assert ledger.loc[ledger.terminal_order_blocked, "order_units"].eq(0).all()
    decisions = ledger.loc[ledger.review & ~ledger.terminal_order_blocked]
    np.testing.assert_array_equal(decisions.order_units, (decisions.target_stock - decisions.inventory_position_before_order).clip(lower=0))
    expected_sku, expected_scenarios = summarize(ledger, [1., 5.])
    for name, frame, keys in (("metrics_by_sku.csv", expected_sku, ["lead_time_days", "policy", "sku", "shortage_cost_per_unit"]),
                             ("scenario_metrics.csv", expected_scenarios, ["lead_time_days", "shortage_cost_per_unit", "policy"])):
        expected = pd.read_csv(StringIO(frame.to_csv(index=False)), dtype={"sku": str})
        actual = pd.read_csv(output / name, dtype={"sku": str})
        pd.testing.assert_frame_equal(actual.sort_values(keys).reset_index(drop=True), expected.sort_values(keys).reset_index(drop=True), check_dtype=False, rtol=1e-11, atol=1e-8)
    initial = pd.read_csv(output / "initialization.csv", dtype={"sku": str})
    exact_start = (initial.history_units * (initial.lead_time_days + 7) + 55) // 56
    np.testing.assert_array_equal(initial.starting_stock, exact_start)
    initialization = initial.set_index(["lead_time_days", "sku"])
    forecasts = pd.read_csv(root / spec["configuration"]["forecast_file"], dtype={"sku": str},
        parse_dates=["origin", "target_date"], usecols=["model", "sku", "origin", "target_date", "predicted_sales"])
    forecasts = forecasts.loc[forecasts.model.eq("weekday_mean")]
    windows = {(sku, origin): rows.set_index("target_date").predicted_sales for (sku, origin), rows in forecasts.groupby(["sku", "origin"])}
    issues = [pd.Timestamp(day) for day in spec["configuration"]["available_forecast_origins"]]
    for row in ledger.loc[ledger.review].itertuples():
        days = min(row.lead_time_days + 7, (pd.Timestamp("2011-09-05") - row.date).days)
        assert row.protection_days == days
        assert row.terminal_order_blocked == (row.date + pd.Timedelta(days=row.lead_time_days) >= pd.Timestamp("2011-09-05"))
        if row.policy == "static_reference":
            history_units = int(initialization.loc[(row.lead_time_days, row.sku), "history_units"])
            assert row.target_stock == (history_units * days + 55) // 56
        else:
            expected_issue = max(issue for issue in issues if issue <= row.date)
            assert row.forecast_origin == expected_issue
            total = float(windows[row.sku, expected_issue].reindex(pd.date_range(row.date, periods=days)).sum())
            np.testing.assert_allclose(row.forecast_window_sum, total, rtol=1e-12, atol=1e-9)
            multiplier = 1.5 if row.policy == "buffered_weekday_mean" else 1.
            assert row.target_stock == math.ceil(multiplier * total)
    for row in expected_scenarios.itertuples():
        assert row.starting_stock + row.received_units == row.fulfilled_units + row.ending_stock
        assert row.ordered_units == row.received_units + row.ending_pipeline_units
        assert row.fulfilled_units + row.unfulfilled_units == row.scenario_input_units
        assert row.scenario_input_units == summary["observed_positive_sales_units_per_physical_alternative"]
        np.testing.assert_allclose(row.total_simulated_cost, row.holding_cost + row.order_setup_cost + row.shortage_cost, rtol=1e-12, atol=1e-8)
    print("PASS: pre-execution specification, prior hashes, one-date sales replay, 81,900 ledger rows, receipt/stock/pipeline conservation, decision timing, exact initialization, cost arithmetic and all per-SKU/scenario metrics. No new simulation or final evaluation performed.")


if __name__ == "__main__":
    main()
