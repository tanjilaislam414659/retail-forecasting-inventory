"""Explicit copy-only export before container startup; no artifact regeneration."""

import argparse
import json
from pathlib import Path

from retail_forecasting.deployment.bundle import export_bundle


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Copy and validate only existing runtime artifacts")
    parser.add_argument("--source-root", type=Path, default=root)
    parser.add_argument("--output", type=Path, default=root / "artifacts/runtime/milestone-9-v0.1.0")
    args = parser.parse_args()
    record = export_bundle(args.source_root, args.output)
    print(json.dumps({"status": "verified byte-preserved runtime bundle", "path": str(args.output.resolve()),
        "files": len(record["files"]), "member_bytes": record["total_member_bytes"]}, indent=2))


if __name__ == "__main__":
    main()
