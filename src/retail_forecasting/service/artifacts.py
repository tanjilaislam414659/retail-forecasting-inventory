"""Load pinned processed inputs once, validate them, and build an inference engine."""

from dataclasses import dataclass
from datetime import date, timedelta
import hashlib
from io import BytesIO
import json
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

import numpy as np
import pandas as pd

from retail_forecasting.service import __version__
from retail_forecasting.service.inference import infer_one
from retail_forecasting.service.schemas import ForecastResponse, MetadataResponse

ARTIFACT_KEYS = {"history", "cohort", "history_mask", "quantiles", "calibration_record", "baseline_spec", "release_spec",
    "uncertainty_spec", "point_code", "interval_code", "release_freeze", "release_manifest", "snapshot_manifest"}
LIMITATIONS = [
    "Historical demonstration only: 100 frozen SKUs and 20 evaluated 2011 origins; not a live retail-data service.",
    "Observed positive sales are not uncensored demand; listing, availability and stockouts are unknown.",
    "Experimental empirical historical-error daily intervals: weak coverage for some SKUs/weekdays, broad bands, no coverage guarantee.",
    "Daily bounds are not calibrated total-28-day or joint bounds; do not sum them as an aggregate interval.",
    "Walk-forward history uses sales strictly before origin; frozen method and original-training quantiles never update.",
    "Final test has already been consumed; this service adds no new model-performance evidence or inventory-benefit claim.",
    "Local single-process portfolio API; not production-ready.",
]


class ArtifactError(RuntimeError):
    def __init__(self, code: str, artifact: str):
        super().__init__(f"{code}: {artifact}")
        self.code, self.artifact = code, artifact


