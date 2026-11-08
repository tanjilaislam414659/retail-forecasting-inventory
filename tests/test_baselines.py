"""Hand-checkable forecasts, calendar alignment, onset/scales, and leakage guards."""

import unittest

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal, assert_series_equal

from retail_forecasting.baselines import MODELS, forecast, seasonal_scale
from retail_forecasting.baseline_validation import adjust_history, first_observations, issue_forecasts, training_scales
from retail_forecasting.metrics import summarize


class ForecastTests(unittest.TestCase):
    def setUp(self):
        self.origin = pd.Timestamp("2011-06-06")
        self.series = pd.Series(np.arange(140, dtype=float),
                                index=pd.date_range(self.origin - pd.Timedelta(days=112), periods=140))

    def test_seasonal_naive_repeats_only_last_observed_week(self):
        result = forecast(self.series, self.origin, "seasonal_naive")
        np.testing.assert_array_equal(result, np.tile(np.arange(105, 112), 4))
        self.assertEqual(result.index[0], self.origin)
        self.assertEqual(result.index[-1], self.origin + pd.Timedelta(days=27))

    def test_recent_mean_uses_previous_28_calendar_days_including_zeros(self):
        result = forecast(self.series, self.origin, "recent_mean")
        np.testing.assert_array_equal(result, np.full(28, 97.5))  # mean of 84 through 111
        with_zeros = self.series.copy()
        with_zeros.loc[self.origin - pd.Timedelta(days=28):self.origin - pd.Timedelta(days=1)] = 0
        self.assertTrue(forecast(with_zeros, self.origin, "recent_mean").eq(0).all())

    def test_weekday_mean_averages_eight_prior_occurrences_not_future_weekdays(self):
        result = forecast(self.series, self.origin, "weekday_mean")
        # Prior Mondays are values 56,63,...,105, whose mean is 80.5.
        np.testing.assert_array_equal(result, np.tile(np.arange(80.5, 87), 4))
        thursday = self.origin + pd.Timedelta(days=3)
        result_thursday = forecast(self.series, thursday, "weekday_mean")
        np.testing.assert_array_equal(result_thursday, np.tile(np.arange(83.5, 90), 4))
        self.assertEqual(result_thursday.index[0].dayofweek, 3)

    def test_mutating_sales_on_or_after_origin_cannot_change_any_issued_forecast(self):
        changed = self.series.copy()
        changed.loc[changed.index >= self.origin] = 10**9
        for model in MODELS:
            with self.subTest(model=model):
                assert_series_equal(forecast(self.series, self.origin, model), forecast(changed, self.origin, model))

    def test_later_origins_can_use_already_observed_validation_sales(self):
        changed = self.series.copy()
        changed.loc["2011-06-10"] += 1000
        for model in MODELS:
            assert_series_equal(forecast(self.series, self.origin, model), forecast(changed, self.origin, model))
            later = self.origin + pd.Timedelta(days=7)
            self.assertFalse(forecast(self.series, later, model).equals(forecast(changed, later, model)))

    def test_missing_calendar_day_fails_instead_of_compressing_time(self):
        missing = self.series.drop(self.origin - pd.Timedelta(days=3))
        for model in MODELS:
            with self.assertRaisesRegex(ValueError, "consecutive"):
                forecast(missing, self.origin, model)

    def test_all_targets_stay_inside_validation_and_values_align(self):
        panel = pd.DataFrame({"sku": "A", "date": self.series.index, "sales_units": self.series.to_numpy()})
        result = issue_forecasts(panel, ["2011-06-06"], "2011-06-06", "2011-09-05")
        self.assertEqual(len(result), 84)
        self.assertTrue((result.target_date - result.origin).dt.days.eq(result.horizon_day - 1).all())
        np.testing.assert_array_equal(result.loc[result.model.eq("recent_mean"), "actual_sales"], np.arange(112, 140))
        self.assertTrue(result.target_date.lt("2011-09-05").all())
        with self.assertRaisesRegex(ValueError, "outside validation"):
            issue_forecasts(panel, ["2011-08-15"], "2011-06-06", "2011-09-05")


