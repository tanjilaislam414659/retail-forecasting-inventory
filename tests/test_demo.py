"""Interface adapter/report regressions; no model evaluation or inventory replay."""

import csv
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
import numpy as np

from retail_forecasting.demo.app import create_demo_app
from retail_forecasting.demo.reports import load_reports
from retail_forecasting.service.app import create_app
from retail_forecasting.service.artifacts import ArtifactError, load_engine

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "src/retail_forecasting/demo/reports"


class DemoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = load_engine(ROOT)
        cls.client = TestClient(create_demo_app(ROOT, loader=lambda root: cls.engine))
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def temp(self):
        cache = ROOT / ".cache/demo-tests"
        cache.mkdir(parents=True, exist_ok=True)
        directory = tempfile.TemporaryDirectory(dir=cache)
        self.addCleanup(directory.cleanup)
        return Path(directory.name)

    def test_three_views_static_assets_csp_and_accessible_elements(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        for marker in ('id="view-forecast"', 'id="view-evaluation"', 'id="view-inventory"', 'class="skip-link"', 'label for="sku"', 'role="alert"', 'aria-live="polite"', 'CC BY 4.0', 'simultaneous'):
            self.assertIn(marker, response.text)
        self.assertIn("script-src 'self'", response.headers["content-security-policy"])
        self.assertNotIn("<script src=\"http", response.text)
        for filename, kind in (("app.js", "javascript"), ("style.css", "text/css")):
            asset = self.client.get("/demo/assets/" + filename)
            self.assertEqual(asset.status_code, 200)
            self.assertIn(kind, asset.headers["content-type"])
        self.assertEqual(self.client.get("/demo/assets/missing.js").status_code, 404)

    def test_original_api_parity_through_demo_adapter(self):
        with TestClient(create_app(ROOT, loader=lambda root: self.engine)) as original:
            for sku in ("21212", "21166", "21533"):
                for origin in ("2011-06-06", "2011-11-07"):
                    with self.subTest(sku=sku, origin=origin):
                        payload = {"sku": sku, "origin": origin, "horizon_days": 28}
                        old = original.post("/forecast", json=payload).json()
                        new = self.client.post("/forecast", json=payload).json()
                        self.assertEqual(old, new)
                        for before, after in zip(old["predictions"], new["predictions"]):
                            np.testing.assert_allclose(before["predicted_sales"], after["predicted_sales"], rtol=1e-12, atol=1e-9)
        self.assertEqual(self.client.post("/forecast", json={"sku": "unknown", "origin": "2011-11-07"}).status_code, 422)

    def test_periods_and_validation_only_candidates_remain_distinct(self):
        data = self.client.get("/demo/api/evaluation").json()
        validation, final = data["validation"]["data"], data["final_test"]["data"]
        self.assertEqual(validation["evidence"], "development")
        self.assertEqual(final["evidence"], "consumed final test")
        self.assertEqual({row["model"] for row in final["models"]}, {"weekday_mean", "seasonal_naive"})
        self.assertEqual({row["model"] for row in validation["models"]}, {"weekday_mean", "seasonal_naive", "recent_mean", "ridge", "hist_poisson"})
        self.assertEqual(validation["last_target"], "2011-09-04")
        self.assertEqual(final["first_target"], "2011-09-05")

    def test_packaged_metrics_match_saved_sources_with_explicit_tolerance(self):
        data = load_reports(REPORTS)
        for key, filename in (("validation", "data/baselines/metrics_by_model.csv"), ("final-test", "data/final_evaluation/point_metrics_by_model.csv")):
            with (ROOT / filename).open(newline="") as stream:
                expected = {row["model"]: row for row in csv.DictReader(stream)}
            for row in data[key]["data"]["models"]:
                if row["model"] not in expected:
                    continue  # candidates have their own saved source, checked below
                for metric in ("macro_mase", "mae", "wape_pct", "mean_bias_units", "bias_pct"):
                    np.testing.assert_allclose(row[metric], float(expected[row["model"]][metric]), rtol=1e-12, atol=1e-9)
        with (ROOT / "data/boosting/metrics_by_model.csv").open(newline="") as stream:
            candidates = {row["model"]: row for row in csv.DictReader(stream)}
        for row in data["validation"]["data"]["models"]:
            if row["model"] in {"ridge", "hist_poisson"}:
                np.testing.assert_allclose(row["macro_mase"], float(candidates[row["model"]]["macro_mase"]), rtol=1e-12, atol=1e-9)

    def test_inventory_has_exact_saved_scenarios_not_optimization(self):
        payload = self.client.get("/demo/api/inventory").json()
        self.assertEqual(payload["status"], "available")
        data = payload["data"]
        self.assertEqual(len(data["scenarios"]), 18)
        self.assertEqual(data["lead_times"], [1, 3, 7])
        self.assertEqual(data["shortage_penalties"], [1, 5])
        with (ROOT / "data/inventory_simulation/v0.1.0/scenario_metrics.csv").open(newline="") as stream:
            expected = {(float(row["lead_time_days"]), float(row["shortage_cost_per_unit"]), row["policy"]): row for row in csv.DictReader(stream)}
        for row in data["scenarios"]:
            source = expected[row["lead_time_days"], row["shortage_cost_per_unit"], row["policy"]]
            for metric in ("fulfilled_unit_rate_pct", "unfulfilled_units", "average_total_closing_inventory", "total_simulated_cost"):
                np.testing.assert_allclose(row[metric], float(source[metric]), rtol=1e-12, atol=1e-9)

    def test_reports_and_inference_use_cached_inputs_during_requests(self):
        with patch("pathlib.Path.read_bytes", side_effect=AssertionError("report data reloaded")), \
             patch("pandas.read_csv", side_effect=AssertionError("data parsed on request")), \
             patch("retail_forecasting.inventory.experiment.execute", side_effect=AssertionError("simulation run")), \
             patch("retail_forecasting.final_evaluation.run_final", side_effect=AssertionError("evaluation run")):
            self.assertEqual(self.client.get("/demo/api/evaluation").status_code, 200)
            self.assertEqual(self.client.get("/demo/api/inventory").status_code, 200)
            self.assertEqual(self.client.post("/forecast", json={"sku": "21212", "origin": "2011-11-07"}).status_code, 200)

    def test_missing_or_corrupt_report_is_isolated_without_substitution(self):
        for kind in ("missing", "corrupt"):
            folder = self.temp() / "reports"
            shutil.copytree(REPORTS, folder)
            if kind == "missing":
                (folder / "validation.json").unlink()
            else:
                (folder / "validation.json").write_bytes(b"CORRUPT")
            with TestClient(create_demo_app(ROOT, loader=lambda root: self.engine, report_directory=folder)) as client:
                data = client.get("/demo/api/evaluation").json()
                self.assertEqual(data["validation"]["status"], "unavailable")
                self.assertEqual(data["final_test"]["status"], "available")
                self.assertEqual(client.get("/demo/api/inventory").json()["status"], "available")
                self.assertEqual(client.get("/").status_code, 200)
                self.assertEqual(client.post("/forecast", json={"sku": "21212", "origin": "2011-11-07"}).status_code, 200)

    def test_missing_reporting_manifest_reports_unavailable(self):
        folder = self.temp()
        result = load_reports(folder)
        self.assertTrue(all(section["status"] == "unavailable" for section in result.values()))

    def test_malformed_reporting_manifest_reports_unavailable(self):
        folder = self.temp()
        for malformed in (b"NOT JSON", b"null", b"[]", b'{"report_version":"0.1.0","payloads":[]}'):
            (folder / "manifest.json").write_bytes(malformed)
            result = load_reports(folder)
            self.assertTrue(all(section["status"] == "unavailable" for section in result.values()))

    def test_missing_forecast_artifacts_keep_static_ui_and_saved_reports_available(self):
        def failed(root):
            raise ArtifactError("missing_artifact", "synthetic-missing-runtime")
        with TestClient(create_demo_app(ROOT, loader=failed)) as client:
            self.assertEqual(client.get("/").status_code, 200)
            self.assertEqual(client.get("/ready").status_code, 503)
            self.assertEqual(client.get("/metadata").status_code, 503)
            self.assertEqual(client.get("/demo/api/inventory").json()["status"], "available")

    def test_reporting_payload_source_and_member_hashes_match(self):
        manifest = json.loads((REPORTS / "manifest.json").read_text())
        for name, digest in manifest["source_sha256"].items():
            self.assertEqual(hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), digest)
        self.assertLess(sum(row["bytes"] for row in manifest["payloads"].values()), 30000)
        for name, entry in manifest["payloads"].items():
            self.assertEqual(hashlib.sha256((REPORTS / name).read_bytes()).hexdigest(), entry["sha256"])


if __name__ == "__main__":
    unittest.main()
