"""Copy saved aggregate metrics into small UI payloads, never evaluate or simulate."""

import csv
import hashlib
import json
from pathlib import Path

from retail_forecasting.inventory.experiment import verify_completed


def main():
    root = Path(__file__).resolve().parents[1]
    verify_completed(root, root / "data/inventory_simulation/v0.1.0")
    output = root / "src/retail_forecasting/demo/reports"
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise FileExistsError("Reporting payloads already exist; refusing replacement")
    sources = {}

    def rows(name):
        path = root / name
        sources[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        with path.open(encoding="utf-8", newline="") as stream:
            return list(csv.DictReader(stream))

    point_columns = ["model", "mae", "wape_pct", "macro_mase", "mean_bias_units", "bias_pct", "row_count"]
    interval_columns = ["level", "coverage_pct", "mean_width", "mean_interval_score", "miss_below_count", "miss_above_count"]

    def select(records, columns):
        return [{key: (row[key] if key == "model" else float(row[key])) for key in columns} for row in records]

    base = rows("data/baselines/metrics_by_model.csv")
    candidates = rows("data/boosting/metrics_by_model.csv")
    validation = select(base, point_columns)
    validation += select([row for row in candidates if row["model"] in {"ridge", "hist_poisson"}], point_columns)
    final = select(rows("data/final_evaluation/point_metrics_by_model.csv"), point_columns)
    payloads = {
        "validation.json": {"period": "validation", "evidence": "development", "first_target": "2011-06-06", "last_target": "2011-09-04",
            "models": validation, "intervals": select(rows("data/uncertainty/metrics_overall.csv"), interval_columns),
            "instances_per_model": 28000, "unique_sku_target_pairs": 9100},
        "final-test.json": {"period": "final_test", "evidence": "consumed final test", "first_target": "2011-09-05", "last_target": "2011-12-04",
            "models": final, "intervals": select(rows("data/final_evaluation/interval_metrics_overall.csv"), interval_columns),
            "instances_per_model": 28000, "unique_sku_target_pairs": 9100},
    }
    scenario_rows = rows("data/inventory_simulation/v0.1.0/scenario_metrics.csv")
    scenario_columns = ["lead_time_days", "shortage_cost_per_unit", "policy", "fulfilled_unit_rate_pct", "fulfilled_units", "unfulfilled_units",
        "average_total_closing_inventory", "order_count", "holding_cost", "shortage_cost", "order_setup_cost", "total_simulated_cost", "starting_stock", "ending_stock"]
    scenarios = [{key: (row[key] if key == "policy" else float(row[key])) for key in scenario_columns} for row in scenario_rows]
    payloads["inventory.json"] = {"evidence": "synthetic validation scenario", "first_date": "2011-06-06", "last_date": "2011-09-04",
        "sku_count": 100, "scenario_input_units": 246299, "unique_sku_dates": 9100, "ledger_rows": 81900,
        "holding_cost_per_unit_day": .01, "setup_cost_per_order": 1., "lead_times": [1, 3, 7], "shortage_penalties": [1, 5], "scenarios": scenarios,
        "assumptions": ["Receipts arrive before sales; orders are placed on Mondays before current-day sales.",
            "Unfulfilled units are lost, without backlog. Costs and lead times are synthetic; procurement/capacity/returns are excluded.",
            "Starting stock is the ceiling of the pre-validation 56-day mean times (lead time + 7), common across policies.",
            "Initial stock and protection targets grow with lead time; longer-lead results do not isolate delivery-delay effects.",
            "Last three reviews reuse the Aug 8 issue aged 7, 14 and 21 days. Windows are clipped at Sep 4; late arrivals are suppressed.",
            "Forecasts are exogenous historical inputs, not recomputed from simulated fulfilled sales. No daily interval bounds are summed."]}
    manifest = {"report_version": "0.1.0", "source_sha256": sources, "payloads": {},
        "scope": "Small saved aggregate reporting copies; no forecast evaluation, calibration or inventory simulation executed"}
    for name, payload in payloads.items():
        raw = (json.dumps(payload, indent=2, allow_nan=False) + "\n").encode()
        with (output / name).open("xb") as stream:
            stream.write(raw)
        manifest["payloads"][name] = {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
    with (output / "manifest.json").open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, indent=2)
        stream.write("\n")
    print(f"Packaged {len(payloads)} saved-report payloads ({sum(p['bytes'] for p in manifest['payloads'].values())} bytes); no evaluations or simulations run.")


if __name__ == "__main__":
    main()
