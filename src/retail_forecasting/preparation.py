"""Auditable preparation of observed positive sales; no forecasting models."""

from collections import Counter
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import time

import numpy as np
from openpyxl import load_workbook
import pandas as pd

from retail_forecasting.acquisition import sha256

HEADERS = ["Invoice", "StockCode", "Description", "Quantity", "InvoiceDate", "Price", "Customer ID", "Country"]
RENAMES = dict(zip(HEADERS, ["invoice", "sku", "description", "quantity", "timestamp", "unit_price", "customer_id", "country"]))


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def identifier(value) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, (int, float)) and float(value).is_integer():
        return str(int(value))
    return str(value).strip()


def validate_protocol(config: dict) -> None:
    dates = [pd.Timestamp(config[key]) for key in ("train_start", "validation_start", "test_start", "end_exclusive")]
    if dates != sorted(set(dates)) or any(day.dayofweek != 0 for day in dates):
        raise ValueError("Split boundaries must be strictly increasing Mondays.")
    if not 1 <= config["max_skus"] <= 100 or config["horizon_days"] != 28:
        raise ValueError("This protocol requires at most 100 SKUs and a 28-day horizon.")


def read_source(path: Path) -> tuple[pd.DataFrame, list[dict]]:
    """Read-only workbook access; retain physical Excel row numbers as provenance."""
    sheets, inspection = [], []
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        for sheet in workbook:
            print(f"Reading {sheet.title} ...", flush=True)
            iterator = sheet.iter_rows(values_only=True)
            headers = list(next(iterator))
            if headers != HEADERS:
                raise ValueError(f"Unexpected schema in {sheet.title}: {headers}")
            types = {name: Counter() for name in headers}
            rows = []
            for row in iterator:
                if len(row) != len(headers):
                    raise ValueError("Unexpected worksheet width.")
                for name, value in zip(headers, row):
                    types[name][type(value).__name__] += 1
                rows.append(row)
            frame = pd.DataFrame(rows, columns=headers)
            # Full-row fingerprints include customer only in memory to avoid false
            # duplicate matches. No customer value or fingerprint is exported.
            frame["record_key"] = [hashlib.sha256(json.dumps(row, default=str, ensure_ascii=False,
                                        separators=(",", ":")).encode("utf-8")).hexdigest() for row in rows]
            del rows
            frame = frame.rename(columns=RENAMES)
            frame["source_sheet"] = sheet.title
            frame["source_row"] = np.arange(2, len(frame) + 2)
            frame["record_id"] = frame.source_sheet + ":" + frame.source_row.astype(str)
            dates = pd.to_datetime(frame.timestamp, errors="coerce")
            inspection.append({
                "sheet": sheet.title, "rows": len(frame), "headers": headers,
                "source_python_types": {key: dict(value) for key, value in types.items()},
                "inferred_pandas_types": {key: str(frame[RENAMES[key]].dtype) for key in headers},
                "missing": {key: int(frame[RENAMES[key]].isna().sum()) for key in headers},
                "timestamp_min": dates.min().isoformat(), "timestamp_max": dates.max().isoformat(),
            })
            frame = frame.drop(columns="customer_id")
            sheets.append(frame)
    finally:
        workbook.close()
    return pd.concat(sheets, ignore_index=True), inspection


