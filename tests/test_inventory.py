"""Synthetic arithmetic and information-timing tests; no real sales or models."""

from fractions import Fraction
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal

from retail_forecasting.inventory.simulation import ForecastBook, simulate_one, summarize


def sales(values, start="2020-01-06"):
    return pd.Series(values, index=pd.date_range(start, periods=len(values)), dtype="int64")


def forecast_frame(origins=("2020-01-06",), predictions=(1.,)):
    return pd.concat([pd.DataFrame({"sku": "SYNTHETIC", "origin": pd.Timestamp(origin),
        "target_date": pd.date_range(origin, periods=28), "predicted_sales": value})
        for origin, value in zip(origins, predictions)], ignore_index=True)


class InventoryTests(unittest.TestCase):
    def test_hand_calculated_receipts_sales_holding_shortage_and_order_costs(self):
        result = simulate_one("SYNTHETIC", sales([3, 4, 5]), None, "static_reference", 1, 5, 2)
        ledger, orders = result.ledger, result.orders
        self.assertEqual(ledger.target_stock.iloc[0], 15)
        self.assertEqual(ledger.order_units.tolist(), [13, 0, 0])
        self.assertEqual(ledger.receipts_units.tolist(), [0, 13, 0])
        self.assertEqual(ledger.fulfilled_units.tolist(), [2, 4, 5])
        self.assertEqual(ledger.unfulfilled_units.tolist(), [1, 0, 0])
        self.assertEqual(ledger.closing_stock.tolist(), [0, 9, 4])
        self.assertEqual(ledger.closing_pipeline_units.tolist(), [13, 0, 0])
        self.assertEqual(orders.received_date.iloc[0], pd.Timestamp("2020-01-07"))
        self.assertEqual(orders.received_units.iloc[0], 13)
        _, aggregate = summarize(ledger, [1., 5.])
        self.assertEqual(aggregate.order_count.tolist(), [1, 1])
        np.testing.assert_allclose(aggregate.holding_cost, [.13, .13], rtol=0, atol=1e-12)
        np.testing.assert_allclose(aggregate.total_simulated_cost, [2.13, 6.13], rtol=0, atol=1e-12)
        np.testing.assert_allclose(aggregate.fulfilled_unit_rate_pct, [100 * 11 / 12] * 2)
        np.testing.assert_allclose(aggregate.average_total_closing_inventory, [13 / 3] * 2)

    def test_lead_two_arrives_on_day_two_not_order_day_or_day_one(self):
        ledger = simulate_one("SYNTHETIC", sales([3, 4, 5]), None, "static_reference", 2, 5, 2).ledger
        self.assertEqual(ledger.receipts_units.tolist(), [0, 0, 13])
        self.assertEqual(ledger.unfulfilled_units.tolist(), [1, 4, 0])
        self.assertEqual(ledger.closing_stock.tolist(), [0, 0, 8])

    def test_lost_sales_are_not_backlogged_or_added_to_future_sales(self):
        ledger = simulate_one("SYNTHETIC", sales([8, 1, 0]), None, "static_reference", 1, 1, 0).ledger
        self.assertEqual(ledger.scenario_input_units.tolist(), [8, 1, 0])
        self.assertEqual(ledger.unfulfilled_units.tolist(), [8, 0, 0])
        self.assertEqual(ledger.closing_stock.tolist(), [0, 2, 2])

    def test_pipeline_prevents_duplicate_order_on_next_weekly_review(self):
        ledger = simulate_one("SYNTHETIC", sales([0] * 15), None, "static_reference", 8, 1, 0).ledger
        self.assertEqual(ledger.order_units.iloc[0], 15)
        self.assertEqual(ledger.inventory_position_before_order.iloc[7], 15)
        self.assertEqual(ledger.order_units.iloc[7], 0)
        self.assertEqual(ledger.receipts_units.iloc[8], 15)
        self.assertEqual(ledger.order_units.gt(0).sum(), 1)

    def test_latest_available_forecast_never_selects_future_issue(self):
        book = ForecastBook(forecast_frame(("2020-01-06", "2020-01-13"), (1., 100.)))
        total, origin, age = book.protection("SYNTHETIC", "2020-01-06", 8)
        self.assertEqual((total, str(origin.date()), age), (8., "2020-01-06", 0))
        self.assertEqual(book.protection("SYNTHETIC", "2020-01-13", 8)[0], 800.)

    def test_stale_forecast_is_explicit_and_no_extrapolation(self):
        book = ForecastBook(forecast_frame())
        self.assertEqual(book.protection("SYNTHETIC", "2020-01-27", 7), (7., pd.Timestamp("2020-01-06"), 21))
        with self.assertRaisesRegex(ValueError, "no extrapolation"):
            book.protection("SYNTHETIC", "2020-01-27", 8)
        with self.assertRaisesRegex(ValueError, "No forecast"):
            book.protection("SYNTHETIC", "2019-12-30", 1)

    def test_current_future_sales_mutation_cannot_change_current_decision(self):
        book = ForecastBook(forecast_frame(("2020-01-06", "2020-01-13"), (2., 3.)))
        original = sales([2] * 14)
        changed = original.copy()
        changed.loc[changed.index >= "2020-01-13"] = 1000
        for policy in ("static_reference", "weekday_mean", "buffered_weekday_mean"):
            with self.subTest(policy=policy):
                before = simulate_one("SYNTHETIC", original, book, policy, 1, 2, 16).ledger
                after = simulate_one("SYNTHETIC", changed, book, policy, 1, 2, 16).ledger
                assert_frame_equal(before.iloc[:7], after.iloc[:7])
                fields = ["opening_stock", "opening_pipeline_units", "receipts_units", "inventory_position_before_order", "forecast_origin", "target_stock", "order_units"]
                assert_frame_equal(before.loc[[7], fields], after.loc[[7], fields])

    def test_terminal_window_is_clipped_and_late_arrival_blocked(self):
        ledger = simulate_one("SYNTHETIC", sales([1, 1, 1]), None, "static_reference", 7, 5, 0).ledger
        self.assertEqual(ledger.protection_days.iloc[0], 3)
        self.assertEqual(ledger.target_stock.iloc[0], 15)
        self.assertTrue(ledger.terminal_order_blocked.iloc[0])
        self.assertEqual(ledger.order_units.sum(), 0)
        self.assertEqual(ledger.unfulfilled_units.sum(), 3)

    def test_buffered_target_uses_point_sum_ceiling_without_rounding_points(self):
        book = ForecastBook(forecast_frame(predictions=(.25,)))
        mean = simulate_one("SYNTHETIC", sales([0, 0, 0]), book, "weekday_mean", 1, 0, 0).ledger
        buffered = simulate_one("SYNTHETIC", sales([0, 0, 0]), book, "buffered_weekday_mean", 1, 0, 0).ledger
        self.assertEqual(mean.forecast_window_sum.iloc[0], .75)
        self.assertEqual(mean.target_stock.iloc[0], 1)
        self.assertEqual(buffered.target_stock.iloc[0], 2)

    def test_zero_denominator_has_explicit_undefined_status(self):
        ledger = simulate_one("SYNTHETIC", sales([0, 0, 0]), None, "static_reference", 1, 0, 0).ledger
        individual, aggregate = summarize(ledger, [1., 5.])
        self.assertTrue(individual.fulfilled_unit_rate_pct.isna().all())
        self.assertTrue(aggregate.fulfilled_unit_rate_pct.isna().all())
        self.assertTrue(aggregate.rate_status.eq("undefined_zero_input_units").all())
        self.assertTrue(aggregate.simulated_cost_difference_pct.isna().all())

    def test_reference_can_use_exact_training_fraction(self):
        ledger = simulate_one("SYNTHETIC", sales([0] * 7), None, "static_reference", 1, Fraction(1, 7), 0).ledger
        self.assertEqual(ledger.target_stock.iloc[0], 1)

    def test_invalid_sales_calendar_values_or_lead_are_rejected(self):
        for values in (sales([-1, 0]), sales([1, 2, 3]).drop(pd.Timestamp("2020-01-07"))):
            with self.subTest(values=values.to_list()), self.assertRaises(ValueError):
                simulate_one("SYNTHETIC", values, None, "static_reference", 1, 1, 0)
        with self.assertRaisesRegex(ValueError, "same-day"):
            simulate_one("SYNTHETIC", sales([1, 2]), None, "static_reference", 0, 1, 0)

    def test_forecast_actuals_duplicate_dates_and_short_windows_rejected(self):
        for frame in (forecast_frame().assign(actual_sales=1), pd.concat([forecast_frame(), forecast_frame()]), forecast_frame().iloc[:-1]):
            with self.assertRaises(ValueError):
                ForecastBook(frame)

    def test_completed_run_verifies_saved_results_without_replay(self):
        from retail_forecasting.inventory.experiment import run
        cache = Path(__file__).resolve().parents[1] / ".cache"
        cache.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=cache) as folder:
            root = Path(folder)
            (root / "manifest.json").write_text("{}")
            with patch("retail_forecasting.inventory.experiment.verify_completed", return_value={"saved": True}) as verify, \
                 patch("retail_forecasting.inventory.experiment.show"), \
                 patch("retail_forecasting.inventory.experiment.execute", side_effect=AssertionError("replay")):
                self.assertEqual(run(root, root), {"saved": True})
                verify.assert_called_once_with(root, root)

    def test_started_incomplete_run_is_not_overwritten(self):
        from retail_forecasting.inventory.experiment import run
        cache = Path(__file__).resolve().parents[1] / ".cache"
        with tempfile.TemporaryDirectory(dir=cache) as folder:
            root = Path(folder)
            (root / "specification-record.json").write_text(json.dumps({"source_and_specification_sha256": {}, "protected_artifact_sha256": {}}))
            (root / "started.json").write_text("{}")
            with patch("retail_forecasting.inventory.experiment.execute", side_effect=AssertionError("replay")):
                with self.assertRaisesRegex(ValueError, "already started"):
                    run(root, root)


if __name__ == "__main__":
    unittest.main()
