"""Build an injected synthetic test engine, never a production artifact loader."""

from datetime import date
import hashlib
import json
from pathlib import Path

import pandas as pd

from retail_forecasting.service.artifacts import InferenceEngine

FIXTURES = Path(__file__).with_name("fixtures")


def synthetic_engine():
    record = json.loads((FIXTURES / "manifest.json").read_text())
    assert record["synthetic"] is True
    for name, digest in record["sha256"].items():
        assert hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest() == digest, name
    frame = pd.read_csv(FIXTURES / "history.csv", parse_dates=["date"])
    quantiles = pd.read_csv(FIXTURES / "quantiles.csv")
    histories = {sku: rows.set_index("date").sales_units for sku, rows in frame.groupby("sku")}
    return InferenceEngine(histories, quantiles, tuple(sorted(histories)),
        (date(2011, 6, 6), date(2011, 6, 13)), "SYNTHETIC-TEST-ONLY-NOT-A-RELEASE", "SYNTHETIC-HANDCRAFTED-NOT-CALIBRATED")
