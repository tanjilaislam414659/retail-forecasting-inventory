"""Run the explicit synthetic suite; failures, skips and zero tests are errors."""

import argparse
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", choices=("runtime", "demo"), default="runtime")
    args = parser.parse_args()
    modules = ["ci.test_inference", "ci.test_api", "ci.test_bundle"]
    if args.package == "demo":
        modules.append("ci.test_demo")
    suite = unittest.defaultTestLoader.loadTestsFromNames(modules)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    required = 24 if args.package == "demo" else 16
    if result.testsRun < required or result.skipped or not result.wasSuccessful():
        raise SystemExit("Required synthetic CI suite failed, skipped tests, or discovered too few tests")
    print(f"PASS: {result.testsRun} explicitly synthetic {args.package} unit/API/packaging tests; zero skips. Full-data integration is a separate command.")


if __name__ == "__main__":
    main()
