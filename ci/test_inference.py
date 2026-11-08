"""Hand-calculated unit checks using only committed synthetic fixture values."""

from datetime import date
import unittest

import numpy as np
import pandas as pd

from ci.fixture_engine import synthetic_engine
from retail_forecasting.service.inference import infer_one


class SyntheticInferenceTests(unittest.TestCase):
    def setUp(self):
        self.engine = synthetic_engine()

    def test_hand_calculated_weekday_means_and_interval_arithmetic(self):
        result = self.engine.predict("SYNTHETIC_A", date(2011, 6, 6))
        expected = np.tile([5.5, 7.5, 3.5, 9.5, 4.5, 0., 6.5], 4)
        np.testing.assert_allclose([r.predicted_sales for r in result.predictions], expected, rtol=1e-12, atol=1e-9)
        self.assertEqual(result.predictions[0].interval_80.lower, 3.5)
        self.assertEqual(result.predictions[0].interval_80.upper, 8.5)
        self.assertEqual(result.predictions[0].interval_95.lower, 1.5)
        self.assertEqual(result.predictions[0].interval_95.upper, 12.5)
        saturday = result.predictions[5]
        self.assertEqual(saturday.predicted_sales, 0.)
        self.assertEqual(saturday.interval_80.upper, 3.)  # No Saturday-zero interval rule.

    def test_future_mutation_cannot_change_any_horizon_value(self):
        history = self.engine.histories["SYNTHETIC_A"].copy()
        origin = date(2011, 6, 6)
        before = infer_one(history, self.engine.quantiles, "SYNTHETIC_A", origin)
        history.loc[history.index >= pd.Timestamp(origin)] = 999999
        self.assertEqual(before, infer_one(history, self.engine.quantiles, "SYNTHETIC_A", origin))

    def test_all_dates_cutoff_nonnegative_nested_endpoints(self):
        result = self.engine.predict("SYNTHETIC_B", date(2011, 6, 13))
        self.assertEqual(str(result.history_cutoff), "2011-06-12")
        self.assertEqual(len(result.predictions), 28)
        self.assertEqual(str(result.predictions[-1].target_date), "2011-07-10")
        for row in result.predictions:
            self.assertTrue(0 <= row.interval_95.lower <= row.interval_80.lower <= row.interval_80.upper <= row.interval_95.upper)

    def test_missing_history_or_calibration_refuses_inference(self):
        history = self.engine.histories["SYNTHETIC_A"].drop(pd.Timestamp("2011-06-05"))
        with self.assertRaisesRegex(ValueError, "consecutive"):
            infer_one(history, self.engine.quantiles, "SYNTHETIC_A", date(2011, 6, 6))
        missing = self.engine.quantiles.loc[self.engine.quantiles.horizon_week.ne(4)]
        with self.assertRaisesRegex(ValueError, "Every SKU"):
            infer_one(self.engine.histories["SYNTHETIC_A"], missing, "SYNTHETIC_A", date(2011, 6, 6))

    def test_point_is_preserved_even_outside_empirical_interval(self):
        quantiles = self.engine.quantiles.copy()
        quantiles.loc[quantiles.level.eq(80), "lower_residual_quantile"] = 1
        result = infer_one(self.engine.histories["SYNTHETIC_A"], quantiles, "SYNTHETIC_A", date(2011, 6, 6))
        self.assertEqual(result[0]["predicted_sales"], 5.5)
        self.assertEqual(result[0]["interval_80"]["lower"], 6.5)
