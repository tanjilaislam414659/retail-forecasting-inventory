"""Verify installed demo wheel assets/code identities without research data."""

import hashlib
from importlib.metadata import distribution
import importlib
import json
from pathlib import Path

import retail_forecasting
from retail_forecasting.demo import __version__


def main():
    root = Path(__file__).resolve().parents[1]
    assert not Path(retail_forecasting.__file__).resolve().is_relative_to(root / "src"), "Testing checkout imports instead of installed demo"
    package = distribution("retail-forecasting-demo")
    assert package.version == __version__ == "0.1.0"
    files = {str(path).replace("\\", "/") for path in package.files}
    for filename in ("app.js", "style.css", "index.html"):
        assert "retail_forecasting/demo/static/" + filename in files
    assert not any(name.endswith(("preparation.py", "final_evaluation.py", ".xlsx", ".csv.gz")) for name in files)
    from retail_forecasting.demo import app
    folder = Path(app.__file__).with_name("reports")
    manifest = json.loads((folder / "manifest.json").read_bytes())
    for name, entry in manifest["payloads"].items():
        raw = (folder / name).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == entry["sha256"] and len(raw) == entry["bytes"]
    from retail_forecasting.deployment import bundle
    identities = json.loads(Path(bundle.__file__).with_name("runtime-code.json").read_bytes())
    for name, expected in identities["installed_module_sha256"].items():
        assert hashlib.sha256(Path(importlib.import_module(name).__file__).read_bytes()).hexdigest() == expected
    print("PASS: installed demo wheel, static/report assets, frozen inference identities; no research data or experiment modules")


if __name__ == "__main__":
    main()
