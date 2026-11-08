"""Continuous lost-sales inventory accounting with origin-available forecasts."""

from bisect import bisect_right
from dataclasses import dataclass
import math

import numpy as np
import pandas as pd

POLICIES = {"static_reference": None, "weekday_mean": 1., "buffered_weekday_mean": 1.5}
ORDER_COLUMNS = ["lead_time_days", "policy", "sku", "order_id", "order_date", "due_date", "order_units", "received_date", "received_units"]


def require(condition, message):
    if not condition:
        raise ValueError(message)


class ForecastBook:
    """Saved point forecasts only. Do not substitute future issues or actuals."""

    def __init__(self, frame):
        require("actual_sales" not in frame, "Actual sales must not enter the forecast book")
        require(not frame.empty and not frame.duplicated(["sku", "origin", "target_date"]).any(), "Empty/duplicate forecast book")
        require(np.isfinite(frame.predicted_sales).all() and frame.predicted_sales.ge(0).all(), "Invalid point forecast")
        self.windows, self.origins = {}, {}
        for (sku, origin), group in frame.groupby(["sku", "origin"], sort=True):
            dates = pd.DatetimeIndex(group.sort_values("target_date").target_date)
            require(len(group) == 28 and dates.equals(pd.date_range(origin, periods=28)), "Forecasts need complete aligned 28-day windows")
            self.windows[sku, origin] = group.set_index("target_date").predicted_sales.sort_index()
            self.origins.setdefault(sku, []).append(origin)

    def protection(self, sku, review_date, days):
        review_date = pd.Timestamp(review_date)
        available = self.origins.get(sku, [])
        position = bisect_right(available, review_date) - 1
        require(position >= 0, "No forecast issued by review time")
        origin = available[position]
        targets = pd.date_range(review_date, periods=days)
        values = self.windows[sku, origin].reindex(targets)
        require(values.notna().all(), "Required dates outside available forecast horizon; no extrapolation")
        return float(values.sum()), origin, (review_date - origin).days


@dataclass
class Replay:
    ledger: pd.DataFrame
    orders: pd.DataFrame


def simulate_one(sku, sales, book, policy, lead_time_days, reference_mean, starting_stock,
                 holding_cost=.01, setup_cost=1., review_days=7):
    """One SKU/policy/lead-time trajectory; economic prices do not affect decisions."""
    require(policy in POLICIES, "Unknown fixed inventory policy")
    require(type(lead_time_days) is int and lead_time_days >= 1, "Lead time must be a positive integer; no same-day replenishment")
    require(type(starting_stock) is int and starting_stock >= 0, "Invalid starting stock")
    require(np.isfinite(float(reference_mean)) and reference_mean >= 0, "Invalid pre-validation mean")
    require(holding_cost >= 0 and setup_cost >= 0 and review_days == 7, "Invalid fixed costs or review period")
    require(not sales.empty and sales.index.is_unique and sales.index.equals(pd.date_range(sales.index.min(), sales.index.max())), "Sales need one consecutive calendar-day record")
    require(sales.index[0].dayofweek == 0, "Scenario starts on a Monday")
    require(np.isfinite(sales).all() and sales.ge(0).all() and sales.mod(1).eq(0).all(), "Scenario input must be nonnegative integer units")
    on_hand = starting_stock
    pipeline = {}
    records, orders = [], []
    end_exclusive = sales.index[-1] + pd.Timedelta(days=1)
    for index, day in enumerate(sales.index):
        opening_stock = on_hand
        opening_pipeline = sum(order["order_units"] for rows in pipeline.values() for order in rows)
        incoming = pipeline.pop(day, [])
        receipts = sum(order["order_units"] for order in incoming)
        for order in incoming:
            order["received_date"] = day
            order["received_units"] = order["order_units"]
        on_hand += receipts
        inventory_position = on_hand + opening_pipeline - receipts
        review = day.dayofweek == 0
        quantity, requested_quantity, target, protection, forecast_sum, issued, age, due = 0, 0, None, None, None, None, None, None
        blocked_terminal = False
        if review:
            protection = min(lead_time_days + review_days, len(sales) - index)
            if policy == "static_reference":
                target = math.ceil(reference_mean * protection)
            else:
                forecast_sum, issued, age = book.protection(sku, day, protection)
                target = math.ceil(POLICIES[policy] * forecast_sum)
            due = day + pd.Timedelta(days=lead_time_days)
            blocked_terminal = due >= end_exclusive
            requested_quantity = max(0, target - inventory_position)
            if not blocked_terminal:
                quantity = requested_quantity
            if quantity:
                order = {"lead_time_days": lead_time_days, "policy": policy, "sku": sku,
                    "order_id": f"{lead_time_days}:{policy}:{sku}:{len(orders) + 1}",
                    "order_date": day, "due_date": due, "order_units": quantity,
                    "received_date": None, "received_units": 0}
                orders.append(order)
                pipeline.setdefault(due, []).append(order)
        # Sales are read only after today's pre-sales ordering decision is complete.
        scenario_input = int(sales.loc[day])
        fulfilled = min(on_hand, scenario_input)
        lost = scenario_input - fulfilled
        on_hand -= fulfilled
        closing_pipeline = opening_pipeline - receipts + quantity
        records.append({"lead_time_days": lead_time_days, "policy": policy, "sku": sku, "date": day,
            "opening_stock": opening_stock, "opening_pipeline_units": opening_pipeline, "receipts_units": receipts,
            "review": review, "inventory_position_before_order": inventory_position,
            "protection_days": protection, "reference_mean": float(reference_mean),
            "forecast_origin": issued, "forecast_age_days": age, "forecast_window_sum": forecast_sum,
            "target_stock": target, "terminal_order_blocked": blocked_terminal,
            "suggested_order_units": requested_quantity, "order_units": quantity, "order_due_date": due if quantity else None,
            "scenario_input_units": scenario_input, "fulfilled_units": fulfilled, "unfulfilled_units": lost,
            "closing_stock": on_hand, "closing_pipeline_units": closing_pipeline,
            "holding_cost": holding_cost * on_hand, "order_setup_cost": setup_cost if quantity else 0.})
    ledger = pd.DataFrame(records)
    for name in ("forecast_origin", "order_due_date"):
        ledger[name] = pd.to_datetime(ledger[name])
    for name in ("protection_days", "forecast_age_days", "forecast_window_sum", "target_stock"):
        ledger[name] = pd.to_numeric(ledger[name], errors="raise").astype(float)
    return Replay(ledger, pd.DataFrame(orders, columns=ORDER_COLUMNS))


