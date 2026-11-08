"""Verify README Compose commands from a prepared clean checkout; stop afterward."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import time

import httpx
import numpy as np
from retail_forecasting.service.artifacts import load_engine


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    checkout = args.checkout.resolve()
    assert checkout.is_relative_to(root / ".cache") and (checkout / ".git").exists()
    assert (checkout / "artifacts/runtime/milestone-9-v0.1.0/bundle-manifest.json").is_file()
    docker = shutil.which("docker")
    if not docker:
        raise RuntimeError("Docker CLI is unavailable; execution cannot be claimed")
    output = root / "reports/generated/publication" / ("docker-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    output.mkdir(parents=True, exist_ok=False)
    prefix = [docker, "compose", "-f", "demo/compose.yaml", "-f", "publication/compose.yaml", "--project-name", "retail-portfolio-clean"]
    operations = []
    with (output / "commands.log").open("x", encoding="utf-8") as log:
        def command(arguments):
            result = subprocess.run([str(p) for p in arguments], cwd=checkout, capture_output=True, text=True, encoding="utf-8", errors="replace")
            log.write(result.stdout + result.stderr); log.flush()
            operations.append({"arguments": [str(p) for p in arguments[1:]], "exit_code": result.returncode})
            if result.returncode:
                raise RuntimeError("Docker check failed; inspect commands.log")
            return result.stdout
        try:
            command([*prefix, "config"])
            command([*prefix, "build"])
            started = time.perf_counter()
            command([*prefix, "up", "-d", "--wait", "--wait-timeout", "90", "--no-build"])
            startup_ms = (time.perf_counter() - started) * 1000
            container = command([*prefix, "ps", "-q", "demo"]).strip()
            info = json.loads(command([docker, "inspect", container]))[0]
            image = json.loads(command([docker, "image", "inspect", "retail-forecasting-portfolio:0.1.0"]))[0]
            assert info["Config"]["User"] == "10001:10001"
            assert info["HostConfig"]["ReadonlyRootfs"]
            assert all(not row["RW"] for row in info["Mounts"] if row["Destination"] == "/runtime")
            assert info["HostConfig"]["PortBindings"]["8000/tcp"] == [{"HostIp": "127.0.0.1", "HostPort": "8000"}]
            reference = load_engine(root)
            difference, cases = 0.0, 0
            with httpx.Client(base_url="http://127.0.0.1:8000", trust_env=False, timeout=10) as client:
                for path in ("/", "/health", "/ready", "/metadata", "/docs", "/demo/assets/app.js", "/demo/assets/style.css", "/demo/api/evaluation", "/demo/api/inventory"):
                    assert client.get(path).status_code == 200, path
                assert "Overall coverage hides uneven performance" in client.get("/demo/assets/app.js").text
                ready = client.get("/ready").json()
                for sku in ("21212", "21166", "21533"):
                    for origin in (reference.origins[0], reference.origins[-1]):
                        response = client.post("/forecast", json={"sku": sku, "origin": origin.isoformat()})
                        assert response.status_code == 200
                        expected = reference.predict(sku, origin).model_dump(mode="json")
                        for actual, want in zip(response.json()["predictions"], expected["predictions"]):
                            assert actual["target_date"] == want["target_date"]
                            a = [actual["predicted_sales"]] + [actual[f"interval_{level}"][end] for level in (80, 95) for end in ("lower", "upper")]
                            b = [want["predicted_sales"]] + [want[f"interval_{level}"][end] for level in (80, 95) for end in ("lower", "upper")]
                            np.testing.assert_allclose(a, b, rtol=1e-12, atol=1e-9)
                            difference = max(difference, float(np.max(np.abs(np.array(a) - b))))
                        cases += 1
                assert client.post("/forecast", json={"sku": "unknown", "origin": "2011-11-07"}).status_code == 422
            record = {"status": "PASS", "checkout": str(checkout), "image_id": image["Id"], "image_size_bytes": image["Size"],
                "compose_up_to_healthy_ms": startup_ms, "ready": ready, "non_root_readonly_loopback": True,
                "parity_cases": cases, "dated_predictions": cases * 28, "numeric_values": cases * 28 * 5,
                "maximum_absolute_difference": difference, "rtol": 1e-12, "atol": 1e-9,
                "scope": "Clean-checkout Docker engineering/inference regression, no scoring, experiments or publication"}
        finally:
            command([*prefix, "down"])
        record["stopped_after_check"] = True
        record["operations"] = operations
        (output / "results.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in record.items() if k != "operations"}, indent=2))
    print("Evidence:", output)


if __name__ == "__main__":
    main()
