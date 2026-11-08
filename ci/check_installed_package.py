"""Assert that CI exercises the installed minimal wheel, not checkout imports."""

from importlib.metadata import distribution
import hashlib
import importlib
import json
from pathlib import Path

import retail_forecasting
from retail_forecasting.deployment import __version__


def main():
    root = Path(__file__).resolve().parents[1]
    assert not Path(retail_forecasting.__file__).resolve().is_relative_to(root / "src"), "Testing checkout imports instead of installed wheel"
    package = distribution("retail-forecasting-runtime")
    assert package.version == __version__ == "0.1.0"
    files = {str(path).replace("\\", "/") for path in package.files}
    assert "retail_forecasting/baselines.py" in files
    assert "retail_forecasting/deployment/runtime-code.json" in files
    assert not any(name.endswith(("ridge_experiment.py", "preparation.py", "final_evaluation.py")) for name in files)
    assert not any("data/processed" in name or name.endswith((".xlsx", ".xls", ".csv.gz")) for name in files)
    from retail_forecasting.deployment import bundle
    identities = json.loads(Path(bundle.__file__).with_name("runtime-code.json").read_bytes())
    for name, expected in identities["installed_module_sha256"].items():
        module = importlib.import_module(name)
        assert hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest() == expected, name
    print("PASS: installed runtime wheel 0.1.0, curated inference/API modules, no research experiments or data files.")


if __name__ == "__main__":
    main()
