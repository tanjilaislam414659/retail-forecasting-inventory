"""Numerical regression over supported cases, never a new performance evaluation."""

from datetime import datetime, timezone
import json
from pathlib import Path
import time

import numpy as np
import pandas as pd

from retail_forecasting.final_evaluation import verify_existing
from retail_forecasting.service import __version__
from retail_forecasting.service.artifacts import load_engine

RTOL, ATOL = 1e-12, 1e-9


def main():
    root = Path(__file__).resolve().parents[1]
    verify_existing(root)  # hash verification only; no evaluation
    started = time.perf_counter()
    engine = load_engine(root)
    load_seconds = time.perf_counter() - started
    results = []
    for origin in engine.origins:
        for sku in engine.skus:
            body = engine.predict(sku, origin)
            for row in body.predictions:
                for level in (80, 95):
                    bounds = getattr(row, f"interval_{level}")
                    results.append({"sku": sku, "origin": origin.isoformat(), "target_date": row.target_date.isoformat(),
                        "horizon_day": row.horizon_day, "level": level,
                        "predicted_sales": row.predicted_sales, "lower": bounds.lower, "upper": bounds.upper})
    generated = pd.DataFrame(results)
    inference_seconds = time.perf_counter() - started - load_seconds
    keys = ["sku", "origin", "target_date", "horizon_day"]
    expected_intervals, expected_points = [], []
    # Only this verification script reads saved forecasts; actual columns are never read.
    for filename in ("data/uncertainty/validation_intervals.csv.gz", "data/final_evaluation/interval_forecasts.csv.gz"):
        expected_intervals.append(pd.read_csv(root / filename, dtype={"sku": str}, float_precision="round_trip",
            usecols=keys + ["level", "lower", "upper"]))
    for filename in ("data/baselines/validation_forecasts.csv.gz", "data/final_evaluation/point_forecasts.csv.gz"):
        saved = pd.read_csv(root / filename, dtype={"sku": str}, float_precision="round_trip",
            usecols=keys + ["model", "predicted_sales"])
        expected_points.append(saved.loc[saved.model.eq("weekday_mean")].drop(columns="model"))
    matched = generated.merge(pd.concat(expected_intervals), on=keys + ["level"], validate="one_to_one", suffixes=("", "_saved"))
    assert len(matched) == len(generated) == 112000
    points = generated.loc[generated.level.eq(80), keys + ["predicted_sales"]]
    matched_points = points.merge(pd.concat(expected_points), on=keys, validate="one_to_one", suffixes=("", "_saved"))
    assert len(matched_points) == 56000
    maxima = {}
    for column, data in (("predicted_sales", matched_points), ("lower", matched), ("upper", matched)):
        np.testing.assert_allclose(data[column], data[column + "_saved"], rtol=RTOL, atol=ATOL)
        maxima[column] = float(np.max(np.abs(data[column] - data[column + "_saved"])))
    verify_existing(root)
    output = root / "reports/generated/service" / ("parity-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    output.mkdir(parents=True, exist_ok=False)
    report = {"kind": "Numerical regression verification, not performance evaluation", "service_version": __version__,
        "sku_origin_cases": 2000, "dated_point_predictions": 56000, "level_specific_intervals": 112000,
        "relative_tolerance": RTOL, "absolute_tolerance": ATOL, "max_absolute_differences": maxima,
        "load_seconds": load_seconds, "all_case_inference_seconds": inference_seconds,
        "frozen_evaluation_unchanged": True, "status": "PASS"}
    with (output / "parity.json").open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    print(json.dumps(report, indent=2), flush=True)
    print(f"Saved {output / 'parity.json'}", flush=True)


if __name__ == "__main__":
    main()
