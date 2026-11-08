"""Frozen-spec validation inventory replay; existing results are verified on repeat."""

from datetime import datetime, timezone
from fractions import Fraction
from importlib.metadata import version
import gzip
import hashlib
import json
import math
from pathlib import Path
import time
import traceback

import numpy as np
import pandas as pd

from retail_forecasting.final_evaluation import verify_existing as verify_final
from retail_forecasting.inventory import __version__
from retail_forecasting.inventory.simulation import ForecastBook, POLICIES, require, simulate_one, summarize


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def json_read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def json_write(path, data):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(data, stream, indent=2, allow_nan=False)
        stream.write("\n")


def frame_write(path, frame):
    if path.suffix == ".gz":
        with path.open("xb") as raw:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
                compressed.write(frame.to_csv(index=False).encode("utf-8"))
    else:
        with path.open("x", encoding="utf-8", newline="") as stream:
            frame.to_csv(stream, index=False)


def check_hashes(root, hashes):
    for name, expected in hashes.items():
        require((root / name).is_file() and sha(root / name) == expected, "Preserved artifact changed: " + name)


def protected_inputs(root):
    verify_final(root)  # Integrity only; does not evaluate or regenerate anything.
    freeze = json_read(root / "data/final_evaluation/freeze.json")
    final = json_read(root / "data/final_evaluation/manifest.json")
    hashes = dict(freeze["sha256"])
    hashes.update(final["artifact_sha256"])
    for name in ("data/final_evaluation/manifest.json", "service/release-0.1.0.json", "deployment/release-0.1.0.json", "deployment/container-verification-20261104.json"):
        hashes[name] = sha(root / name)
    api = json_read(root / "service/release-0.1.0.json")
    hashes.update(api["source_configuration_sha256"])
    hashes.update(api["evidence_sha256"])
    container = json_read(root / "deployment/container-verification-20261104.json")
    hashes.update(container["source_sha256"])
    hashes.update(container["evidence_sha256"])
    for directory, manifest_file, key in (
        ("artifacts/frozen-release/milestone-7-fcd91ea17928", "snapshot-manifest.json", "copied_sha256"),
        ("artifacts/engineering/milestone-9-pre-container-verification", "manifest.json", "sha256"),
        ("artifacts/runtime/milestone-9-v0.1.0", "bundle-manifest.json", "files")):
        base = root / directory
        record = json_read(base / manifest_file)
        hashes[directory + "/" + manifest_file] = sha(base / manifest_file)
        for name, entry in record[key].items():
            hashes[directory + "/" + name] = entry["sha256"] if isinstance(entry, dict) else entry
    check_hashes(root, hashes)
    return hashes


def freeze_run(root, output):
    require(not output.exists(), "Simulation output already exists; refusing a new freeze")
    config = json_read(root / "configs/inventory-simulation.json")
    require(config["simulation_version"] == __version__ and config["start_date"] == "2011-06-06"
        and config["end_date_exclusive"] == "2011-09-05" and config["lead_times_days"] == [1, 3, 7]
        and config["shortage_costs_per_unfulfilled_unit"] == [1., 5.]
        and config["holding_cost_per_end_of_day_unit"] == .01 and config["fixed_cost_per_positive_sku_order"] == 1.
        and [p["name"] for p in config["policies"]] == list(POLICIES)
        and [p["forecast_multiplier"] for p in config["policies"]] == list(POLICIES.values())
        and not config["tuning_or_policy_search"] and not config["final_test_usage"], "Fixed simulation specification changed")
    protected = protected_inputs(root)
    sources = [root / "configs/inventory-simulation.json", root / "docs/inventory-simulation-spec.md", root / "tests/test_inventory.py", root / "scripts/validate_inventory.py"]
    sources.extend(sorted(Path(__file__).parent.glob("*.py")))
    hashes = {p.relative_to(root).as_posix(): sha(p) for p in sources}
    output.mkdir(parents=True, exist_ok=False)
    record = {"specified_before_execution_at_utc": now(), "configuration": config,
        "source_and_specification_sha256": hashes, "protected_artifact_sha256": protected,
        "input_sha256": {name: sha(root / name) for name in (config["sales_file"], config["forecast_file"], "data/processed/sku_selection.csv")},
        "versions": {name: version(name) for name in ("retail-forecasting", "numpy", "pandas", "matplotlib")},
        "scope": "Fixed synthetic inventory scenarios on validation only; no final sales or interval bounds as inputs"}
    json_write(output / "specification-record.json", record)
    print(f"Inventory specification frozen at {record['specified_before_execution_at_utc']}; {len(protected)} prior artifacts protected.", flush=True)
    return record