def summarize(ledger, shortage_prices):
    """Price a physical trajectory twice without creating duplicate sales ledgers."""
    data = ledger.assign(shortage_sku_day=ledger.unfulfilled_units.gt(0).astype(int),
        positive_order=ledger.order_units.gt(0).astype(int))
    keys = ["lead_time_days", "policy", "sku"]
    physical = data.groupby(keys, sort=True).agg(days=("date", "size"),
        scenario_input_units=("scenario_input_units", "sum"), fulfilled_units=("fulfilled_units", "sum"),
        unfulfilled_units=("unfulfilled_units", "sum"), shortage_sku_days=("shortage_sku_day", "sum"),
        inventory_unit_days=("closing_stock", "sum"), order_count=("positive_order", "sum"),
        ordered_units=("order_units", "sum"), received_units=("receipts_units", "sum"),
        starting_stock=("opening_stock", "first"), ending_stock=("closing_stock", "last"),
        ending_pipeline_units=("closing_pipeline_units", "last"), holding_cost=("holding_cost", "sum"),
        order_setup_cost=("order_setup_cost", "sum")).reset_index()
    economic = physical.merge(pd.DataFrame({"shortage_cost_per_unit": shortage_prices}), how="cross")
    economic["shortage_cost"] = economic.unfulfilled_units * economic.shortage_cost_per_unit
    economic["total_simulated_cost"] = economic.holding_cost + economic.order_setup_cost + economic.shortage_cost
    economic["fulfilled_unit_rate_pct"] = (100 * economic.fulfilled_units / economic.scenario_input_units.where(economic.scenario_input_units.ne(0)))
    economic["rate_status"] = np.where(economic.scenario_input_units.eq(0), "undefined_zero_input_units", "defined")
    economic["average_closing_inventory"] = economic.inventory_unit_days / economic.days
    overall = economic.groupby(["lead_time_days", "shortage_cost_per_unit", "policy"], sort=True).agg(
        sku_count=("sku", "nunique"), sku_days=("days", "sum"), scenario_days=("days", "max"),
        scenario_input_units=("scenario_input_units", "sum"), fulfilled_units=("fulfilled_units", "sum"),
        unfulfilled_units=("unfulfilled_units", "sum"), shortage_sku_days=("shortage_sku_days", "sum"),
        inventory_unit_days=("inventory_unit_days", "sum"), order_count=("order_count", "sum"),
        ordered_units=("ordered_units", "sum"), received_units=("received_units", "sum"),
        starting_stock=("starting_stock", "sum"), ending_stock=("ending_stock", "sum"),
        ending_pipeline_units=("ending_pipeline_units", "sum"), holding_cost=("holding_cost", "sum"),
        order_setup_cost=("order_setup_cost", "sum"), shortage_cost=("shortage_cost", "sum"),
        total_simulated_cost=("total_simulated_cost", "sum")).reset_index()
    overall["fulfilled_unit_rate_pct"] = 100 * overall.fulfilled_units / overall.scenario_input_units.where(overall.scenario_input_units.ne(0))
    overall["rate_status"] = np.where(overall.scenario_input_units.eq(0), "undefined_zero_input_units", "defined")
    overall["average_total_closing_inventory"] = overall.inventory_unit_days / overall.scenario_days
    overall["average_closing_inventory_per_sku"] = overall.inventory_unit_days / overall.sku_days
    reference = overall.loc[overall.policy.eq("static_reference"), ["lead_time_days", "shortage_cost_per_unit", "total_simulated_cost", "fulfilled_unit_rate_pct"]]
    reference = reference.rename(columns={"total_simulated_cost": "reference_simulated_cost", "fulfilled_unit_rate_pct": "reference_fulfilled_rate_pct"})
    overall = overall.merge(reference, on=["lead_time_days", "shortage_cost_per_unit"], validate="many_to_one")
    overall["simulated_cost_difference_pct"] = 100 * (overall.total_simulated_cost - overall.reference_simulated_cost) / overall.reference_simulated_cost.where(overall.reference_simulated_cost.ne(0))
    overall["fulfilled_rate_difference_pp"] = overall.fulfilled_unit_rate_pct - overall.reference_fulfilled_rate_pct
    return economic, overall
