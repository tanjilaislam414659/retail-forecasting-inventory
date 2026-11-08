"""Synthetic tests only: no final-test inputs or outcomes are read."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal

from retail_forecasting.final_evaluation import (OUTPUT, issue_points, join_actuals, run_final,
    save_frame, sku_comparison, verify_hashes, write_json)


class FinalEvaluationTests(unittest.TestCase):
    def fixture(self):
        return pd.DataFrame({"sku": "A", "date": pd.date_range("2011-07-01", "2011-10-02"),
            "sales_units": np.arange(94, dtype=float) % 13})

    def temp(self):
        base = Path(__file__).resolve().parents[1] / ".cache/test-final"
        base.mkdir(parents=True, exist_ok=True)
        return tempfile.TemporaryDirectory(dir=base)

    def test_all_28_predictions_invariant_to_origin_and_future_changes(self):
        history = self.fixture()
        original = issue_points(history, ["2011-09-05"], "2011-12-05")
        changed = history.copy()
        changed.loc[changed.date.ge("2011-09-05"), "sales_units"] = 999999
        assert_frame_equal(original, issue_points(changed, ["2011-09-05"], "2011-12-05"))
        self.assertNotIn("actual_sales", original)
        self.assertTrue(original.history_last_date.lt(original.origin).all())
        self.assertEqual(original.groupby("model").size().tolist(), [28, 28])
        weekday = original.loc[original.model.eq("weekday_mean")]
        past = history.loc[history.date.ge("2011-07-11") & history.date.lt("2011-09-05")]
        expected = past.groupby(past.date.dt.dayofweek).sales_units.mean()
        np.testing.assert_array_equal(weekday.predicted_sales, [expected.loc[d] for d in weekday.target_date.dt.dayofweek])

    def test_alignment_boundary_and_actual_join_do_not_change_predictions(self):
        issued = issue_points(self.fixture(), ["2011-09-05"], "2011-12-05")
        self.assertTrue((issued.target_date - issued.origin).dt.days.eq(issued.horizon_day - 1).all())
        self.assertTrue(issued.horizon_week.eq((issued.horizon_day - 1) // 7 + 1).all())
        scored = join_actuals(issued, self.fixture())
        np.testing.assert_array_equal(issued.predicted_sales, scored.predicted_sales)
        with self.assertRaisesRegex(ValueError, "boundary"):
            issue_points(self.fixture(), ["2011-11-14"], "2011-12-05")
        with self.assertRaisesRegex(ValueError, "Monday"):
            issue_points(self.fixture(), ["2011-09-06"], "2011-12-05")
        with self.assertRaisesRegex(ValueError, "Missing"):
            join_actuals(issued, self.fixture().query("date < '2011-09-05'"))

    def test_exclusive_writes_preserve_original_bytes(self):
        with self.temp() as folder:
            root = Path(folder)
            for name in ("frame.csv", "frame.csv.gz"):
                path = root / name
                save_frame(path, pd.DataFrame({"x": [1]}))
                before = path.read_bytes()
                with self.assertRaises(FileExistsError):
                    save_frame(path, pd.DataFrame({"x": [2]}))
                self.assertEqual(before, path.read_bytes())
            write_json(root / "record.json", {"value": 1})
            with self.assertRaises(FileExistsError):
                write_json(root / "record.json", {"value": 2})
            with self.assertRaisesRegex(ValueError, "Hash mismatch"):
                verify_hashes(root, {"record.json": "incorrect"})

    def test_complete_repeat_never_enters_prediction_scoring_or_panel_reader(self):
        with self.temp() as folder:
            root = Path(folder)
            (root / OUTPUT).mkdir(parents=True)
            (root / OUTPUT / "manifest.json").write_text("{}")
            with patch("retail_forecasting.final_evaluation.verify_existing", return_value={"saved": True}) as verify, \
                 patch("retail_forecasting.final_evaluation.show_summary"), \
                 patch("retail_forecasting.final_evaluation._evaluate", side_effect=AssertionError("reevaluation")), \
                 patch("retail_forecasting.final_evaluation.pd.read_csv", side_effect=AssertionError("data parsed")):
                self.assertEqual(run_final(root), {"saved": True})
                verify.assert_called_once_with(root)

    def test_incomplete_started_run_is_refused(self):
        with self.temp() as folder:
            root = Path(folder)
            (root / OUTPUT).mkdir(parents=True)
            (root / OUTPUT / "started.json").write_text("{}")
            with patch("retail_forecasting.final_evaluation.verify_freeze", return_value={}), \
                 patch("retail_forecasting.final_evaluation._evaluate", side_effect=AssertionError("reevaluation")):
                with self.assertRaisesRegex(ValueError, "Refusing reevaluation"):
                    run_final(root)

    def test_failure_preserves_partial_artifact_and_logs_without_retry(self):
        with self.temp() as folder:
            root = Path(folder)
            (root / OUTPUT).mkdir(parents=True)
            with patch("retail_forecasting.final_evaluation.verify_freeze", return_value={}), \
                 patch("retail_forecasting.final_evaluation.sha256", return_value="synthetic"), \
                 patch("retail_forecasting.final_evaluation._evaluate", side_effect=RuntimeError("synthetic failure")) as evaluate:
                with self.assertRaisesRegex(RuntimeError, "synthetic failure"):
                    run_final(root)
                evaluate.assert_called_once()
            self.assertTrue((root / OUTPUT / "started.json").exists())
            self.assertIn("synthetic failure", (root / OUTPUT / "failure.json").read_text())

    def test_mase_win_tie_loss_explicit_tolerance(self):
        frame = pd.DataFrame({"sku": ["A", "B", "C"] * 2,
            "model": ["weekday_mean"] * 3 + ["seasonal_naive"] * 3,
            "macro_mase": [.5, 1 + 1e-12, 2, 1, 1, 1]})
        self.assertEqual(sku_comparison(frame).outcome.tolist(), ["win", "tie", "loss"])


if __name__ == "__main__":
    unittest.main()