class UnsupportedRequest(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def ensure(condition, artifact):
    if not condition:
        raise ArtifactError("invalid_artifact", artifact)


@dataclass(frozen=True)
class InferenceEngine:
    histories: Mapping[str, pd.Series]
    quantiles: pd.DataFrame
    skus: tuple[str, ...]
    origins: tuple[date, ...]
    forecast_release_id: str
    calibration_id: str

    def predict(self, sku, origin, horizon_days=28):
        if sku not in self.skus:
            raise UnsupportedRequest("unknown_sku", "SKU is not in the frozen 100-SKU cohort; see /metadata")
        if origin not in self.origins:
            raise UnsupportedRequest("unsupported_origin", "Origin is not one of the 20 supported historical dates; see /metadata")
        if type(horizon_days) is not int or horizon_days != 28:
            raise UnsupportedRequest("unsupported_horizon", "Only horizon_days=28 is supported")
        series = self.histories[sku]
        past = series.loc[series.index < pd.Timestamp(origin)]
        return ForecastResponse(service_version=__version__, forecast_release_id=self.forecast_release_id,
            calibration_id=self.calibration_id, sku=sku, origin=origin, history_cutoff=origin - timedelta(days=1),
            predictions=infer_one(past, self.quantiles, sku, origin, horizon_days))

    def metadata(self):
        return MetadataResponse(service_version=__version__, forecast_release_id=self.forecast_release_id,
            calibration_id=self.calibration_id, supported_skus=list(self.skus), supported_origins=list(self.origins),
            limitations=LIMITATIONS)


def load_engine(root: Path) -> InferenceEngine:
    """Only this loader touches disk. No evaluation forecast file is required/read."""
    root = root.resolve()
    try:
        contract = json.loads((root / "service/artifact-contract.json").read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ArtifactError("missing_artifact", "contract") from exc
    except (OSError, ValueError) as exc:
        raise ArtifactError("invalid_artifact", "contract") from exc
    try:
        return _load(root, contract)
    except ArtifactError:
        raise
    except (OSError, ValueError, TypeError, KeyError, AttributeError, pd.errors.ParserError) as exc:
        raise ArtifactError("invalid_artifact", "processed_inputs") from exc


def _load(root, contract):
    origins = pd.date_range("2011-06-06", "2011-08-08", freq="7D").strftime("%Y-%m-%d").tolist()
    origins += pd.date_range("2011-09-05", "2011-11-07", freq="7D").strftime("%Y-%m-%d").tolist()
    ensure(contract["service_version"] == __version__ and contract["forecast_method"] == "weekday_mean"
        and contract["horizon_days"] == 28 and contract["cohort_size"] == 100
        and contract["origins"] == origins and set(contract["artifacts"]) == ARTIFACT_KEYS, "contract")
    blobs = {}
    for name, entry in contract["artifacts"].items():
        path = (root / entry["path"]).resolve()
        ensure(path.is_relative_to(root), "contract")
        try:
            blob = path.read_bytes()
        except FileNotFoundError as exc:
            raise ArtifactError("missing_artifact", name) from exc
        except OSError as exc:
            raise ArtifactError("unreadable_artifact", name) from exc
        if hashlib.sha256(blob).hexdigest() != entry["sha256"]:
            raise ArtifactError("checksum_mismatch", name)
        blobs[name] = blob
    read_json = lambda name: json.loads(blobs[name])
    calibration = read_json("calibration_record")
    ensure(calibration["calibration_target_end_exclusive"] == "2011-06-06"
        and calibration["quantiles_sha256"] == contract["artifacts"]["quantiles"]["sha256"]
        and contract["calibration_id"] == "sha256:" + calibration["quantiles_sha256"], "calibration_record")
    ensure(read_json("baseline_spec")["origins"] == origins[:10]
        and read_json("release_spec")["origins"] == origins[10:]
        and read_json("uncertainty_spec")["calibration_target_end_exclusive"] == "2011-06-06", "specifications")
    freeze = read_json("release_freeze")
    ensure(read_json("release_manifest")["freeze_sha256"] == contract["artifacts"]["release_freeze"]["sha256"], "release_manifest")
    for name in ("history", "cohort", "history_mask", "quantiles", "calibration_record", "point_code", "interval_code"):
        item = contract["artifacts"][name]
        ensure(freeze["sha256"][item["path"]] == item["sha256"], "frozen_input_identity")
    ensure(contract["forecast_release_id"] == "weekday-mean-1.0+" + contract["artifacts"]["release_freeze"]["sha256"][:12], "release_identity")
    snapshot = read_json("snapshot_manifest")
    ensure(snapshot["freeze_sha256"] == contract["artifacts"]["release_freeze"]["sha256"]
        and snapshot["original_evaluation_manifest_sha256"] == contract["artifacts"]["release_manifest"]["sha256"], "snapshot_identity")
    dtype = {"sku": str}
    cohort = pd.read_csv(BytesIO(blobs["cohort"]), dtype=dtype)
    mask = pd.read_csv(BytesIO(blobs["history_mask"]), dtype=dtype, parse_dates=["modelling_start"])
    history = pd.read_csv(BytesIO(blobs["history"]), compression="gzip", dtype=dtype,
        usecols=["sku", "date", "sales_units"], parse_dates=["date"])
    # Preserve original default parsing of calibration numeric values, as evaluated.
    quantiles = pd.read_csv(BytesIO(blobs["quantiles"]), dtype=dtype)
    skus = tuple(sorted(cohort.sku))
    ensure(len(skus) == len(set(skus)) == len(mask) == 100 and set(mask.sku) == set(skus)
        and not mask.sku.duplicated().any(), "cohort")
    ensure(mask.excluded_leading_days.sum() == 484 and mask.excluded_leading_days.gt(0).sum() == 10
        and mask.loc[mask.sku.eq("21166"), "modelling_start"].iloc[0] == pd.Timestamp("2009-12-07"), "history_mask")
    ensure(len(history) == 72800 and set(history.sku) == set(skus)
        and not history.duplicated(["sku", "date"]).any()
        and history.date.notna().all() and np.isfinite(history.sales_units).all()
        and history.sales_units.ge(0).all() and history.sales_units.mod(1).eq(0).all(), "history")
    expected_dates = pd.date_range("2009-12-07", "2011-12-04")
    for _, group in history.groupby("sku"):
        ensure(pd.DatetimeIndex(group.date.sort_values()).equals(expected_dates), "history_calendar")
    expected_groups = {(sku, week, level) for sku in skus for week in range(1, 5) for level in (80, 95)}
    ensure(len(quantiles) == 800 and set(quantiles[["sku", "horizon_week", "level"]].itertuples(index=False, name=None)) == expected_groups
        and quantiles.calibration_status.eq("defined").all()
        and np.isfinite(quantiles[["lower_residual_quantile", "upper_residual_quantile"]]).all().all()
        and quantiles.lower_residual_quantile.le(quantiles.upper_residual_quantile).all()
        and quantiles.residual_count.gt(0).all(), "quantiles")
    nested = quantiles.pivot(index=["sku", "horizon_week"], columns="level", values=["lower_residual_quantile", "upper_residual_quantile"])
    ensure(nested.lower_residual_quantile[95].le(nested.lower_residual_quantile[80]).all()
        and nested.upper_residual_quantile[95].ge(nested.upper_residual_quantile[80]).all(), "quantile_nesting")
    starts = mask.set_index("sku").modelling_start
    history = history.loc[history.date.ge(history.sku.map(starts))]
    # Only retain dates that can enter a supported issue's historical inputs.
    history = history.loc[history.date.ge(pd.Timestamp(origins[0]) - pd.Timedelta(days=56)) & history.date.lt(origins[-1])]
    lookup = {}
    for sku, group in history.groupby("sku"):
        series = group.set_index("date").sales_units.sort_index()
        for origin in origins:
            dates = pd.date_range(pd.Timestamp(origin) - pd.Timedelta(days=56), periods=56)
            ensure(series.reindex(dates).notna().all(), "required_history")
        series.to_numpy().setflags(write=False)
        lookup[sku] = series
    return InferenceEngine(MappingProxyType(lookup), quantiles, skus, tuple(date.fromisoformat(s) for s in origins),
        contract["forecast_release_id"], contract["calibration_id"])
