"""Copy verified frozen source/config bytes without touching evaluation artifacts."""

import json
from pathlib import Path

from retail_forecasting.acquisition import sha256
from retail_forecasting.final_evaluation import verify_existing


def main():
    root = Path(__file__).resolve().parents[1]
    verify_existing(root)  # integrity only; no evaluation
    freeze_path = root / "data/final_evaluation/freeze.json"
    freeze = json.loads(freeze_path.read_text())
    tag = "milestone-7-" + sha256(freeze_path)[:12]
    output = root / "artifacts/frozen-release" / tag
    if output.exists():
        record = json.loads((output / "snapshot-manifest.json").read_text())
        for name, digest in record["copied_sha256"].items():
            assert sha256(output / name) == digest, name
        print(f"Existing {tag} snapshot verified; no overwrite.")
        return
    paths = [name for name in freeze["sha256"] if not name.startswith(("data/", "models/", "reports/"))]
    paths += ["data/final_evaluation/freeze.json", "data/final_evaluation/manifest.json",
        "docs/final-evaluation-report.md", "docs/final-evaluation-verification.md",
        "scripts/validate_final_evaluation_v2.py",
        "data/final_evaluation_corrections/001-validator-csv-roundtrip/manifest.json"]
    output.mkdir(parents=True, exist_ok=False)
    copied = {}
    for name in sorted(set(paths)):
        source, target = root / name, output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(source.read_bytes())
        copied[name] = sha256(target)
        assert copied[name] == sha256(source)
    with (output / "snapshot-manifest.json").open("x", encoding="utf-8") as stream:
        json.dump({"release_snapshot": tag, "freeze_sha256": sha256(freeze_path),
            "original_evaluation_manifest_sha256": sha256(root / "data/final_evaluation/manifest.json"),
            "copied_sha256": copied, "note": "Byte-preserved code/config/docs snapshot; original evaluation datasets/artifacts remain in place unchanged."}, stream, indent=2)
        stream.write("\n")
    print(f"Preserved {len(copied)} frozen source/config/provenance files at {output}.")


if __name__ == "__main__":
    main()
