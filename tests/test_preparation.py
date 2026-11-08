"""Synthetic contract tests: no network, retail downloads, or model training."""

import json
from pathlib import Path
import unittest

import pandas as pd
from pandas.testing import assert_frame_equal

from retail_forecasting.preparation import build_panels, classify, select_skus, split_labels, validate_protocol

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "configs/preparation.json").read_text(encoding="utf-8"))


def records(rows):
    result = []
    for index, overrides in enumerate(rows):
        row = {"invoice": "123456", "sku": "12345A", "description": "TEST PRODUCT",
               "quantity": 2, "timestamp": pd.Timestamp("2010-01-04"), "unit_price": 1.5,
               "country": "United Kingdom", "source_sheet": "A", "source_row": index + 2,
               "record_id": f"A:{index + 2}", "record_key": str(index)}
        row.update(overrides)
        result.append(row)
    return pd.DataFrame(result)


class PreparationTests(unittest.TestCase):
    def test_split_boundaries_are_half_open_and_weeks_do_not_straddle(self):
        validate_protocol(CONFIG)
        dates = pd.Series(pd.to_datetime(["2009-12-06", "2009-12-07", "2011-06-05", "2011-06-06",
                                         "2011-09-04", "2011-09-05", "2011-12-04", "2011-12-05"]))
        self.assertEqual(split_labels(dates, CONFIG).tolist(),
                         ["outside", "train", "train", "validation", "validation", "test", "test", "outside"])
        with self.assertRaises(ValueError):
            validate_protocol(CONFIG | {"test_start": "2011-09-06"})

    def test_cross_sheet_matching_preserves_within_sheet_multiplicity(self):
        frame = records([
            {"record_key": "same"}, {"record_key": "same"},
            {"record_key": "same", "source_sheet": "B", "record_id": "B:2"},
            {"record_key": "same", "source_sheet": "B", "record_id": "B:3"},
            {"record_key": "same", "source_sheet": "B", "record_id": "B:4"},
            {"record_key": "different", "source_sheet": "B", "record_id": "B:5", "quantity": 3},
        ])
        classified, _ = classify(frame, CONFIG)
        self.assertEqual(classified.disposition.tolist(), ["eligible_sale", "eligible_sale", "cross_sheet_copy",
                                                          "cross_sheet_copy", "eligible_sale", "eligible_sale"])
        self.assertEqual(classified.loc[2, "canonical_record_id"], "A:2")
        self.assertEqual(classified.loc[3, "canonical_record_id"], "A:3")

    def test_return_routing_and_extremes_do_not_corrupt_positive_target(self):
        frame = records([
            {"quantity": 80000}, {"quantity": -2}, {"invoice": "C123456", "quantity": 2},
            {"unit_price": 0}, {"sku": "POST"}, {"quantity": 0}, {"quantity": 1.5},
            {"description": None}, {"invoice": None}, {"timestamp": pd.Timestamp("2011-12-09")},
            {"unit_price": float("inf")},
        ])
        classified, _ = classify(frame, CONFIG)
        self.assertEqual(classified.disposition.tolist(), [
            "eligible_sale", "returns_ledger", "returns_ledger", "nonpositive_or_invalid_price",
            "non_product_code", "zero_quantity", "invalid_required_value", "eligible_sale",
            "invalid_required_value", "outside_protocol_window", "nonpositive_or_invalid_price",
        ])
        self.assertTrue(classified.loc[0, "extreme_order"])
        self.assertIn("negative_quantity", classified.loc[1, "reasons"])

    def test_held_out_changes_cannot_change_sku_selection(self):
        dates = pd.date_range("2010-01-04", "2011-05-30", freq="W-MON")
        training = pd.DataFrame({"sku": "12345", "date": dates, "quantity": 1})
        validation = pd.DataFrame({"sku": ["99999", "12345"], "date": pd.to_datetime(["2011-06-06", "2011-09-05"]),
                                   "quantity": [10**9, 10**9]})
        expected = select_skus(training, CONFIG)
        actual = select_skus(pd.concat([training, validation], ignore_index=True), CONFIG)
        assert_frame_equal(actual, expected)
        self.assertEqual(actual.sku.tolist(), ["12345"])

    def test_dense_grid_keeps_pre_sale_and_post_sale_zeros_and_conserves_units(self):
        sales = pd.DataFrame({"sku": ["12345", "12345", "12345"],
                              "date": pd.to_datetime(["2010-01-04", "2011-06-06", "2011-09-05"]),
                              "quantity": [3, 5, 7]})
        cohort = pd.DataFrame({"sku": ["12345"]})
        daily, weekly, assessment = build_panels(sales, cohort, CONFIG)
        self.assertEqual(len(daily), 728)
        self.assertEqual(len(weekly), 104)
        self.assertEqual(daily.sales_units.sum(), 15)
        self.assertEqual(weekly.sales_units.sum(), 15)
        self.assertEqual(daily.iloc[0].sales_units, 0)
        self.assertEqual(daily.iloc[-1].sales_units, 0)
        self.assertTrue(weekly.days_in_period.eq(7).all())
        self.assertEqual(assessment["frequency"], "weekly")
        self.assertEqual(assessment["forecast_horizon_periods"], 4)
        changed = sales.copy()
        changed.loc[changed.date.ge(CONFIG["validation_start"]), "quantity"] = 100000
        self.assertEqual(build_panels(changed, cohort, CONFIG)[2], assessment)


if __name__ == "__main__":
    unittest.main()
