"""Synthetic examples exercise causal feature availability and pipeline fitting."""

import unittest

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal

from retail_forecasting.ridge_features import MODEL_FEATURES, NUMERIC_FEATURES, origin_features, training_examples
from retail_forecasting.ridge_model import make_pipeline
from retail_forecasting.ridge_experiment import compare_metrics


class RidgeTests(unittest.TestCase):
    def setUp(self):
        self.origin = pd.Timestamp("2011-06-06")
        self.series = pd.Series(np.arange(140, dtype=float),
            index=pd.date_range(self.origin - pd.Timedelta(days=112), periods=140))

    def test_hand_calculated_origin_features_and_target_alignment(self):
        rows = origin_features(self.series, "A", self.origin)
        self.assertEqual(len(rows), 28)
        self.assertTrue(rows.sales_mean_7.eq(108).all())
        self.assertTrue(rows.sales_mean_28.eq(97.5).all())
        self.assertTrue(rows.sales_mean_56.eq(83.5).all())
        np.testing.assert_allclose(rows.sales_std_28, np.std(np.arange(84, 112), ddof=0))
        self.assertTrue(rows.zero_share_28.eq(0).all())
        np.testing.assert_array_equal(rows.weekday_mean_8, np.tile(np.arange(80.5, 87), 4))
        self.assertEqual(rows.target_date.iloc[-1], self.origin + pd.Timedelta(days=27))
        self.assertTrue((rows.target_date - rows.origin).dt.days.eq(rows.horizon_day - 1).all())
        self.assertEqual(rows.target_weekday.tolist(), [str(i) for i in range(7)] * 4)
        self.assertTrue(rows.history_end.lt(rows.origin).all())

    def test_zeros_are_retained_and_std_convention_is_population(self):
        series = self.series.copy()
        series.loc[self.origin - pd.Timedelta(days=28):self.origin - pd.Timedelta(days=15)] = 0
        rows = origin_features(series, "A", self.origin)
        self.assertTrue(rows.zero_share_28.eq(0.5).all())
        expected = np.array([0] * 14 + list(range(98, 112)))
        self.assertAlmostEqual(rows.sales_std_28.iloc[0], np.std(expected, ddof=0))

    def test_changing_sales_on_or_after_origin_changes_neither_features_nor_predictions(self):
        original = origin_features(self.series, "A", self.origin)
        changed = self.series.copy()
        changed.loc[changed.index >= self.origin] = 10**9
        changed_features = origin_features(changed, "A", self.origin)
        assert_frame_equal(original, changed_features)
        pipeline = make_pipeline().fit(original[MODEL_FEATURES], np.arange(28))  # synthetic only
        np.testing.assert_array_equal(pipeline.predict(original[MODEL_FEATURES]), pipeline.predict(changed_features[MODEL_FEATURES]))

    def test_later_origin_refreshes_observed_features_without_changing_earlier_issue(self):
        changed = self.series.copy()
        changed.loc["2011-06-10"] += 1000
        assert_frame_equal(origin_features(self.series, "A", self.origin), origin_features(changed, "A", self.origin))
        later = self.origin + pd.Timedelta(days=7)
        self.assertFalse(origin_features(self.series, "A", later).equals(origin_features(changed, "A", later)))

    def test_gap_in_required_history_is_not_silently_compressed(self):
        with self.assertRaisesRegex(ValueError, "56 preceding"):
            origin_features(self.series.drop(self.origin - pd.Timedelta(days=3)), "A", self.origin)

    def test_training_origin_eligibility_and_all_targets_precede_cutoff(self):
        dates = pd.date_range("2011-01-03", "2011-07-31")
        panel = pd.DataFrame({"sku": "A", "date": dates, "sales_units": np.arange(len(dates))})
        rows = training_examples(panel)
        self.assertEqual(rows.origin.min(), pd.Timestamp("2011-02-28"))
        self.assertEqual(rows.origin.max(), pd.Timestamp("2011-05-09"))
        self.assertEqual(rows.target_date.max(), pd.Timestamp("2011-06-05"))
        self.assertTrue(rows.origin.dt.dayofweek.eq(0).all())
        self.assertTrue(rows.groupby(["sku", "origin"]).size().eq(28).all())
        self.assertTrue(rows.target_date.lt("2011-06-06").all())
        changed = panel.copy()
        changed.loc[changed.date.ge("2011-06-06"), "sales_units"] = 10**9
        assert_frame_equal(rows, training_examples(changed))

    def test_each_sku_gets_only_origins_with_its_own_retained_history(self):
        dates = pd.date_range("2011-01-03", "2011-06-05")
        a = pd.DataFrame({"sku": "A", "date": dates, "sales_units": 1})
        b = a.loc[a.date.ge("2011-02-07")].assign(sku="B")
        rows = training_examples(pd.concat([a, b]))
        self.assertEqual(rows.loc[rows.sku.eq("B"), "origin"].min(), pd.Timestamp("2011-04-04"))
        self.assertGreater(rows.loc[rows.sku.eq("A"), "origin"].nunique(), rows.loc[rows.sku.eq("B"), "origin"].nunique())

    def test_preprocessors_fit_only_training_and_do_not_learn_validation_categories(self):
        train = origin_features(self.series, "A", self.origin)
        pipeline = make_pipeline().fit(train[MODEL_FEATURES], np.arange(28))
        preprocess = pipeline.named_steps["preprocessing"]
        scaler = preprocess.named_transformers_["numeric"]
        encoder = preprocess.named_transformers_["categorical"]
        np.testing.assert_allclose(scaler.mean_, train[NUMERIC_FEATURES].mean())
        self.assertEqual(scaler.n_samples_seen_, 28)
        before = scaler.mean_.copy()
        categories_before = [values.copy() for values in encoder.categories_]
        validation = train.copy().assign(sku="UNSEEN", target_month="12")
        validation[NUMERIC_FEATURES] = validation[NUMERIC_FEATURES] + 10**6
        pipeline.predict(validation[MODEL_FEATURES])
        np.testing.assert_array_equal(scaler.mean_, before)
        for actual, expected in zip(encoder.categories_, categories_before):
            np.testing.assert_array_equal(actual, expected)
        self.assertNotIn("UNSEEN", encoder.categories_[0])
        self.assertNotIn("12", encoder.categories_[2])
        self.assertEqual(pipeline.named_steps["ridge"].alpha, 1.0)

    def test_comparison_uses_primary_metric_and_explicit_zero_relative_denominator(self):
        data = pd.DataFrame({"model": ["ridge", "weekday_mean"], "macro_mase": [2, 1],
            "mae": [2, 1], "wape_pct": [20, 10], "mean_bias_units": [1, 0], "bias_pct": [10, 0]})
        comparison = compare_metrics(data, []).iloc[0]
        self.assertEqual(comparison.ridge_result, "loss")
        self.assertEqual(comparison.macro_mase_relative_change_pct, 100)
        self.assertTrue(pd.isna(comparison.absolute_bias_relative_change_pct))
        self.assertEqual(comparison.absolute_bias_relative_status, "undefined_zero_baseline")


if __name__ == "__main__":
    unittest.main()
