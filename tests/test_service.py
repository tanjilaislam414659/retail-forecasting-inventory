"""Local API, artifact, inference and representative parity regression tests."""

from dataclasses import replace
from datetime import date, timedelta
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import Mock, patch
from uuid import UUID

from fastapi.testclient import TestClient
import numpy as np
import pandas as pd

from retail_forecasting.service.app import create_app
from retail_forecasting.service.artifacts import ArtifactError, load_engine
from retail_forecasting.service.inference import infer_one

ROOT = Path(__file__).resolve().parents[1]
RTOL, ATOL = 1e-12, 1e-9


class ServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = load_engine(ROOT)
        cls.client = TestClient(create_app(ROOT, loader=lambda root: cls.engine))
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def test_liveness_readiness_metadata_and_openapi(self):
        self.assertEqual(self.client.get("/health").json()["status"], "alive")
        self.assertEqual(self.client.get("/ready").json()["status"], "ready")
        metadata = self.client.get("/metadata").json()
        self.assertEqual(len(metadata["supported_skus"]), 100)
        self.assertEqual(len(metadata["supported_origins"]), 20)
        self.assertEqual(metadata["horizon_days"], 28)
        self.assertTrue(metadata["historical_demo"] and metadata["intervals_experimental"])
        schema = self.client.get("/openapi.json").json()
        self.assertEqual(schema["info"]["version"], "0.1.0")
        self.assertFalse(schema["components"]["schemas"]["ForecastRequest"]["additionalProperties"])
        for path in ("/health", "/ready", "/metadata", "/forecast"):
            self.assertIn(path, schema["paths"])

    def test_response_alignment_bounds_labels_and_no_actuals_or_customers(self):
        response = self.client.post("/forecast", json={"sku": "21212", "origin": "2011-11-07", "horizon_days": 28})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["history_cutoff"], "2011-11-06")
        self.assertTrue(body["historical_demo"] and body["intervals_experimental"])
        self.assertEqual(len(body["predictions"]), 28)
        UUID(response.headers["x-request-id"])
        for day, row in enumerate(body["predictions"], 1):
            self.assertEqual(row["horizon_day"], day)
            self.assertEqual(date.fromisoformat(row["target_date"]), date(2011, 11, 7) + timedelta(days=day - 1))
            lo80, hi80 = row["interval_80"].values()
            lo95, hi95 = row["interval_95"].values()
            self.assertTrue(0 <= lo95 <= lo80 <= hi80 <= hi95)
            self.assertTrue(np.isfinite([lo95, lo80, hi80, hi95, row["predicted_sales"]]).all())
        self.assertNotIn("actual", response.text.lower())
        self.assertNotIn("customer", response.text.lower())
        self.assertNotIn("sales_units", response.text)

    def test_invalid_requests_are_422_with_clear_errors(self):
        valid = {"sku": "21212", "origin": "2011-11-07"}
        cases = [
            {"sku": "unknown"}, {"sku": 21212}, {"sku": ""},
            {"origin": "2011-08-15"}, {"origin": "2026-11-02"},
            {"origin": "2011-02-30"}, {"origin": "07/11/2011"},
            {"origin": "2011-11-07T00:00:00"}, {"origin": 1320624000}, {"origin": None},
            {"horizon_days": 7}, {"horizon_days": "28"}, {"horizon_days": 28.0}, {"horizon_days": True},
            {"extra": "forbidden"},
        ]
        for delta in cases:
            with self.subTest(delta=delta):
                response = self.client.post("/forecast", json={**valid, **delta})
                self.assertEqual(response.status_code, 422, response.text)
                self.assertIn("detail", response.json())
        for payload in ({}, {"sku": "21212"}, {"origin": "2011-11-07"}, []):
            self.assertEqual(self.client.post("/forecast", json=payload).status_code, 422)
        self.assertEqual(self.client.post("/forecast", content="{bad", headers={"content-type": "application/json"}).status_code, 422)

    def test_startup_loads_once_requests_do_no_io_or_fitting(self):
        loader = Mock(return_value=self.engine)
        with TestClient(create_app(ROOT, loader=loader)) as client:
            with patch("pathlib.Path.read_bytes", side_effect=AssertionError("disk read on request")), \
                 patch("pandas.read_csv", side_effect=AssertionError("CSV parse on request")), \
                 patch("retail_forecasting.uncertainty.fit_quantiles", side_effect=AssertionError("recalibration")), \
                 patch("retail_forecasting.final_evaluation.run_final", side_effect=AssertionError("evaluation")):
                for _ in range(2):
                    self.assertEqual(client.post("/forecast", json={"sku": "21212", "origin": "2011-06-06"}).status_code, 200)
            loader.assert_called_once_with(ROOT.resolve())

    def test_no_evaluation_forecast_file_is_read_at_startup(self):
        original = Path.read_bytes
        def guarded(path):
            self.assertFalse(path.name in {"point_forecasts.csv.gz", "interval_forecasts.csv.gz", "validation_forecasts.csv.gz", "validation_intervals.csv.gz"})
            return original(path)
        with patch.object(Path, "read_bytes", guarded):
            loaded = load_engine(ROOT)
        self.assertEqual(len(loaded.skus), 100)

    def test_structured_logging_has_request_id_outcome_version_timing_no_credentials(self):
        with self.assertLogs("retail_forecasting.service", level="INFO") as logs:
            response = self.client.post("/forecast?token=do-not-log-query", headers={"Authorization": "Bearer do-not-log-secret"},
                json={"sku": "21212", "origin": "2011-11-07", "credential": "do-not-log-body"})
        events = [json.loads(record.getMessage()) for record in logs.records]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["request_id"], response.headers["x-request-id"])
        self.assertEqual(events[0]["outcome"], "rejected")
        self.assertEqual(events[0]["service_version"], "0.1.0")
        self.assertGreaterEqual(events[0]["elapsed_ms"], 0)
        self.assertNotIn("do-not-log", str(events))
        self.assertNotIn("do-not-log-body", response.text)

    def test_api_future_history_mutations_leave_issued_values_unchanged(self):
        for origin in (date(2011, 6, 6), date(2011, 9, 5)):
            with self.subTest(origin=origin):
                histories = dict(self.engine.histories)
                series = histories["21212"].copy()
                series.loc[series.index >= pd.Timestamp(origin)] = 999999
                histories["21212"] = series
                changed = replace(self.engine, histories=histories)
                with TestClient(create_app(ROOT, loader=lambda root: changed)) as client:
                    payload = {"sku": "21212", "origin": origin.isoformat()}
                    self.assertEqual(self.client.post("/forecast", json=payload).json(), client.post("/forecast", json=payload).json())

    def test_engine_passes_only_pre_origin_values_into_inference(self):
        with patch("retail_forecasting.service.artifacts.infer_one", wraps=infer_one) as inference:
            self.engine.predict("21212", date(2011, 6, 6))
        supplied_history = inference.call_args.args[0]
        self.assertTrue((supplied_history.index < pd.Timestamp("2011-06-06")).all())

    def test_pure_inference_future_mutation_all_28_days_and_frozen_quantiles(self):
        origin = pd.Timestamp("2011-09-05")
        series = pd.Series(np.arange(84, dtype=float), index=pd.date_range(origin - pd.Timedelta(days=56), periods=84))
        original_quantiles = self.engine.quantiles.copy(deep=True)
        before = infer_one(series, self.engine.quantiles, "21212", origin.date())
        series.loc[series.index >= origin] = 1e12
        after = infer_one(series, self.engine.quantiles, "21212", origin.date())
        self.assertEqual(before, after)
        pd.testing.assert_frame_equal(original_quantiles, self.engine.quantiles)
        expected = np.arange(56).reshape(8, 7).mean(axis=0)
        np.testing.assert_allclose([r["predicted_sales"] for r in before], np.tile(expected, 4), rtol=RTOL, atol=ATOL)
        with self.assertRaisesRegex(ValueError, "28-day"):
            infer_one(series, self.engine.quantiles, "21212", origin.date(), 7)
        with self.assertRaisesRegex(ValueError, "consecutive"):
            infer_one(series.drop(origin - pd.Timedelta(days=1)), self.engine.quantiles, "21212", origin.date())

    def test_http_parity_with_saved_validation_and_final_outputs(self):
        # Only test code reads reference predictions; actual-sales columns are omitted.
        for origin, filename in (("2011-06-06", "data/uncertainty/validation_intervals.csv.gz"),
                                 ("2011-11-07", "data/final_evaluation/interval_forecasts.csv.gz")):
            reference = pd.read_csv(ROOT / filename, dtype={"sku": str}, float_precision="round_trip",
                usecols=["sku", "origin", "horizon_day", "level", "point_prediction", "lower", "upper"])
            for sku in ("21212", "21166", "21533"):
                with self.subTest(origin=origin, sku=sku):
                    body = self.client.post("/forecast", json={"sku": sku, "origin": origin}).json()
                    rows = reference.loc[reference.sku.eq(sku) & reference.origin.eq(origin)]
                    for level in (80, 95):
                        expected = rows.loc[rows.level.eq(level)].sort_values("horizon_day")
                        np.testing.assert_allclose([p["predicted_sales"] for p in body["predictions"]], expected.point_prediction, rtol=RTOL, atol=ATOL)
                        for endpoint in ("lower", "upper"):
                            np.testing.assert_allclose([p[f"interval_{level}"][endpoint] for p in body["predictions"]], expected[endpoint], rtol=RTOL, atol=ATOL)