def verify_completed(root, output):
    manifest = json_read(output / "manifest.json")
    require(manifest["status"] == "complete", "Simulation incomplete")
    check_hashes(root, manifest["artifact_sha256"])
    spec = json_read(output / "specification-record.json")
    check_hashes(root, spec["protected_artifact_sha256"])
    check_hashes(root, spec["source_and_specification_sha256"])
    check_hashes(root, spec["input_sha256"])
    return json_read(output / "summary.json")


def audit(ledger, orders, replay_sales):
    keys = ["lead_time_days", "policy", "sku", "date"]
    require(len(ledger) == 81900 and not ledger.duplicated(keys).any(), "Physical ledger key/count mismatch")
    require(ledger.date.ge("2011-06-06").all() and ledger.date.lt("2011-09-05").all(), "Ledger date outside validation")
    require(ledger.groupby(keys[:3]).size().eq(91).all(), "A trajectory does not span all 91 days")
    require((ledger.fulfilled_units + ledger.unfulfilled_units).eq(ledger.scenario_input_units).all(), "Input service/lost reconciliation failed")
    require((ledger.opening_stock + ledger.receipts_units - ledger.fulfilled_units).eq(ledger.closing_stock).all(), "Stock conservation failed")
    require((ledger.opening_pipeline_units + ledger.order_units - ledger.receipts_units).eq(ledger.closing_pipeline_units).all(), "Pipeline conservation failed")
    require(ledger[["closing_stock", "closing_pipeline_units", "fulfilled_units", "unfulfilled_units", "order_units"]].ge(0).all().all(), "Negative units in ledger")
    aligned = ledger.merge(replay_sales.rename(columns={"sales_units": "source_units"}), on=["sku", "date"], validate="many_to_one")
    require(aligned.scenario_input_units.eq(aligned.source_units).all(), "Replayed sales differ from single-date source")
    review = ledger.loc[ledger.review]
    require(review.groupby(keys[:3]).size().eq(13).all(), "Wrong review count")
    require(ledger.loc[ledger.order_units.gt(0), "review"].all(), "An order is not on a review day")
    for _, group in ledger.groupby(keys[:3], sort=False):
        require(np.array_equal(group.opening_stock.iloc[1:], group.closing_stock.iloc[:-1]), "Stock reset across dates/origins")
        require(np.array_equal(group.opening_pipeline_units.iloc[1:], group.closing_pipeline_units.iloc[:-1]), "Pipeline reset across dates/origins")
    require(not orders.order_id.duplicated().any(), "Duplicate order ID")
    require(orders.received_date.notna().all() and orders.received_units.eq(orders.order_units).all(), "Missing/mismatched receipt")
    require((orders.due_date - orders.order_date).dt.days.eq(orders.lead_time_days).all()
        and orders.received_date.eq(orders.due_date).all() and orders.due_date.lt("2011-09-05").all(), "Receipt lead-time/boundary failure")
    receipt_totals = orders.groupby(keys[:3] + ["received_date"]).received_units.sum().reset_index().rename(columns={"received_date": "date"})
    receipts = ledger.merge(receipt_totals, on=keys, how="left", validate="one_to_one")
    require(receipts.receipts_units.eq(receipts.received_units.fillna(0)).all(), "Daily receipts differ from order audit")
    used = review.loc[review.policy.ne("static_reference")]
    require(used.forecast_origin.notna().all() and used.forecast_origin.le(used.date).all(), "Future or missing forecast issue")
    require((used.date - used.forecast_origin).dt.days.eq(used.forecast_age_days).all(), "Forecast age mismatch")
    require((used.date + pd.to_timedelta(used.protection_days - 1, unit="D")).le(used.forecast_origin + pd.Timedelta(days=27)).all(), "Protection beyond saved forecast")
    require(ledger.groupby(["lead_time_days", "policy"]).scenario_input_units.sum().eq(replay_sales.sales_units.sum()).all(), "Overlapping forecast dates counted as extra sales")


