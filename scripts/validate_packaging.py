"""Static YAML/Docker/package checks; not Docker execution or hosted Actions."""

import json
from pathlib import Path
import re
import tomllib

import yaml


def main():
    root = Path(__file__).resolve().parents[1]
    compose = yaml.safe_load((root / "compose.yaml").read_text())
    service = compose["services"]["forecast"]
    assert service["ports"] == ["127.0.0.1:8000:8000"]
    assert service["platform"] == "linux/amd64" and service["read_only"] is True
    assert len(service["volumes"]) == 1
    mount = service["volumes"][0]
    assert mount["target"] == "/runtime" and mount["read_only"] is True
    assert mount["bind"]["create_host_path"] is False
    dockerfile = (root / "Dockerfile").read_text()
    image = json.loads((root / "deployment/base-image.json").read_text())
    expected = "python:" + image["resolved_version_tag"] + "@" + image["index_digest"]
    assert len(re.findall(r"^FROM " + re.escape(expected) + r" AS \w+$", dockerfile, flags=re.M)) == 2
    assert "USER 10001:10001" in dockerfile and "retail_forecasting.deployment.healthcheck" in dockerfile
    assert '--host", "0.0.0.0"' in dockerfile and "--require-hashes" in dockerfile
    assert "COPY . " not in dockerfile and "COPY data" not in dockerfile
    ignore = (root / ".dockerignore").read_text().splitlines()
    assert "**" in ignore and not any(line.startswith(("!data", "!artifacts", "!.venv", "!.env", "!reports")) for line in ignore)
    workflow = yaml.load((root / ".github/workflows/ci.yml").read_text(), Loader=yaml.BaseLoader)
    assert set(workflow["on"]) == {"push", "pull_request", "workflow_dispatch"}
    assert workflow["permissions"] == {"contents": "read"}
    steps = workflow["jobs"]["synthetic-tests-and-package"]["steps"]
    assert set(workflow["jobs"]["synthetic-tests-and-package"]["strategy"]["matrix"]["package"]) == {"runtime", "demo"}
    for step in steps:
        if "uses" in step:
            assert re.fullmatch(r"actions/[a-z-]+@[0-9a-f]{40}", step["uses"])
        assert "continue-on-error" not in step
    commands = "\n".join(step.get("run", "") for step in steps)
    for command in ("ci/run_tests.py", "build_runtime_package.py", "build_demo_package.py", "pip install --no-deps", "ci/check_installed_package.py", "ci/check_installed_demo.py"):
        assert command in commands
    for forbidden in ("scripts/verify_service_parity.py", "scripts/export_runtime_bundle.py", "-m retail_forecasting final-evaluation", "acquire", "ridge", "boosting"):
        assert forbidden not in commands
    package = tomllib.loads((root / "packaging/runtime/pyproject.toml").read_text())
    assert package["project"]["name"] == "retail-forecasting-runtime"
    for scope in ("runtime", "build", "ci"):
        rows = (root / f"deployment/requirements-{scope}-linux.lock").read_text().splitlines()
        required = [line for line in rows if line and not line.startswith("#")]
        assert required and all(re.fullmatch(r"[\w.-]+==[\w.]+ --hash=sha256:[0-9a-f]{64}", line) for line in required)
    print("PASS: static Compose/Workflow YAML, pinned image/action/dependency identities, non-root/read-only/readiness settings, restricted build context and routine-CI scope. Docker/Actions execution not asserted.")


if __name__ == "__main__":
    main()