class ArtifactTests(unittest.TestCase):
    def fixture(self):
        cache = ROOT / ".cache/api-tests"
        cache.mkdir(parents=True, exist_ok=True)
        temp = tempfile.TemporaryDirectory(dir=cache)
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        contract = json.loads((ROOT / "service/artifact-contract.json").read_text())
        (root / "service").mkdir()
        shutil.copyfile(ROOT / "service/artifact-contract.json", root / "service/artifact-contract.json")
        for entry in contract["artifacts"].values():
            target = root / entry["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / entry["path"], target)
        return root, contract

    def check_unready(self, root, expected_code):
        with TestClient(create_app(root)) as client:
            self.assertEqual(client.get("/health").status_code, 200)
            ready = client.get("/ready")
            self.assertEqual(ready.status_code, 503)
            self.assertEqual(ready.json()["error_code"], expected_code)
            self.assertEqual(client.get("/metadata").status_code, 503)
            self.assertEqual(client.post("/forecast", json={"sku": "21212", "origin": "2011-11-07"}).status_code, 503)

    def test_missing_history_and_calibration_are_not_ready(self):
        for key in ("history", "quantiles"):
            with self.subTest(key=key):
                root, contract = self.fixture()
                (root / contract["artifacts"][key]["path"]).unlink()
                self.check_unready(root, "missing_artifact")

    def test_corrupt_history_calibration_or_frozen_code_are_not_ready(self):
        for key in ("history", "quantiles", "point_code"):
            with self.subTest(key=key):
                root, contract = self.fixture()
                with (root / contract["artifacts"][key]["path"]).open("ab") as stream:
                    stream.write(b"corrupt")
                self.check_unready(root, "checksum_mismatch")

    def test_missing_or_invalid_contract_is_not_ready(self):
        root, _ = self.fixture()
        path = root / "service/artifact-contract.json"
        path.write_text("{broken")
        self.check_unready(root, "invalid_artifact")
        path.unlink()
        self.check_unready(root, "missing_artifact")

    def test_engine_missing_calibration_does_not_substitute(self):
        from retail_forecasting.service.artifacts import load_engine
        engine = load_engine(ROOT)
        incomplete = engine.quantiles.loc[~(engine.quantiles.sku.eq("21212") & engine.quantiles.horizon_week.eq(1))]
        with self.assertRaisesRegex(ValueError, "Every SKU"):
            infer_one(engine.histories["21212"], incomplete, "21212", date(2011, 11, 7))


if __name__ == "__main__":
    unittest.main()