def show(summary, prefix):
    print(prefix, flush=True)
    frame = pd.DataFrame(summary["scenario_metrics"])
    print(frame[["lead_time_days", "shortage_cost_per_unit", "policy", "fulfilled_unit_rate_pct", "unfulfilled_units", "average_total_closing_inventory", "order_count", "total_simulated_cost"]].to_string(index=False), flush=True)


def run(root, output):
    if (output / "manifest.json").exists():
        result = verify_completed(root, output)
        show(result, "Verified saved inventory simulation; no ledger replay or overwrite.")
        return result
    if not output.exists():
        freeze_run(root, output)
    spec = json_read(output / "specification-record.json")
    check_hashes(root, spec["source_and_specification_sha256"])
    check_hashes(root, spec["protected_artifact_sha256"])
    require(not (output / "started.json").exists(), "A simulation already started; preserve partial outputs and investigate rather than overwrite")
    json_write(output / "started.json", {"executed_at_utc": now(), "specification_record_sha256": sha(output / "specification-record.json")})
    try:
        return execute(root, output, spec)
    except Exception:
        json_write(output / "failure.json", {"recorded_at_utc": now(), "exception": traceback.format_exc(), "policy": "Preserve partial outputs; do not tune or silently retry"})
        raise


def execute(root, output, spec):
    started = time.perf_counter()
    config = spec["configuration"]
    history = pd.read_csv(root / config["sales_file"], dtype={"sku": str}, parse_dates=["date"], usecols=["sku", "date", "sales_units"])
    require(len(history) == 63216 and history.date.lt("2011-09-05").all(), "Original modelling history boundary/count mismatch")
    cohort = pd.read_csv(root / "data/processed/sku_selection.csv", dtype={"sku": str})
    skus = sorted(cohort.sku.tolist())
    require(len(skus) == len(set(skus)) == 100 and set(history.sku) == set(skus), "Cohort changed")
    require(not history.duplicated(["sku", "date"]).any(), "History has duplicate dates")
    saved = pd.read_csv(root / config["forecast_file"], dtype={"sku": str}, parse_dates=["origin", "target_date"],
        usecols=["model", "sku", "origin", "target_date", "horizon_day", "predicted_sales"])
    points = saved.loc[saved.model.eq("weekday_mean")].copy()
    require(len(points) == 28000 and set(points.sku) == set(skus)
        and sorted(points.origin.dt.strftime("%Y-%m-%d").unique()) == config["available_forecast_origins"]
        and points.target_date.lt("2011-09-05").all(), "Saved validation forecast grid mismatch")
    require((points.target_date - points.origin).dt.days.eq(points.horizon_day - 1).all(), "Forecast day misalignment")
    book = ForecastBook(points)
    lookup = {sku: rows.set_index("date").sales_units.sort_index() for sku, rows in history.groupby("sku")}
    training_dates = pd.date_range("2011-04-11", "2011-06-05")
    validation_dates = pd.date_range("2011-06-06", "2011-09-04")
    references, sales = {}, {}
    initialization = []
    for sku in skus:
        training = lookup[sku].reindex(training_dates)
        require(training.notna().all() and training.ge(0).all() and training.mod(1).eq(0).all(), "Missing/invalid initialization history")
        references[sku] = Fraction(int(training.sum()), 56)
        sales[sku] = lookup[sku].reindex(validation_dates)
        require(sales[sku].notna().all(), "Missing validation date; no new zero filling permitted")
        for lead in config["lead_times_days"]:
            initialization.append({"sku": sku, "lead_time_days": lead, "training_history_days": 56,
                "history_first": "2011-04-11", "history_last": "2011-06-05", "history_units": int(training.sum()),
                "reference_daily_mean": float(references[sku]), "starting_stock": math.ceil(references[sku] * (lead + 7)), "starting_pipeline_units": 0})
    frame_write(output / "initialization.csv", pd.DataFrame(initialization))
    replay_sales = history.loc[history.date.ge("2011-06-06")].sort_values(["sku", "date"])
    require(len(replay_sales) == 9100, "Unique replay count mismatch")
    frame_write(output / "validation_scenario_input.csv.gz", replay_sales)
    load_seconds = time.perf_counter() - started
    print("Replaying fixed continuous validation ledgers for 100 SKUs, three policies and three lead times ...", flush=True)
    simulation_started = time.perf_counter()
    replays = [simulate_one(sku, sales[sku], book, policy, lead, references[sku],
        math.ceil(references[sku] * (lead + 7)), config["holding_cost_per_end_of_day_unit"], config["fixed_cost_per_positive_sku_order"])
        for lead in config["lead_times_days"] for policy in POLICIES for sku in skus]
    ledger = pd.concat([item.ledger for item in replays], ignore_index=True)
    ledger["forecast_origin"] = pd.to_datetime(ledger.forecast_origin)
    ledger["order_due_date"] = pd.to_datetime(ledger.order_due_date)
    nonempty_orders = [item.orders for item in replays if not item.orders.empty]
    orders = pd.concat(nonempty_orders, ignore_index=True)
    simulation_seconds = time.perf_counter() - simulation_started
    audit(ledger, orders, replay_sales)
    frame_write(output / "daily_inventory_ledger.csv.gz", ledger)
    frame_write(output / "orders_receipts.csv.gz", orders)
    by_sku, metrics = summarize(ledger, config["shortage_costs_per_unfulfilled_unit"])
    require(len(by_sku) == 1800 and len(metrics) == 18, "Economic scenario count mismatch")
    frame_write(output / "metrics_by_sku.csv", by_sku)
    frame_write(output / "scenario_metrics.csv", metrics)
    weekly_data = ledger.assign(week_start=ledger.date - pd.to_timedelta(ledger.date.dt.dayofweek, unit="D"), positive_order=ledger.order_units.gt(0).astype(int))
    weekly = weekly_data.groupby(["lead_time_days", "policy", "week_start"]).agg(
        scenario_input_units=("scenario_input_units", "sum"), fulfilled_units=("fulfilled_units", "sum"), unfulfilled_units=("unfulfilled_units", "sum"),
        inventory_unit_days=("closing_stock", "sum"), order_count=("positive_order", "sum")).reset_index()
    weekly["fulfilled_unit_rate_pct"] = 100 * weekly.fulfilled_units / weekly.scenario_input_units.where(weekly.scenario_input_units.ne(0))
    weekly["average_total_closing_inventory"] = weekly.inventory_unit_days / 7
    frame_write(output / "metrics_by_week.csv", weekly)
    from retail_forecasting.inventory.reporting import make_plot, write_report
    plot = make_plot(root, metrics)
    used = ledger.loc[ledger.review & ledger.policy.ne("static_reference")]
    result = {"version": __version__, "scenario": config["interpretation"], "start": "2011-06-06", "last_date": "2011-09-04",
        "sku_count": 100, "unique_sku_date_inputs": len(replay_sales), "observed_positive_sales_units_per_physical_alternative": int(replay_sales.sales_units.sum()),
        "physical_trajectories": 900, "ledger_rows": len(ledger), "order_rows": len(orders), "economic_sku_rows": len(by_sku), "aggregate_scenario_rows": len(metrics),
        "forecast_reviews": len(used), "aged_forecast_review_counts": {str(int(age)): int(count) for age, count in used.forecast_age_days.value_counts().sort_index().items()},
        "late_arrival_ineligible_reviews": int(ledger.terminal_order_blocked.sum()),
        "positive_suggested_orders_suppressed_at_terminal": int((ledger.terminal_order_blocked & ledger.suggested_order_units.gt(0)).sum()),
        "load_seconds": load_seconds, "simulation_seconds": simulation_seconds,
        "wall_seconds": time.perf_counter() - started, "scenario_metrics": json.loads(metrics.to_json(orient="records")),
        "plot": plot, "integrity_checks": "PASS", "final_test_used": False, "interval_bounds_used": False, "implementation_defects": []}
    report = write_report(root, result, metrics)
    json_write(output / "summary.json", result)
    check_hashes(root, spec["protected_artifact_sha256"])
    artifacts = [path for path in output.iterdir() if path.is_file()] + [root / plot, root / report]
    json_write(output / "manifest.json", {"status": "complete", "completed_at_utc": now(),
        "artifact_sha256": {path.relative_to(root).as_posix(): sha(path) for path in sorted(artifacts)},
        "report": report, "plot": plot, "scope": "Synthetic validation inventory development; no new held-out assessment"})
    verify_completed(root, output)
    show(result, "Inventory scenario simulation complete; outcomes are synthetic, not business savings.")
    return result
