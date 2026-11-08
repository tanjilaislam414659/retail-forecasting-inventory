"""Exercise the entire final runner on labelled synthetic data before unblinding."""

import contextlib
from io import StringIO
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

import numpy as np
import pandas as pd

from retail_forecasting.final_evaluation import OUTPUT, read_json, run_final, save_frame, write_json
from retail_forecasting.acquisition import sha256
from validate_final_evaluation import main as validate


def main():
    project = Path(__file__).resolve().parents[1]
    base = project / ".cache/final-synthetic-preflight"
    base.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=base) as folder:
        root = Path(folder)
        for name in ("configs", "docs", "data/processed", "data/baselines", "data/uncertainty", str(OUTPUT)):
            (root / name).mkdir(parents=True, exist_ok=True)
        config = read_json(project / "configs/final-evaluation.json")
        write_json(root / "configs/final-evaluation.json", config)
        # Empty synthetic hash map is only a fixture; production freeze hashes all inputs.
        write_json(root / OUTPUT / "freeze.json", {"configuration": config, "sha256": {}, "versions": {},
            "frozen_at_utc": "2000-01-01T00:00:00+00:00", "synthetic": True})
        dates = pd.date_range("2009-12-07", "2011-12-04")
        skus = [f"S{i:03d}" for i in range(99)] + ["21166"]
        frames, scale_rows = [], []
        for index, sku in enumerate(skus):
            excluded = 49 if index < 9 else (43 if index == 9 else 0)
            values = ((np.arange(len(dates)) + index) % 23).astype(int)
            values[dates.dayofweek == 5] = 0
            values[:excluded] = 0
            frames.append(pd.DataFrame({"sku": sku, "date": dates, "sales_units": values,
                "sales_lines": (values > 0).astype(int),
                "split": np.where(dates < "2011-06-06", "train", np.where(dates < "2011-09-05", "validation", "test"))}))
            scale_rows.append({"sku": sku, "modelling_start": dates[excluded], "excluded_leading_days": excluded,
                "mase_scale": 10., "training_end": "2011-06-05", "training_positive_units": 10000 - index})
        panel, scales = pd.concat(frames, ignore_index=True), pd.DataFrame(scale_rows)
        save_frame(root / "data/processed/sales_daily.csv.gz", panel)
        save_frame(root / "data/processed/sku_selection.csv", pd.DataFrame({"sku": skus}))
        save_frame(root / "data/baselines/history_and_scales.csv", scales)
        retained = panel.loc[panel.date.ge(panel.sku.map(scales.set_index("sku").modelling_start)) & panel.date.lt("2011-09-05")]
        save_frame(root / "data/baselines/modelling_history.csv.gz", retained)
        groups = []
        for sku in skus:
            for week in range(1, 5):
                for level, alpha, width in ((80, .2, 10), (95, .05, 20)):
                    groups.append({"sku": sku, "horizon_week": week, "level": level, "alpha": alpha,
                        "lower_residual_quantile": -width, "upper_residual_quantile": width,
                        "calibration_status": "defined"})
        save_frame(root / "data/uncertainty/calibration_quantiles.csv", pd.DataFrame(groups))
        write_json(root / "data/uncertainty/calibration-record.json", {
            "calibration_target_end_exclusive": "2011-06-06",
            "quantiles_sha256": sha256(root / "data/uncertainty/calibration_quantiles.csv")})
        save_frame(root / "data/baselines/metrics_by_model.csv", pd.DataFrame([
            {"model": model, "macro_mase": 1., "mae": 10., "wape_pct": 100., "mean_bias_units": 0., "bias_pct": 0.}
            for model in ("weekday_mean", "seasonal_naive")]))
        save_frame(root / "data/uncertainty/metrics_overall.csv", pd.DataFrame([
            {"level": level, "coverage_pct": 90., "mean_width": 20., "mean_interval_score": 30.,
             "miss_below_count": 0, "miss_above_count": 0, "missing_interval_count": 0, "zero_width_count": 0}
            for level in (80, 95)]))
        with contextlib.redirect_stdout(StringIO()):
            summary = run_final(root)
            validate(root)
            before = {p.relative_to(root): p.read_bytes() for p in (root / OUTPUT).iterdir()}
            with patch("retail_forecasting.final_evaluation._evaluate", side_effect=AssertionError("reevaluated")), \
                 patch("retail_forecasting.final_evaluation.pd.read_csv", side_effect=AssertionError("parsed outcomes")):
                repeated = run_final(root)
        assert summary == repeated
        assert before == {p.relative_to(root): p.read_bytes() for p in (root / OUTPUT).iterdir()}
        assert (root / "docs/final-evaluation-report.md").is_file()
        assert len(summary["plots"]["files"]) == 4
        assert summary["point_instances_per_model"] == 28000 and not summary["implementation_defects"]
        print("PASS: SYNTHETIC 100-SKU end-to-end preflight, plots/report/manifest, and repeat with predictor/scorer/data parser blocked. No real final outcomes read.")


if __name__ == "__main__":
    main()