class HistoryAndMetricTests(unittest.TestCase):
    def test_pre_study_sale_preserves_zero_that_an_in_study_rule_would_remove(self):
        audit = pd.DataFrame({
            "sku": ["21166", "B", "B", "B", "B"],
            "timestamp": pd.to_datetime(["2009-12-01", "2009-12-09", "2009-12-01", "2009-12-01", "2011-06-06"]),
            "quantity": [1, 4, 1, -1, 99], "unit_price": [1, 1, 0, 1, 1],
            "invoice": ["1", "2", "3", "C4", "5"],
            "disposition": ["outside_protocol_window", "selected_sale", "outside_protocol_window", "returns_ledger", "selected_sale"],
        })
        first = first_observations(audit, ["21166", "B"], "2011-06-06")
        panel = pd.DataFrame({"sku": ["21166"] * 4 + ["B"] * 4,
            "date": list(pd.date_range("2009-12-07", periods=4)) * 2,
            "sales_units": [0, 1, 0, 1, 0, 0, 4, 0]})
        adjusted, starts = adjust_history(panel, first, "2011-06-06")
        special = starts.set_index("sku").loc["21166"]
        self.assertEqual(special.excluded_leading_days, 0)
        self.assertEqual(special.zeros_before_first_in_study, 1)
        self.assertEqual(starts.excluded_leading_days.sum(), 2)
        self.assertEqual(len(adjusted), 6)
        self.assertEqual(len(panel), 8)  # original object unchanged

    def test_seasonal_scale_excludes_pairs_crossing_pre_observation_history(self):
        full = pd.Series([0] * 7 + list(range(1, 15)), index=pd.date_range("2010-01-01", periods=21))
        scale, pairs = seasonal_scale(full.iloc[7:])
        self.assertEqual(scale, 7)
        self.assertEqual(pairs, 7)
        self.assertEqual(seasonal_scale(full)[0], 5.5)

    def test_validation_changes_do_not_update_original_training_scales(self):
        panel = pd.DataFrame({"sku": "A", "date": pd.date_range("2011-05-01", periods=70),
                              "sales_units": np.arange(70)})
        expected = training_scales(panel, "2011-06-06")
        panel.loc[panel.date.ge("2011-06-06"), "sales_units"] = 10**9
        assert_frame_equal(expected, training_scales(panel, "2011-06-06"))

    def test_metric_arithmetic_and_macro_weighting(self):
        rows = pd.DataFrame({"model": "m", "sku": ["A", "A", "B", "B"],
            "actual_sales": [2, 4, 10, 0], "predicted_sales": [4, 2, 12, 2]})
        scales = pd.DataFrame({"sku": ["A", "B"], "mase_scale": [1, 4]})
        result = summarize(rows, scales, ["model"]).iloc[0]
        self.assertEqual(result.mae, 2)
        self.assertEqual(result.wape_pct, 50)
        self.assertEqual(result.mean_bias_units, 1)
        self.assertEqual(result.bias_pct, 25)
        self.assertEqual(result.macro_mase, 1.25)  # equal mean of SKU MASEs 2 and 0.5
        self.assertEqual(result.sku_count, 2)

    def test_zero_denominators_are_explicit_and_no_sku_is_dropped(self):
        rows = pd.DataFrame({"model": "m", "sku": ["A", "B"],
            "actual_sales": [0, 0], "predicted_sales": [0, 2]})
        scales = pd.DataFrame({"sku": ["A", "B"], "mase_scale": [0, 1]})
        result = summarize(rows, scales, ["model"]).iloc[0]
        self.assertTrue(pd.isna(result.wape_pct))
        self.assertTrue(pd.isna(result.bias_pct))
        self.assertTrue(pd.isna(result.macro_mase))
        self.assertEqual(result.undefined_mase_skus, 1)
        self.assertEqual(result.sku_count, 2)
        self.assertEqual(result.mae, 1)
        self.assertEqual(result.mean_bias_units, 1)
        self.assertEqual(result.wape_status, "undefined_zero_actual_total")
        self.assertEqual(result.mase_status, "undefined_contains_zero_scale_sku")


if __name__ == "__main__":
    unittest.main()
