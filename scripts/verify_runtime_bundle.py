"""Full-data host integration of portable bundle; not container/performance eval."""

from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import tempfile
import time

from fastapi.testclient import TestClient
import numpy as np

from retail_forecasting.deployment.bundle import digest, export_bundle, load_runtime_engine, verify_bundle
from retail_forecasting.final_evaluation import verify_existing
from retail_forecasting.service.app import create_app
from retail_forecasting.service.artifacts import load_engine


def main():
    root = Path(__file__).resolve().parents[1]
    bundle = root / "artifacts/runtime/milestone-9-v0.1.0"
    verify_existing(root)
    manifest = verify_bundle(bundle)
    before = digest((bundle / "bundle-manifest.json").read_bytes())
    export_bundle(root, bundle)
    assert before == digest((bundle / "bundle-manifest.json").read_bytes())
    reference = load_engine(root)
    max_difference = 0.
    checked = 0
    started = time.perf_counter()
    with TestClient(create_app(bundle, loader=load_runtime_engine)) as client:
        assert client.get("/health").status_code == client.get("/ready").status_code == 200
        metadata = client.get("/metadata").json()
        assert len(metadata["supported_skus"]) == 100 and len(metadata["supported_origins"]) == 20
        startup_ms = client.get("/ready").json()["startup_ms"]
        for sku in ("21212", "21166", "21533"):
            for origin in (reference.origins[0], reference.origins[-1]):
                response = client.post("/forecast", json={"sku": sku, "origin": origin.isoformat()})
                assert response.status_code == 200
                observed = response.json()
                expected = reference.predict(sku, origin).model_dump(mode="json")
                assert set(observed) == set(expected)
                for got, want in zip(observed["predictions"], expected["predictions"]):
                    assert got["target_date"] == want["target_date"] and got["horizon_day"] == want["horizon_day"]
                    actual_numbers = [got["predicted_sales"]] + [got[f"interval_{level}"][endpoint] for level in (80, 95) for endpoint in ("lower", "upper")]
                    reference_numbers = [want["predicted_sales"]] + [want[f"interval_{level}"][endpoint] for level in (80, 95) for endpoint in ("lower", "upper")]
                    np.testing.assert_allclose(actual_numbers, reference_numbers, rtol=1e-12, atol=1e-9)
                    max_difference = max(max_difference, float(np.max(np.abs(np.array(actual_numbers) - reference_numbers))))
                checked += 1
        assert client.post("/forecast", json={"sku": "unknown", "origin": "2011-11-07"}).status_code == 422
    cache = root / ".cache"
    failures = {}
    contract = json.loads((bundle / "service/artifact-contract.json").read_text())
    for kind in ("missing", "corrupt"):
        with tempfile.TemporaryDirectory(prefix="runtime-fixture-", dir=cache) as directory:
            fixture = Path(directory) / "bundle"
            shutil.copytree(bundle, fixture)
            calibration = fixture / contract["artifacts"]["quantiles"]["path"]
            if kind == "missing":
                calibration.unlink()
            else:
                calibration.write_bytes(b"deliberately corrupt local integration fixture")
            with TestClient(create_app(fixture, loader=load_runtime_engine)) as client:
                assert client.get("/health").status_code == 200
                ready = client.get("/ready")
                assert ready.status_code == 503
                assert client.post("/forecast", json={"sku": "21212", "origin": "2011-11-07"}).status_code == 503
                failures[kind] = ready.json()["error_code"]
    verify_existing(root)
    output = root / "reports/generated/deployment" / ("bundle-integration-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    output.mkdir(parents=True, exist_ok=False)
    report = {"status": "PASS", "scope": "Host in-process HTTP with exported runtime bundle; not Docker execution or new forecast performance evaluation",
        "bundle_files_excluding_manifest": len(manifest["files"]), "member_bytes": manifest["total_member_bytes"],
        "source_and_installed_code_hash_checks": "PASS", "copy_only_export_idempotence": "PASS",
        "parity_cases": checked, "dated_predictions": checked * 28, "max_absolute_numeric_difference": max_difference,
        "relative_tolerance": 1e-12, "absolute_tolerance": 1e-9, "missing_corrupt_readiness": failures,
        "host_artifact_load_ms": startup_ms, "wall_seconds": time.perf_counter() - started,
        "frozen_research_and_final_evaluation_unchanged": True}
    (output / "integration.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"Saved {output}")


if __name__ == "__main__":
    main()
