"""Verify actual Compose health, UID, read-only mounts and loopback publication."""

from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import time
from uuid import uuid4

import httpx
import numpy as np


def main():
    root = Path(__file__).resolve().parents[1]
    docker = shutil.which("docker") or r"C:\Program Files\Docker\Docker\resources\bin\docker.exe"
    project = "retail-forecasting-verification-" + uuid4().hex[:10]
    output = root / "reports/generated/deployment" / ("compose-check-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    output.mkdir(parents=True, exist_ok=False)
    prefix = ["compose", "--project-name", project]
    with (output / "commands.log").open("x", encoding="utf-8") as log:
        def command(arguments):
            result = subprocess.run([docker] + arguments, cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace")
            log.write(result.stdout + result.stderr)
            log.flush()
            if result.returncode:
                raise RuntimeError("Compose verification failed; inspect saved commands.log")
            return result.stdout.strip()

        started = time.perf_counter()
        stopped = False
        try:
            config = json.loads(command(prefix + ["config", "--format", "json"]))
            assert config["services"]["forecast"]["ports"][0]["host_ip"] == "127.0.0.1"
            command(prefix + ["up", "--detach", "--wait", "--wait-timeout", "90", "--no-build"])
            startup_ms = (time.perf_counter() - started) * 1000
            container = command(prefix + ["ps", "--quiet", "forecast"])
            info = json.loads(command(["inspect", container]))[0]
            image = json.loads(command(["image", "inspect", info["Image"]]))[0]
            assert info["State"]["Health"]["Status"] == "healthy"
            assert info["HostConfig"]["ReadonlyRootfs"] is True
            mounts = [m for m in info["Mounts"] if m["Destination"] == "/runtime"]
            assert len(mounts) == 1 and mounts[0]["Type"] == "bind" and mounts[0]["RW"] is False
            assert info["Config"]["User"] == "10001:10001"
            ports = info["NetworkSettings"]["Ports"]["8000/tcp"]
            assert all(p["HostIp"] == "127.0.0.1" for p in ports)
            assert "0.0.0.0" in info["Config"]["Cmd"]
            probe = """import errno,json,os
from pathlib import Path
result={'uid':os.geteuid(),'gid':os.getegid(),'writes':{}}
assert result['uid']==10001 and result['gid']==10001
for directory in ['/runtime','/app']:
    path=Path(directory)/'.milestone9-readonly-probe'
    try:
        with path.open('x') as stream: stream.write('probe')
    except OSError as exc:
        assert exc.errno==errno.EROFS,(directory,exc.errno)
        result['writes'][directory]={'denied':True,'errno':exc.errno}
    else:
        path.unlink()
        raise AssertionError('Unexpected writable filesystem: '+directory)
print(json.dumps(result))
"""
            permissions = json.loads(command(["exec", container, "python", "-c", probe]))
            with httpx.Client(base_url="http://127.0.0.1:" + ports[0]["HostPort"], timeout=5, trust_env=False) as client:
                health, ready, metadata = [client.get(path) for path in ("/health", "/ready", "/metadata")]
                assert health.status_code == ready.status_code == metadata.status_code == 200
                assert len(metadata.json()["supported_skus"]) == 100 and len(metadata.json()["supported_origins"]) == 20
                payload = {"sku": "21212", "origin": "2011-11-07", "horizon_days": 28}
                latencies = []
                for _ in range(20):
                    before = time.perf_counter()
                    response = client.post("/forecast", json=payload)
                    assert response.status_code == 200 and len(response.json()["predictions"]) == 28
                    latencies.append((time.perf_counter() - before) * 1000)
                assert client.post("/forecast", json={**payload, "unexpected": True}).status_code == 422
                example = response.json()
                (output / "example-response.json").write_text(json.dumps(example, indent=2) + "\n", encoding="utf-8")
            report = {"status": "PASS", "scope": "Actual Linux Docker Compose runtime verification",
                "image_id": info["Image"], "image_size_bytes": image["Size"], "container_health": "healthy",
                "runtime_identity": permissions, "artifact_mount_type": "bind", "artifact_mount_read_only": True,
                "root_filesystem_read_only": True, "host_bindings": ports, "internal_host": "0.0.0.0",
                "compose_start_to_healthy_ms": startup_ms, "artifact_load_ms": ready.json()["startup_ms"],
                "warm_http_samples": 20, "warm_http_median_ms": float(np.median(latencies)),
                "warm_http_p95_ms": float(np.quantile(latencies, .95)), "invalid_request_status": 422,
                "hosted_actions": "PENDING"}
        finally:
            command(prefix + ["down"])
            stopped = not command(["ps", "--all", "--quiet", "--filter", "label=com.docker.compose.project=" + project])
        assert stopped
        report["containers_stopped_and_removed"] = True
        (output / "compose.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2), flush=True)
        print(f"Saved {output}", flush=True)


if __name__ == "__main__":
    main()
