"""Quantile/interval arithmetic, training boundaries and outcome invariance."""

import unittest

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal

from retail_forecasting.uncertainty import fit_quantiles, historical_forecasts, issue_intervals, score_intervals, summarize_intervals


def calibration_fixture():
    return pd.DataFrame({"sku": "A", "origin": pd.Timestamp("2010-12-27"),
        "target_date": pd.date_range("2011-01-03", periods=4), "horizon_week": 1,
        "actual_sales": [6., 8., 10., 20.], "point_prediction": 10., "residual": [-4., -2., 0., 10.]})


def point_fixture(point=10.):
    return pd.DataFrame({"sku": "A", "origin": pd.Timestamp("2011-06-06"),
        "target_date": [pd.Timestamp("2011-06-06")], "horizon_day": 1, "point_prediction": point})


class UncertaintyTests(unittest.TestCase):
    def test_linear_quantile_arithmetic_and_residual_sign(self):
        quantiles = fit_quantiles(calibration_fixture(), ["A"]).query("horizon_week == 1").set_index("level")
        self.assertAlmostEqual(quantiles.loc[80, "lower_residual_quantile"], -3.4)
        self.assertAlmostEqual(quantiles.loc[80, "upper_residual_quantile"], 7.)
        self.assertAlmostEqual(quantiles.loc[95, "lower_residual_quantile"], -3.85)
        self.assertAlmostEqual(quantiles.loc[95, "upper_residual_quantile"], 9.25)
        wrong_sign = calibration_fixture()
        wrong_sign["residual"] *= -1
        with self.assertRaisesRegex(ValueError, "actual minus"):
            fit_quantiles(wrong_sign, ["A"])

    def test_counts_distinguish_residual_rows_dates_and_origins(self):
        frame = calibration_fixture()
        frame.loc[2:, "target_date"] = frame.loc[:1, "target_date"].to_numpy()
        frame.loc[2:, "origin"] = pd.Timestamp("2010-12-20")
        row = fit_quantiles(frame, ["A"]).query("horizon_week == 1 and level == 80").iloc[0]
        self.assertEqual((row.residual_count, row.unique_target_dates, row.distinct_origins), (4, 2, 2))

    def test_order_nesting_nonnegative_bounds_and_exact_point_preservation(self):
        quantiles = fit_quantiles(calibration_fixture(), ["A"])
        points = point_fixture(0.123456789012345)
        issued = issue_intervals(points, quantiles).set_index("level")
        self.assertTrue(issued.lower.ge(0).all())
        self.assertTrue(issued.upper.ge(issued.lower).all())
        self.assertLessEqual(issued.loc[95, "lower"], issued.loc[80, "lower"])
        self.assertGreaterEqual(issued.loc[95, "upper"], issued.loc[80, "upper"])
        self.assertTrue(issued.point_prediction.eq(points.point_prediction.iloc[0]).all())
        self.assertAlmostEqual(issued.loc[80, "upper"], points.point_prediction.iloc[0] + 7)

    def test_point_is_not_forced_inside_and_negative_bounds_can_collapse_to_zero(self):
        q = fit_quantiles(calibration_fixture(), ["A"])
        q.loc[q.horizon_week.eq(1), "lower_residual_quantile"] = 1.25
        q.loc[q.horizon_week.eq(1), "upper_residual_quantile"] = 2.75
        issued = issue_intervals(point_fixture(), q)
        self.assertTrue(issued.lower.gt(issued.point_prediction).all())
        q.loc[q.horizon_week.eq(1), "lower_residual_quantile"] = -20
        q.loc[q.horizon_week.eq(1), "upper_residual_quantile"] = -11
        issued = issue_intervals(point_fixture(), q)
        self.assertTrue(issued.lower.eq(0).all() and issued.upper.eq(0).all())
        self.assertTrue(issued.point_prediction.eq(10).all())

    def test_inclusive_coverage_interval_score_and_miss_counts(self):
        q = fit_quantiles(calibration_fixture(), ["A"])
        q.loc[q.horizon_week.eq(1), "lower_residual_quantile"] = -9
        q.loc[q.horizon_week.eq(1), "upper_residual_quantile"] = -7
        issued = issue_intervals(point_fixture(), q)
        for actual, covered, score80, score95 in [(0., 0, 12., 42.), (1., 1, 2., 2.),
                (2., 1, 2., 2.), (3., 1, 2., 2.), (4., 0, 12., 42.)]:
            actuals = point_fixture().drop(columns="point_prediction").assign(actual_sales=actual)
            scored = score_intervals(issued, actuals).set_index("level")
            self.assertEqual(scored.loc[80, "covered"], covered)
            self.assertAlmostEqual(scored.loc[80, "interval_score"], score80)
            self.assertAlmostEqual(scored.loc[95, "interval_score"], score95)
            metrics = summarize_intervals(scored.reset_index(), ["level"])
            self.assertTrue((metrics.covered_count + metrics.miss_below_count + metrics.miss_above_count).eq(1).all())

    def test_missing_groups_are_explicit_and_do_not_create_partial_aggregate_metrics(self):
        q = fit_quantiles(calibration_fixture(), ["A", "B"])
        self.assertEqual(len(q), 16)
        self.assertEqual(q.calibration_status.eq("missing_calibration_group").sum(), 14)
        points = pd.concat([point_fixture(), point_fixture().assign(sku="B")], ignore_index=True)
        issued = issue_intervals(points, q)
        actuals = points.drop(columns="point_prediction").assign(actual_sales=10.)
        metrics = summarize_intervals(score_intervals(issued, actuals), ["level"])
        self.assertTrue(metrics.missing_interval_count.eq(1).all())
        self.assertTrue(metrics.coverage_pct.isna().all() and metrics.mean_width.isna().all())
        self.assertTrue(metrics.mean_interval_score.isna().all())

    def test_calibration_date_cutoff_is_strict(self):
        frame = calibration_fixture()
        frame.loc[0, "target_date"] = pd.Timestamp("2011-06-06")
        with self.assertRaisesRegex(ValueError, "cutoff"):
            fit_quantiles(frame, ["A"])

    def test_historical_forecasts_require_complete_history_and_training_only_targets(self):
        dates = pd.date_range("2011-01-01", "2011-06-20")
        history = pd.DataFrame({"sku": "A", "date": dates, "sales_units": np.arange(len(dates))})
        origin = pd.Timestamp("2011-03-07")
        targets = pd.date_range(origin, periods=28)
        grid = pd.DataFrame({"sku": "A", "origin": origin, "target_date": targets, "horizon_day": np.arange(1, 29),
            "actual_sales": history.set_index("date").sales_units.reindex(targets).to_numpy()})
        result = historical_forecasts(history, grid)
        self.assertTrue(result.target_date.lt("2011-06-06").all())
        np.testing.assert_array_equal(result.residual, result.actual_sales - result.point_prediction)
        with self.assertRaisesRegex(ValueError, "56 consecutive"):
            historical_forecasts(history.loc[history.date.ne(origin - pd.Timedelta(days=2))], grid)
        bad = grid.copy()
        bad.loc[0, "target_date"] = pd.Timestamp("2011-06-06")
        with self.assertRaisesRegex(ValueError, "cutoff"):
            historical_forecasts(history, bad)

    def test_validation_outcomes_cannot_change_quantiles_or_already_issued_intervals(self):
        dates = pd.date_range("2011-01-01", "2011-07-03")
        history = pd.DataFrame({"sku": "A", "date": dates, "sales_units": np.arange(len(dates))})
        origin = pd.Timestamp("2011-03-07")
        targets = pd.date_range(origin, periods=28)
        grid = pd.DataFrame({"sku": "A", "origin": origin, "target_date": targets, "horizon_day": np.arange(1, 29),
            "actual_sales": history.set_index("date").sales_units.reindex(targets).to_numpy()})
        changed = history.copy()
        changed.loc[changed.date.ge("2011-06-06"), "sales_units"] = 10**9
        q = fit_quantiles(historical_forecasts(history, grid), ["A"])
        changed_q = fit_quantiles(historical_forecasts(changed, grid), ["A"])
        assert_frame_equal(q, changed_q)
        issued = issue_intervals(point_fixture(), q)
        assert_frame_equal(issued, issue_intervals(point_fixture(), changed_q))
        keys = point_fixture().drop(columns="point_prediction")
        first = score_intervals(issued, keys.assign(actual_sales=0))
        second = score_intervals(issued, keys.assign(actual_sales=10**9))
        assert_frame_equal(first[["point_prediction", "lower", "upper"]], second[["point_prediction", "lower", "upper"]])


if __name__ == "__main__":
    unittest.main()
