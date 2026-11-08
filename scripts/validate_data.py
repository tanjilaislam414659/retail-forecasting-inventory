"""Check saved data contracts independently of pipeline execution."""

import json
from importlib.metadata import version
from pathlib import Path

import pandas as pd

from retail_forecasting.acquisition import sha256


def main():
    root = Path(__file__).resolve().parents[1]
    processed = root / "data/processed"
    provenance = json.loads((root / "docs/data-provenance.json").read_text(encoding="utf-8"))
    manifest = json.loads((processed / "preparation-manifest.json").read_text(encoding="utf-8"))
    quality = json.loads((processed / "quality.json").read_text(encoding="utf-8"))
    config = manifest["protocol"]
    for key in ("archive", "workbook"):
        path = root / provenance[key]["path"]
        assert path.stat().st_size == provenance[key]["bytes"], f"Changed {key} size"
        assert sha256(path) == provenance[key]["sha256"], f"Changed {key} bytes"
    assert sha256(root / "configs/preparation.json") == manifest["protocol_sha256"]
    for name, digest in manifest["code_sha256"].items():
        assert sha256(root / "src/retail_forecasting" / name) == digest, f"Changed pipeline code: {name}"
    for name, expected_version in manifest["versions"].items():
        assert version(name) == expected_version, f"Changed installed dependency: {name}"
    for name, entry in manifest["outputs"].items():
        assert sha256(processed / name) == entry["sha256"], f"Changed output: {name}"
    cohort = pd.read_csv(processed / "sku_selection.csv", dtype={"sku": str})
    daily = pd.read_csv(processed / "sales_daily.csv.gz", dtype={"sku": str}, parse_dates=["date"])
    weekly = pd.read_csv(processed / "sales_weekly.csv.gz", dtype={"sku": str}, parse_dates=["date"])
    audit = pd.read_csv(processed / "row_audit.csv.gz", dtype={"sku": str}, usecols=[
        "record_id", "sku", "timestamp", "quantity", "disposition", "reasons", "canonical_record_id"
    ], parse_dates=["timestamp"])
    assert len(audit) == quality["raw_rows"] == sum(quality["dispositions_exclusive"].values())
    assert audit.record_id.is_unique
    copies = audit.loc[audit.disposition.eq("cross_sheet_copy")]
    assert copies.canonical_record_id.isin(audit.record_id).all()
    excluded = audit.loc[~audit.disposition.eq("selected_sale")]
    assert excluded.reasons.notna().all(), "Excluded row without reason"
    selected = audit.loc[audit.disposition.eq("selected_sale")].copy()
    assert selected.quantity.gt(0).all()
    assert selected.sku.isin(cohort.sku).all()
    selected["date"] = selected.timestamp.dt.normalize()
    expected = selected.groupby(["sku", "date"]).quantity.sum()
    actual = daily.set_index(["sku", "date"]).sales_units
    assert actual.index.is_unique
    assert expected.eq(actual.reindex(expected.index)).all()
    assert int(expected.sum()) == int(actual.sum()) == int(weekly.sales_units.sum())
    assert daily.sales_units.ge(0).all() and (daily.sales_units % 1).eq(0).all()
    assert daily.zero_filled.eq(daily.sales_lines.eq(0)).all()
    days = pd.date_range(config["train_start"], pd.Timestamp(config["end_exclusive"]) - pd.Timedelta(days=1))
    assert daily.groupby("sku").size().eq(len(days)).all()
    assert set(daily.sku) == set(cohort.sku) and 1 <= len(cohort) <= 100
    assert weekly.days_in_period.eq(7).all() and weekly.date.dt.dayofweek.eq(0).all()
    for label, start, end in (("train", config["train_start"], config["validation_start"]),
                               ("validation", config["validation_start"], config["test_start"]),
                               ("test", config["test_start"], config["end_exclusive"])):
        split = daily.loc[daily.split.eq(label)]
        assert split.date.ge(start).all() and split.date.lt(end).all()
        assert set(split.sku) == set(cohort.sku)
    assert sum(len(daily.loc[daily.split.eq(k)]) for k in ("train", "validation", "test")) == len(daily)
    ledger = pd.read_csv(processed / "returns_ledger.csv.gz", dtype={"sku": str, "invoice": str})
    assert len(ledger) == quality["returns_ledger_rows"]
    assert set(ledger.record_id) == set(audit.loc[audit.disposition.eq("returns_ledger"), "record_id"])
    assert not set(ledger.record_id) & set(selected.record_id)
    assert (ledger.quantity.lt(0) | ledger.invoice.fillna("").str.upper().str.startswith("C")).all()
    for path in processed.glob("*.csv*"):
        columns = pd.read_csv(path, nrows=0).columns
        assert not any("customer" in name.lower() for name in columns), f"Customer column in {path.name}"
    print("PASS: raw/output checksums, exhaustive audit, panel conservation, cohort coverage, splits, returns, and customer exclusion.")


if __name__ == "__main__":
    main()
