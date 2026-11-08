"""In-process HTTP checks with a visibly synthetic two-SKU injected engine."""

from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
import pandas as pd

from ci.fixture_engine import synthetic_engine
from retail_forecasting.service.app import create_app
from retail_forecasting.service.artifacts import ArtifactError, load_engine


class SyntheticApiTests(unittest.TestCase):
    def setUp(self):
        self.engine = synthetic_engine()
        self.client = TestClient(create_app(loader=lambda root: self.engine))
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def test_health_ready_metadata_and_openapi(self):
        for path in ("/health", "/ready", "/metadata", "/openapi.json"):
            self.assertEqual(self.client.get(path).status_code, 200)
        metadata = self.client.get("/metadata").json()
        self.assertEqual(metadata["supported_skus"], ["SYNTHETIC_A", "SYNTHETIC_B"])
        self.assertIn("SYNTHETIC", metadata["forecast_release_id"])

    def test_valid_request_and_no_actuals_or_customers(self):
        response = self.client.post("/forecast", json={"sku": "SYNTHETIC_A", "origin": "2011-06-06", "horizon_days": 28})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["predictions"]), 28)
        self.assertTrue(response.json()["historical_demo"] and response.json()["intervals_experimental"])
        self.assertNotIn("actual", response.text.lower())
        self.assertNotIn("customer", response.text.lower())
        self.assertIn("x-request-id", response.headers)

    def test_invalid_requests_fail_explicitly(self):
        base = {"sku": "SYNTHETIC_A", "origin": "2011-06-06"}
        for delta in ({"sku": "unknown"}, {"origin": "2011-06-07"}, {"origin": "2011-02-30"},
                      {"origin": "2011-06-06T00:00:00"}, {"horizon_days": 7}, {"horizon_days": True},
                      {"horizon_days": "28"}, {"unexpected": 1}):
            with self.subTest(delta=delta):
                self.assertEqual(self.client.post("/forecast", json={**base, **delta}).status_code, 422)

    def test_health_survives_missing_and_corrupt_artifacts(self):
        for code in ("missing_artifact", "checksum_mismatch"):
            def failed_loader(root):
                raise ArtifactError(code, "SYNTHETIC-fixture")
            with TestClient(create_app(loader=failed_loader)) as client:
                self.assertEqual(client.get("/health").status_code, 200)
                self.assertEqual(client.get("/ready").status_code, 503)
                self.assertEqual(client.get("/ready").json()["error_code"], code)
                self.assertEqual(client.post("/forecast", json={"sku": "SYNTHETIC_A", "origin": "2011-06-06"}).status_code, 503)

    def test_real_loader_rejects_missing_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ArtifactError) as caught:
                load_engine(Path(directory))
            self.assertEqual(caught.exception.code, "missing_artifact")

    def test_load_once_requests_have_no_file_reads(self):
        with patch("pathlib.Path.read_bytes", side_effect=AssertionError("request disk access")), \
             patch("pandas.read_csv", side_effect=AssertionError("request CSV parse")):
            self.assertEqual(self.client.post("/forecast", json={"sku": "SYNTHETIC_A", "origin": "2011-06-06"}).status_code, 200)

    def test_http_future_sales_mutation_preserves_predictions(self):
        history = {sku: values.copy() for sku, values in self.engine.histories.items()}
        history["SYNTHETIC_A"].loc[history["SYNTHETIC_A"].index >= pd.Timestamp("2011-06-06")] = 1e9
        changed = replace(self.engine, histories=history)
        with TestClient(create_app(loader=lambda root: changed)) as other:
            payload = {"sku": "SYNTHETIC_A", "origin": "2011-06-06"}
            self.assertEqual(self.client.post("/forecast", json=payload).json(), other.post("/forecast", json=payload).json())

    def test_logs_do_not_contain_submitted_credentials(self):
        with self.assertLogs("retail_forecasting.service", level="INFO") as logs:
            self.client.post("/forecast", headers={"authorization": "SECRET-header"}, json={
                "sku": "SYNTHETIC_A", "origin": "2011-06-06", "secret": "SECRET-body"})
        event = json.loads(logs.records[-1].getMessage())
        self.assertEqual(event["outcome"], "rejected")
        self.assertIn("request_id", event)
        self.assertNotIn("SECRET", str(event))
