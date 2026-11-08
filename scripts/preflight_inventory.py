"""Exercise the complete ledger/report/validator using generated synthetic data only."""

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import time
from unittest.mock import patch

import numpy as np
import pandas as pd

from retail_forecasting.inventory.experiment import execute, frame_write, json_write
from validate_inventory import main as validate


def main():
    project = Path(__file__).resolve().parents[1]
    config = json.loads((project / "configs/inventory-simulation.json").read_text())
    cache = project / ".cache"
    cache.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="inventory-synthetic-", dir=cache) as directory:
        root = Path(directory)
        output = root / "data/inventory_simulation/v0.1.0"
        for name in ("data/baselines", "data/processed", "docs", str(output.relative_to(root))):
            (root / name).mkdir(parents=True, exist_ok=True)
        skus = [f"SYNTHETIC_{index:03d}" for index in range(100)]
        dates = pd.date_range("2009-12-07", "2011-09-04")
        histories, forecasts = [], []
        for index, sku in enumerate(skus):
            excluded = 49 if index < 9 else 43 if index == 9 else 0
            histories.append(pd.DataFrame({"sku": sku, "date": dates[excluded:],
                "sales_units": ((np.arange(len(dates)) + index) % 13)[excluded:]}))
            for origin in config["available_forecast_origins"]:
                forecasts.append(pd.DataFrame({"sku": sku, "origin": origin, "target_date": pd.date_range(origin, periods=28),
                    "horizon_day": np.arange(1, 29), "model": "weekday_mean", "predicted_sales": float(index % 10) + 1.125}))
        frame_write(root / config["sales_file"], pd.concat(histories, ignore_index=True))
        frame_write(root / config["forecast_file"], pd.concat(forecasts, ignore_index=True))
        frame_write(root / "data/processed/sku_selection.csv", pd.DataFrame({"sku": skus}))
        spec = {"configuration": config, "protected_artifact_sha256": {}, "source_and_specification_sha256": {},
            "input_sha256": {}, "specified_before_execution_at_utc": "2000-01-01T00:00:00+00:00", "synthetic_fixture": True}
        json_write(output / "specification-record.json", spec)
        json_write(output / "started.json", {"executed_at_utc": "2001-01-01T00:00:00+00:00"})
        with redirect_stdout(StringIO()):
            # The harness omits real-artifact guards only for this isolated synthetic
            # root; no production guard, config, input or source file is changed.
            result = execute(root, output, spec)
            validate(root)
        assert result["ledger_rows"] == 81900 and result["aggregate_scenario_rows"] == 18
        assert (root / "docs/milestone-10.md").is_file()
        assert not (output / "failure.json").exists()
    print("PASS: fully synthetic 100-SKU end-to-end inventory preflight, 81,900 chronological rows, report/plot/manifest and independent saved-output validation. No real sales or final outcomes used.")


if __name__ == "__main__":
    main()