def classify(frame: pd.DataFrame, config: dict) -> tuple[pd.DataFrame, dict]:
    """Reconcile exact cross-sheet copies, then apply independent exclusion flags."""
    frame = frame.copy()
    frame["within_sheet_occurrence"] = frame.groupby(["source_sheet", "record_key"], sort=False).cumcount()
    keys = ["record_key", "within_sheet_occurrence"]
    frame["cross_sheet_copy"] = frame.duplicated(keys)
    frame["canonical_record_id"] = frame.groupby(keys, sort=False)["record_id"].transform("first")
    frame["duplicate_looking"] = frame.duplicated(["source_sheet", "record_key"], keep=False)
    additional = frame.duplicated(["source_sheet", "record_key"])
    frame["invoice"] = frame.invoice.map(identifier).str.upper()
    frame["sku"] = frame.sku.map(identifier).str.upper()
    frame["timestamp"] = pd.to_datetime(frame.timestamp, errors="coerce")
    for column in ("quantity", "unit_price"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    quantity_valid = np.isfinite(frame.quantity) & (frame.quantity.fillna(0) % 1 == 0)
    price_valid = np.isfinite(frame.unit_price) & frame.unit_price.gt(0)
    frame["cancellation"] = frame.invoice.str.startswith("C")
    frame["negative_quantity"] = frame.quantity.lt(0)
    frame["product_code"] = frame.sku.str.fullmatch(r"\d{5}[A-Z]{0,2}")
    frame["extreme_order"] = (
        frame.quantity.abs().ge(config["extreme_quantity_review_threshold"])
        | (frame.quantity * frame.unit_price).abs().ge(config["extreme_line_value_gbp_review_threshold"])
    )
    frame["date"] = frame.timestamp.dt.normalize()
    flags = {
        "cross_sheet_copy": frame.cross_sheet_copy,
        "missing_invoice": frame.invoice.eq(""),
        "missing_sku": frame.sku.eq(""),
        "invalid_timestamp": frame.timestamp.isna(),
        "invalid_quantity": ~quantity_valid,
        "nonpositive_or_invalid_price": ~price_valid,
        "non_product_code": ~frame.product_code,
        "cancellation": frame.cancellation,
        "negative_quantity": frame.negative_quantity,
        "zero_quantity": frame.quantity.eq(0),
        "outside_protocol_window": ~(frame.date.ge(config["train_start"]) & frame.date.lt(config["end_exclusive"])),
    }
    frame["reasons"] = ""
    for name, flag in flags.items():
        frame.loc[flag, "reasons"] += name + ";"
    frame["reasons"] = frame.reasons.str.rstrip(";")
    is_return = frame.cancellation | frame.negative_quantity
    malformed = flags["missing_invoice"] | flags["missing_sku"] | flags["invalid_timestamp"] | flags["invalid_quantity"]
    frame["disposition"] = np.select(
        [frame.cross_sheet_copy, is_return, malformed, ~frame.product_code, ~price_valid,
         frame.quantity.eq(0), flags["outside_protocol_window"]],
        ["cross_sheet_copy", "returns_ledger", "invalid_required_value", "non_product_code",
         "nonpositive_or_invalid_price", "zero_quantity", "outside_protocol_window"],
        default="eligible_sale",
    )
    statistics = {
        "flags_nonexclusive": {key: int(flag.sum()) for key, flag in flags.items()},
        "within_sheet_duplicate_looking_rows": int(frame.duplicate_looking.sum()),
        "within_sheet_duplicate_additional_rows": int(additional.sum()),
        "cross_sheet_copy_rows": int(frame.cross_sheet_copy.sum()),
        "extreme_review_rows": int(frame.extreme_order.sum()),
        "negative_quantity_without_cancellation": int((frame.negative_quantity & ~frame.cancellation).sum()),
        "cancellation_without_negative_quantity": int((frame.cancellation & ~frame.negative_quantity).sum()),
        "non_product_codes": {str(k): int(v) for k, v in frame.loc[~frame.product_code, "sku"].value_counts().items()},
        "quantity_min": float(frame.quantity.min()), "quantity_max": float(frame.quantity.max()),
        "price_min": float(frame.unit_price.min()), "price_max": float(frame.unit_price.max()),
        "zero_price_rows": int(frame.unit_price.eq(0).sum()),
        "negative_price_rows": int(frame.unit_price.lt(0).sum()),
        "nonfinite_price_rows": int((~np.isfinite(frame.unit_price)).sum()),
    }
    return frame, statistics


def split_labels(dates: pd.Series, config: dict) -> np.ndarray:
    return np.select([
        dates.ge(config["train_start"]) & dates.lt(config["validation_start"]),
        dates.ge(config["validation_start"]) & dates.lt(config["test_start"]),
        dates.ge(config["test_start"]) & dates.lt(config["end_exclusive"]),
    ], ["train", "validation", "test"], default="outside")


def select_skus(sales: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Filter BEFORE computing any selection statistics: held-out rows cannot vote."""
    training = sales.loc[sales.date.ge(config["train_start"]) & sales.date.lt(config["validation_start"])].copy()
    training["week"] = training.date - pd.to_timedelta(training.date.dt.dayofweek, unit="D")
    cohort = training.groupby("sku").agg(
        positive_days=("date", "nunique"), positive_weeks=("week", "nunique"),
        positive_units=("quantity", "sum"), first_training_sale=("date", "min"),
    )
    cohort["history_days_at_training_end"] = (pd.Timestamp(config["validation_start"]) - cohort.first_training_sale).dt.days
    cohort = cohort.loc[
        cohort.positive_weeks.ge(config["minimum_positive_training_weeks"])
        & cohort.history_days_at_training_end.ge(config["minimum_training_history_days"])
    ].reset_index().sort_values(["positive_days", "positive_units", "sku"], ascending=[False, False, True])
    cohort = cohort.head(config["max_skus"]).reset_index(drop=True)
    cohort.insert(0, "selection_rank", np.arange(1, len(cohort) + 1))
    if cohort.empty:
        raise ValueError("No SKUs meet the predeclared training eligibility rules.")
    return cohort


def build_panels(sales: pd.DataFrame, cohort: pd.DataFrame, config: dict) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    dates = pd.date_range(config["train_start"], pd.Timestamp(config["end_exclusive"]) - pd.Timedelta(days=1), freq="D")
    selected = sales.loc[sales.sku.isin(cohort.sku)]
    totals = selected.groupby(["sku", "date"]).agg(sales_units=("quantity", "sum"), sales_lines=("quantity", "size"))
    index = pd.MultiIndex.from_product([cohort.sku.tolist(), dates], names=["sku", "date"])
    daily = totals.reindex(index, fill_value=0).reset_index()
    daily[["sales_units", "sales_lines"]] = daily[["sales_units", "sales_lines"]].astype("int64")
    daily["zero_filled"] = daily.sales_lines.eq(0)
    daily["split"] = split_labels(daily.date, config)
    if daily.split.eq("outside").any():
        raise ValueError("Panel contains dates outside split boundaries.")
    daily["week"] = daily.date - pd.to_timedelta(daily.date.dt.dayofweek, unit="D")
    weekly = daily.groupby(["sku", "week", "split"], sort=True).agg(
        sales_units=("sales_units", "sum"), sales_lines=("sales_lines", "sum"),
        zero_filled_days=("zero_filled", "sum"), days_in_period=("date", "size"),
    ).reset_index().rename(columns={"week": "date"})
    daily = daily.drop(columns="week")
    train_daily = daily.loc[daily.split.eq("train")]
    train_weekly = weekly.loc[weekly.split.eq("train")]
    daily_zeros = train_daily.groupby("sku").sales_units.agg(lambda x: x.eq(0).mean())
    weekly_zeros = train_weekly.groupby("sku").sales_units.agg(lambda x: x.eq(0).mean())
    median_daily = float(daily_zeros.median())
    frequency = "weekly" if median_daily >= config["weekly_if_median_daily_zero_share_at_least"] else "daily"
    diagnostics = {
        "decision_uses": "selected SKUs, training dates only", "frequency": frequency,
        "median_training_daily_zero_share": median_daily,
        "median_training_weekly_zero_share": float(weekly_zeros.median()),
        "training_daily_zero_share_range": [float(daily_zeros.min()), float(daily_zeros.max())],
        "forecast_horizon_periods": config["horizon_days"] if frequency == "daily" else config["horizon_days"] // 7,
        "forecast_horizon_calendar_days": config["horizon_days"],
    }
    return daily, weekly, diagnostics


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def prepare(root: Path) -> dict:
    started = time.perf_counter()
    config_path = root / "configs/preparation.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    validate_protocol(config)
    provenance = json.loads((root / "docs/data-provenance.json").read_text(encoding="utf-8"))
    workbook = root / provenance["workbook"]["path"]
    require(sha256(workbook) == provenance["workbook"]["sha256"], "Raw workbook checksum mismatch.")
    output = root / "data/processed"
    output.mkdir(parents=True, exist_ok=True)
    frame, sheets = read_source(workbook)
    frame, quality = classify(frame, config)
    print(f"Classified {len(frame):,} source rows; selecting from training only ...", flush=True)
    sales = frame.loc[frame.disposition.eq("eligible_sale")].copy()
    cohort = select_skus(sales, config)
    daily, weekly, frequency = build_panels(sales, cohort, config)
    selected_mask = frame.disposition.eq("eligible_sale") & frame.sku.isin(cohort.sku)
    frame.loc[selected_mask, "disposition"] = "selected_sale"
    frame.loc[frame.disposition.eq("eligible_sale"), "disposition"] = "eligible_unselected_sku"
    frame.loc[frame.disposition.eq("eligible_unselected_sku"), "reasons"] = "not_in_training_selected_cohort"
    ledger = frame.loc[frame.disposition.eq("returns_ledger")].copy()
    ledger["return_units"] = (-ledger.quantity).where(ledger.quantity.lt(0))
    ledger["eligible_product_return"] = (
        ledger.product_code & ledger.quantity.lt(0) & ledger.unit_price.gt(0)
        & ledger.timestamp.notna() & ledger.invoice.ne("")
        & np.isfinite(ledger.quantity) & (ledger.quantity % 1 == 0) & np.isfinite(ledger.unit_price)
    )
    export_columns = ["record_id", "source_sheet", "source_row", "invoice", "sku", "description",
                      "timestamp", "quantity", "unit_price", "country", "disposition", "reasons",
                      "duplicate_looking", "extreme_order", "canonical_record_id"]
    frame[export_columns].to_csv(output / "row_audit.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})
    ledger[export_columns + ["return_units", "eligible_product_return"]].to_csv(
        output / "returns_ledger.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})
    daily.to_csv(output / "sales_daily.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})
    weekly.to_csv(output / "sales_weekly.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})
    cohort.to_csv(output / "sku_selection.csv", index=False)
    selected = frame.loc[selected_mask]
    # Independent controls compare row-level source quantities with both aggregations.
    require(int(selected.quantity.sum()) == int(daily.sales_units.sum()) == int(weekly.sales_units.sum()), "Panel quantity reconciliation failed.")
    require(not daily.duplicated(["sku", "date"]).any(), "Duplicate daily panel key.")
    require(not weekly.duplicated(["sku", "date"]).any(), "Duplicate weekly panel key.")
    require(weekly.days_in_period.eq(7).all(), "Incomplete or split-straddling week.")
    require(daily.sales_units.ge(0).all(), "Negative target found.")
    require("customer_id" not in daily.columns and "customer_id" not in ledger[export_columns].columns, "Customer identifier leaked.")
    overlap = []
    for i, left in enumerate(sheets):
        for right in sheets[i + 1:]:
            lower = max(pd.Timestamp(left["timestamp_min"]).normalize(), pd.Timestamp(right["timestamp_min"]).normalize())
            upper = min(pd.Timestamp(left["timestamp_max"]).normalize(), pd.Timestamp(right["timestamp_max"]).normalize())
            overlap.append({"sheets": [left["sheet"], right["sheet"]], "start_date": lower.date().isoformat(),
                            "end_date": upper.date().isoformat(), "overlap_days": max(0, (upper - lower).days + 1)})
    boundary = frame.loc[frame.date.notna()].groupby("date").agg(rows=("record_id", "size"),
                    first_timestamp=("timestamp", "min"), last_timestamp=("timestamp", "max"))
    boundary_rows = pd.concat([boundary.head(7), boundary.tail(7)]).reset_index()
    boundary_rows.to_csv(output / "boundary_dates.csv", index=False)
    missing_dates = pd.date_range(frame.date.min(), frame.date.max()).difference(boundary.index)
    retained = frame.loc[frame.disposition.isin(["selected_sale", "eligible_unselected_sku"])]
    invoice_lines = retained.assign(line_value_gbp=retained.quantity * retained.unit_price)
    invoices = invoice_lines.groupby("invoice").agg(
        timestamp=("timestamp", "min"), positive_units=("quantity", "sum"),
        line_value_gbp=("line_value_gbp", "sum"), lines=("record_id", "size"),
    ).reset_index()
    large_invoices = invoices.loc[
        invoices.positive_units.ge(config["extreme_quantity_review_threshold"])
        | invoices.line_value_gbp.ge(config["extreme_line_value_gbp_review_threshold"])
    ].sort_values(["positive_units", "invoice"], ascending=[False, True])
    large_invoices.to_csv(output / "large_invoices.csv", index=False)
    frame.loc[frame.extreme_order, export_columns].to_csv(output / "extreme_lines.csv.gz", index=False,
                                                        compression={"method": "gzip", "mtime": 0})
    overlap_details = []
    for item in overlap:
        subset = frame.loc[frame.source_sheet.isin(item["sheets"]) & frame.date.ge(item["start_date"])
                           & frame.date.le(item["end_date"])]
        overlap_details.append(item | {
            "raw_rows_by_sheet": {str(k): int(v) for k, v in subset.groupby("source_sheet").size().items()},
            "cross_sheet_copies": int(subset.cross_sheet_copy.sum()),
            "unmatched_rows_by_sheet": {str(k): int(v) for k, v in subset.loc[~subset.cross_sheet_copy].groupby("source_sheet").size().items()},
        })
    quality.update({
        "raw_rows": len(frame), "sheets": sheets, "sheet_date_overlap": overlap_details,
        "dispositions_exclusive": {str(k): int(v) for k, v in frame.disposition.value_counts().items()},
        "unique_rows_after_cross_sheet_reconciliation": int((~frame.cross_sheet_copy).sum()),
        "retained_duplicate_looking_sales_rows": int(retained.duplicate_looking.sum()),
        "retained_extreme_sales_rows": int(retained.extreme_order.sum()),
        "large_retained_invoices": len(large_invoices),
        "largest_retained_invoice_units": int(invoices.positive_units.max()),
        "largest_retained_invoice_value_gbp": float(invoices.line_value_gbp.max()),
        "missing_description_retained_sales_rows": int(retained.description.isna().sum()),
        "global_dates_without_source_rows_count": len(missing_dates),
        "eligible_sales_rows_all_skus": len(retained), "eligible_sales_units_all_skus": int(retained.quantity.sum()),
        "selected_sales_rows": len(selected), "selected_sales_units": int(selected.quantity.sum()),
        "selected_extreme_sales_rows": int(selected.extreme_order.sum()),
        "returns_ledger_rows": len(ledger), "eligible_product_return_rows": int(ledger.eligible_product_return.sum()),
        "negative_units_in_ledger": int(ledger.return_units.sum()),
        "selected_skus": len(cohort), "daily_panel_rows": len(daily), "weekly_panel_rows": len(weekly),
        "frequency_assessment": frequency,
        "daily_split_counts": {str(k): int(v) for k, v in daily.split.value_counts().items()},
        "weekly_split_counts": {str(k): int(v) for k, v in weekly.split.value_counts().items()},
        "selected_units_by_split": {str(k): int(v) for k, v in daily.groupby("split").sales_units.sum().items()},
        "global_dates_without_source_rows": [date.date().isoformat() for date in missing_dates],
        "boundary_dates": json.loads(boundary_rows.to_json(orient="records", date_format="iso")),
        "runtime_seconds": round(time.perf_counter() - started, 3),
    })
    write_json(output / "quality.json", quality)
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "raw_workbook_sha256": provenance["workbook"]["sha256"], "protocol": config,
        "protocol_sha256": sha256(config_path),
        "code_sha256": {p.name: sha256(p) for p in (Path(__file__), Path(__file__).with_name("acquisition.py"))},
        "versions": {name: version(name) for name in ("retail-forecasting", "pandas", "numpy", "openpyxl")},
        "forecast_panel": "data/processed/sales_" + frequency["frequency"] + ".csv.gz",
        "frequency_assessment": frequency,
        "outputs": {p.name: {"bytes": p.stat().st_size, "sha256": sha256(p)} for p in sorted(output.iterdir()) if p.is_file() and p.name != "preparation-manifest.json"},
    }
    write_json(output / "preparation-manifest.json", manifest)
    render_quality_report(root, quality, provenance, config)
    print(json.dumps({key: quality[key] for key in ("raw_rows", "dispositions_exclusive", "selected_skus", "daily_panel_rows", "weekly_panel_rows", "selected_sales_units", "frequency_assessment", "runtime_seconds")}, indent=2), flush=True)
    return quality


def render_quality_report(root: Path, quality: dict, provenance: dict, config: dict) -> None:
    """Create a concise committed report from actual measurements, not manual counts."""
    q = quality
    frequency = q["frequency_assessment"]
    lines = [
        "# Milestone 2: data-quality report", "",
        "Generated by `python -m retail_forecasting prepare`. All counts below are measured from the acquired workbook.", "",
        "## Acquisition and workbook inspection", "",
        f"Retrieved {provenance['retrieved_at_utc']}. Workbook: **{provenance['workbook']['bytes']:,} bytes**.",
        f"SHA-256: `{provenance['workbook']['sha256']}`.",
        "Source, archive integrity, license, and attribution: [provenance](data-provenance.json). The workbook is unchanged.", "",
        "| Actual sheet | Rows | First timestamp | Last timestamp | Missing description | Missing customer ID |",
        "| --- | ---: | --- | --- | ---: | ---: |",
    ]
    for sheet in q["sheets"]:
        lines.append(f"| {sheet['sheet']} | {sheet['rows']:,} | {sheet['timestamp_min']} | {sheet['timestamp_max']} | {sheet['missing']['Description']:,} | {sheet['missing']['Customer ID']:,} |")
    lines += [
        "", f"Total **{q['raw_rows']:,} rows**, matching UCI's published total. Actual headers are `Invoice`, `StockCode`, `Description`, `Quantity`, `InvoiceDate`, `Price`, `Customer ID`, `Country`.",
        "Published `InvoiceNo`, `UnitPrice`, and `CustomerID` therefore map to actual `Invoice`, `Price`, and `Customer ID`. SKU codes can have letter suffixes; invoice/SKU columns mix numbers and text. Normalize identifiers to strings. Quantities are integers, prices numeric, timestamps datetime values without a supplied timezone. Description includes four numeric cells. Full per-sheet type counts are in `data/processed/quality.json`.",
        "Missingness is concentrated in description/customer fields. Invoice, SKU, quantity, timestamp, price and country have no missing cells. Missing customer IDs do not invalidate SKU sales; customers are excluded from derived files. Missing description does not exclude an otherwise valid sale.", "",
        "## Overlap, repeated records, and extreme orders", "",
    ]
    for item in q["sheet_date_overlap"]:
        lines.append(f"The sheets overlap **{item['start_date']} through {item['end_date']}** ({item['overlap_days']} calendar days). Raw rows by sheet in that interval: `{item['raw_rows_by_sheet']}`. Exact cross-sheet copies removed: **{item['cross_sheet_copies']:,}**. Unmatched rows remain; no date range is dropped wholesale.")
    lines += [
        f"There are **{q['within_sheet_duplicate_additional_rows']:,} additional identical-looking rows within individual sheets** ({q['within_sheet_duplicate_looking_rows']:,} participating rows). They are not automatically removed. **{q['retained_duplicate_looking_sales_rows']:,} duplicate-looking rows** remain in eligible sales across all SKUs.",
        f"Review flags identify **{q['extreme_review_rows']:,} source line items** with absolute quantity >=1,000 or absolute line value >=GBP10,000. **{q['retained_extreme_sales_rows']:,} large line items** remain in eligible sales, including **{q['selected_extreme_sales_rows']:,}** in the selected cohort. No winsorization or size exclusion is applied.",
        f"Across eligible sales, **{q['large_retained_invoices']:,} invoices** meet the same thresholds on invoice totals. The largest retained invoice contains **{q['largest_retained_invoice_units']:,} units**; the largest invoice value is **GBP{q['largest_retained_invoice_value_gbp']:,.2f}** (these maxima need not belong to the same invoice). See `large_invoices.csv` and `extreme_lines.csv.gz` under `data/processed/`.", "",
        "## Quality flags and exclusive row accounting", "",
        f"Raw quantities range from {q['quantity_min']:,.0f} to {q['quantity_max']:,.0f}; prices from GBP{q['price_min']:,.2f} to GBP{q['price_max']:,.2f}. There are **{q['zero_price_rows']:,} zero-price** and **{q['negative_price_rows']:,} negative-price rows**, {q['nonfinite_price_rows']:,} nonfinite prices, and no invalid timestamps/noninteger quantities/zero quantities.",
        f"Raw cancellation flags: **{q['flags_nonexclusive']['cancellation']:,}**; negative-quantity rows: **{q['flags_nonexclusive']['negative_quantity']:,}**. **{q['negative_quantity_without_cancellation']:,}** negative rows lack a cancellation prefix, and **{q['cancellation_without_negative_quantity']:,}** cancellation row has no negative quantity. These counts overlap other flags and include cross-sheet copies.",
        f"**{q['flags_nonexclusive']['non_product_code']:,} rows** fail the declared merchandise-code pattern. Common examples: POST, DOT, M, C2, D, BANK CHARGES, ADJUST, gift vouchers. The pattern is a reproducible scope heuristic, not a verified merchandise catalogue; ambiguous exceptions remain a limitation.", "",
        "| Exclusive disposition (in precedence order) | Rows |", "| --- | ---: |",
    ]
    order = ["cross_sheet_copy", "returns_ledger", "invalid_required_value", "non_product_code",
             "nonpositive_or_invalid_price", "zero_quantity", "outside_protocol_window",
             "eligible_unselected_sku", "selected_sale"]
    for name in order:
        lines.append(f"| {name} | {q['dispositions_exclusive'].get(name, 0):,} |")
    lines += [
        f"| **Total** | **{q['raw_rows']:,}** |", "",
        f"After overlap reconciliation: **{q['unique_rows_after_cross_sheet_reconciliation']:,} rows**. Within the study dates, eligible positive sales across all SKUs: **{q['eligible_sales_rows_all_skus']:,} lines / {q['eligible_sales_units_all_skus']:,} units**.",
        f"The separate returns/adjustments ledger contains **{q['returns_ledger_rows']:,} rows**, of which **{q['eligible_product_return_rows']:,}** pass the product/negative-quantity/positive-price checks. Negative quantities in the entire ledger total **{q['negative_units_in_ledger']:,} units**; this includes adjustments and is not a verified customer-return total. Returns are not matched to original purchases or netted from the target.",
        "Every source row has a sheet/Excel-row pointer, disposition, and exclusion reasons in `row_audit.csv.gz`. Cross-sheet copies point to their retained counterpart. Exclusive disposition counts sum to the source total; nonexclusive issue counts must not be summed.", "",
        "## Fixed splits, cohort, and frequency", "",
        "Boundaries and selection/frequency rules were saved in `configs/preparation.json` before workbook inspection. Calendar dates below are inclusive; intervals are implemented with exclusive next-period boundaries.", "",
        "| Split | Date range | Daily panel rows | Positive units |", "| --- | --- | ---: | ---: |",
        f"| Train / development | {config['train_start']} to 2011-06-05 | {q['daily_split_counts']['train']:,} | {q['selected_units_by_split']['train']:,} |",
        f"| Validation | {config['validation_start']} to 2011-09-04 | {q['daily_split_counts']['validation']:,} | {q['selected_units_by_split']['validation']:,} |",
        f"| Final test | {config['test_start']} to 2011-12-04 | {q['daily_split_counts']['test']:,} | {q['selected_units_by_split']['test']:,} |", "",
        f"Selected **{q['selected_skus']} SKUs** using training only: at least {config['minimum_positive_training_weeks']} positive weeks and {config['minimum_training_history_days']} days of history from the first training sale to training end. Rank by positive sale days descending, then positive units descending, then SKU ascending. Keep the first {config['max_skus']}; no held-out eligibility or performance filtering.",
        f"Median zero share in training: **{frequency['median_training_daily_zero_share']:.2%} daily**, **{frequency['median_training_weekly_zero_share']:.2%} weekly**. The predeclared 50% daily-zero threshold selects **{frequency['frequency']} forecasting**. Proposed horizon: **{frequency['forecast_horizon_periods']} periods / 28 calendar days**, a four-week planning scenario rather than a measured supplier lead time.",
        f"The selected cohort has **{q['selected_sales_rows']:,} positive source lines / {q['selected_sales_units']:,} units**. Daily grid: **{q['daily_panel_rows']:,} rows**; Monday-start weekly aggregate: **{q['weekly_panel_rows']:,} rows**. Daily and weekly quantities both reconcile to the selected source lines.", "",
        "## Boundary dates, zeros, and limitations", "",
        "Full Monday-to-Sunday study weeks avoid partial first/last weeks. The source starts 2009-12-01 at 07:45 and ends 2011-12-09 at 12:50; the last date appears truncated. Dates before 2009-12-07 and from 2011-12-05 remain in the audit/ledger but not the sales panel. No calendar completeness is inferred from those timestamps alone.",
        f"There are **{q['global_dates_without_source_rows_count']} calendar dates without any source rows** between the raw endpoints. They could represent closure, missing collection, or no transactions. The explicit list and first/last seven observed dates/times are in `quality.json` and `boundary_dates.csv`.",
        "For the fixed training-selected cohort, the grid spans all 728 study days, including before the first and after the last observed sale. A day with no accepted positive sales line receives zero observed sales and `zero_filled=True`; this does not assert availability, listing status, store opening, or zero latent demand. No future sale is used to infer inactivity or trim a SKU's grid. Weekly rows report their zero-filled-day count.",
        "The cohort favors historically frequent established products and will not represent new or slow-moving SKUs. Sales may be stockout-censored; assortment, opening hours, inventory and lost demand are unknown. Customer country is not store location. Inventory lead times/costs are absent, returns may be administrative adjustments, and the code-pattern scope may omit legitimate special codes. Repeated transactions may still inflate sales; they are retained pending stronger evidence.",
        "Final-test records were inspected for data quality and mechanical reconciliation only. They must not be used to revise cohort, frequency, horizon or model decisions. No models have been trained.", "",
        "## Reproduction and next milestone", "",
        "See [Milestone 2 protocol and commands](milestone-2.md). Generated data and raw files are ignored by Git. The preparation manifest records source/config/code hashes, output hashes, and installed library versions. Checks cover synthetic boundary/leakage cases plus saved-data reconciliation.",
        "Next: seasonal-naive (lag 7), last-value, and training-mean baselines with 28-day rolling-origin validation, per-SKU and pooled MAE/WAPE, and explicit zero-denominator handling. Freeze choices before one final-test evaluation. Establish forecast baselines before inventory simulation.", "",
    ]
    (root / "docs/data-quality-report.md").write_text("\n".join(lines), encoding="utf-8")
