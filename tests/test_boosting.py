"""Native categorical and positive-prediction checks with synthetic data only."""

import copy
from pathlib import Path
import tempfile
import unittest

import joblib
import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal
from threadpoolctl import threadpool_limits

from retail_forecasting.boosting_model import MODEL_PARAMETERS, make_pipeline
from retail_forecasting.ridge_features import CATEGORICAL_FEATURES, MODEL_FEATURES, NUMERIC_FEATURES, origin_features


class BoostingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        n = 840
        index = np.arange(n)
        cls.x = pd.DataFrame({
            "horizon_day": index % 28 + 1, "sales_mean_7": index % 20 + 1.0,
            "sales_mean_28": index % 25 + 2.0, "sales_mean_56": index % 30 + 1.0,
            "sales_std_28": index % 10 + 0.5, "zero_share_28": (index % 7) / 7,
            "weekday_mean_8": index % 15 + 1.0, "sku": np.array(["100", "900", "A"])[index % 3],
            "target_weekday": (index % 7).astype(str), "target_month": (index % 12 + 1).astype(str),
        })[MODEL_FEATURES]
        cls.y = np.where(index % 5 == 0, 0, 1 + index % 9).astype(float)
        with threadpool_limits(limits=1):
            cls.pipeline = make_pipeline().fit(cls.x, cls.y)

    def test_fixed_parameters_and_no_early_stopping(self):
        estimator = self.pipeline.named_steps["estimator"]
        for name, value in MODEL_PARAMETERS.items():
            self.assertEqual(estimator.get_params()[name], value)
        self.assertEqual(estimator.n_iter_, 200)
        self.assertFalse(estimator.do_early_stopping_)

    def test_sku_weekday_month_are_native_unordered_categories_not_scaled_measurements(self):
        transformed = self.pipeline.named_steps["categories"].transform(self.x)
        assert_frame_equal(transformed[NUMERIC_FEATURES], self.x[NUMERIC_FEATURES])
        for name in CATEGORICAL_FEATURES:
            self.assertIsInstance(transformed[name].dtype, pd.CategoricalDtype)
            self.assertFalse(transformed[name].cat.ordered)
        expected = [name in CATEGORICAL_FEATURES for name in MODEL_FEATURES]
        np.testing.assert_array_equal(self.pipeline.named_steps["estimator"].is_categorical_, expected)
        self.assertEqual(self.pipeline.named_steps["categories"].categories_["sku"], ["100", "900", "A"])

    def test_categories_are_training_defined_and_unknowns_do_not_modify_them(self):
        transformer = self.pipeline.named_steps["categories"]
        before = copy.deepcopy(transformer.categories_)
        unknown = self.x.iloc[:28].copy().assign(sku="UNSEEN")
        with self.assertRaisesRegex(ValueError, "Unknown"):
            transformer.transform(unknown)
        self.assertEqual(before, transformer.categories_)
        self.assertEqual(transformer.n_samples_seen_, len(self.x))

    def test_predictions_are_finite_positive_with_zero_targets_retained(self):
        with threadpool_limits(limits=1):
            prediction = self.pipeline.predict(self.x)
        self.assertTrue(np.isfinite(prediction).all())
        self.assertTrue((prediction > 0).all())
        self.assertEqual(self.pipeline.named_steps["categories"].n_samples_seen_, len(self.y))
        self.assertGreater((self.y == 0).sum(), 0)

    def test_saved_model_reload_preserves_predictions_and_category_dictionaries(self):
        cache = Path(__file__).resolve().parents[1] / ".cache"
        cache.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="boosting-test-", dir=cache) as directory:
            path = Path(directory) / "toy.joblib"
            joblib.dump(self.pipeline, path)
            loaded = joblib.load(path)
            with threadpool_limits(limits=1):
                np.testing.assert_array_equal(self.pipeline.predict(self.x), loaded.predict(self.x))
            self.assertEqual(loaded.named_steps["categories"].categories_, self.pipeline.named_steps["categories"].categories_)

    def test_future_sales_mutation_changes_neither_features_nor_issued_predictions(self):
        origin = pd.Timestamp("2011-06-06")
        series = pd.Series(np.arange(140, dtype=float), index=pd.date_range(origin - pd.Timedelta(days=112), periods=140))
        changed = series.copy()
        changed.loc[changed.index >= origin] = 10**9
        original = origin_features(series, "100", origin)[MODEL_FEATURES]
        mutated = origin_features(changed, "100", origin)[MODEL_FEATURES]
        assert_frame_equal(original, mutated)
        with threadpool_limits(limits=1):
            np.testing.assert_array_equal(self.pipeline.predict(original), self.pipeline.predict(mutated))


if __name__ == "__main__":
    unittest.main()
