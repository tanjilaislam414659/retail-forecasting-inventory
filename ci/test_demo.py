"""Dataset-free demo adapter checks using only explicitly synthetic fixtures."""

from dataclasses import replace
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
import numpy as np
import pandas as pd

from ci.fixture_engine import synthetic_engine
from retail_forecasting.demo.app import create_demo_app
from retail_forecasting.service.artifacts import ArtifactError

FIXTURES = Path(__file__).with_name("fixtures") / "demo"


class SyntheticDemoTests(unittest.TestCase):
    def setUp(self):
        self.engine = synthetic_engine()
        self.client = TestClient(create_demo_app(loader=lambda root: self.engine, report_directory=FIXTURES))
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def test_home_assets_three_views_and_accessibility(self):
        page = self.client.get("/")
        self.assertEqual(page.status_code, 200)
        for marker in ('id="view-forecast"', 'id="view-evaluation"', 'id="view-inventory"', 'class="skip-link"', 'aria-live="polite"', 'role="alert"', 'CC BY 4.0'):
            self.assertIn(marker, page.text)
        self.assertIn("script-src 'self'", page.headers["content-security-policy"])
        for name in ("app.js", "style.css"):
            self.assertEqual(self.client.get("/demo/assets/" + name).status_code, 200)
        self.assertEqual(self.client.get("/demo/assets/missing.js").status_code, 404)

    def test_synthetic_forecast_adapter_parity(self):
        response = self.client.post("/forecast", json={"sku": "SYNTHETIC_A", "origin": "2011-06-06"})
        self.assertEqual(response.status_code, 200)
        expected = self.engine.predict("SYNTHETIC_A", self.engine.origins[0]).model_dump(mode="json")
        got = response.json()
        self.assertEqual(len(got["predictions"]), 28)
        for actual, wanted in zip(got["predictions"], expected["predictions"]):
            self.assertEqual(actual["target_date"], wanted["target_date"])
            for key in ("interval_80", "interval_95"):
                np.testing.assert_allclose(list(actual[key].values()), list(wanted[key].values()), rtol=1e-12, atol=1e-9)
            np.testing.assert_allclose(actual["predicted_sales"], wanted["predicted_sales"], rtol=1e-12, atol=1e-9)

    def test_future_sales_cannot_change_adapter_predictions(self):
        histories = {sku: series.copy() for sku, series in self.engine.histories.items()}
        for series in histories.values():
            series.loc[series.index >= pd.Timestamp("2011-06-06")] = 999999
        changed = replace(self.engine, histories=histories)
        with TestClient(create_demo_app(loader=lambda root: changed, report_directory=FIXTURES)) as client:
            request = {"sku": "SYNTHETIC_A", "origin": "2011-06-06"}
            self.assertEqual(self.client.post("/forecast", json=request).json(), client.post("/forecast", json=request).json())

    def test_invalid_requests_remain_rejected(self):
        base = {"sku": "SYNTHETIC_A", "origin": "2011-06-06"}
        for change in ({"sku": "unknown"}, {"origin": "2011-02-30"}, {"horizon_days": 7}, {"extra": True}):
            self.assertEqual(self.client.post("/forecast", json={**base, **change}).status_code, 422)

    def test_reports_are_explicit_synthetic_and_cached(self):
        with patch("pathlib.Path.read_bytes", side_effect=AssertionError("report reloaded")), patch("pandas.read_csv", side_effect=AssertionError("dataset parsed")):
            data = self.client.get("/demo/api/evaluation").json()
            for name in ("validation", "final_test"):
                self.assertEqual(data[name]["status"], "available")
                self.assertTrue(data[name]["data"]["synthetic"])
            self.assertTrue(self.client.get("/demo/api/inventory").json()["data"]["synthetic"])

    def test_missing_corrupt_reports_are_isolated(self):
        for mode in ("missing", "corrupt"):
            with tempfile.TemporaryDirectory() as directory:
                folder = Path(directory) / "reports"
                shutil.copytree(FIXTURES, folder)
                path = folder / "validation.json"
                if mode == "missing":
                    path.unlink()
                else:
                    path.write_bytes(b"SYNTHETIC CORRUPT COPY")
                with TestClient(create_demo_app(loader=lambda root: self.engine, report_directory=folder)) as client:
                    data = client.get("/demo/api/evaluation").json()
                    self.assertEqual(data["validation"]["status"], "unavailable")
                    self.assertEqual(data["final_test"]["status"], "available")
                    self.assertEqual(client.get("/demo/api/inventory").json()["status"], "available")

    def test_missing_forecast_artifacts_do_not_disable_saved_reports(self):
        def fail(root):
            raise ArtifactError("missing_artifact", "SYNTHETIC CHECK")
        with TestClient(create_demo_app(loader=fail, report_directory=FIXTURES)) as client:
            self.assertEqual(client.get("/").status_code, 200)
            self.assertEqual(client.get("/ready").status_code, 503)
            self.assertEqual(client.get("/demo/api/evaluation").json()["final_test"]["status"], "available")

    def test_missing_manifest_has_no_silent_reporting_substitute(self):
        with tempfile.TemporaryDirectory() as directory:
            with TestClient(create_demo_app(loader=lambda root: self.engine, report_directory=Path(directory))) as client:
                result = client.get("/demo/api/evaluation").json()
                self.assertEqual(result["validation"]["status"], "unavailable")
                self.assertEqual(result["final_test"]["status"], "unavailable")


if __name__ == "__main__":
    unittest.main()
