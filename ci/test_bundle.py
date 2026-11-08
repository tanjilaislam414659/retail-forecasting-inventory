"""Small synthetic envelope tests; native 100-SKU loading remains integration."""

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from retail_forecasting.deployment.bundle import local_path, verify_bundle
from retail_forecasting.service.artifacts import ArtifactError


class BundleIntegrityTests(unittest.TestCase):
    def fixture(self, root):
        files = {"service/artifact-contract.json": json.dumps({"artifacts": {"synthetic": {"path": "fixture.txt"}}}).encode(),
            "fixture.txt": b"SYNTHETIC ONLY, NOT RETAIL DATA", "provenance/data-provenance.json": b'{"synthetic":true}',
            "DATASET-ATTRIBUTION.md": b"Synthetic fixture has no real dataset"}
        records = {}
        for name, blob in files.items():
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(blob)
            records[name] = {"sha256": hashlib.sha256(blob).hexdigest(), "bytes": len(blob)}
        manifest = {"runtime_version": "0.1.0", "files": records,
            "source_contract_sha256": hashlib.sha256(files["service/artifact-contract.json"]).hexdigest()}
        (root / "bundle-manifest.json").write_text(json.dumps(manifest))
        return manifest

    def test_synthetic_envelope_integrity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            expected = self.fixture(root)
            self.assertEqual(verify_bundle(root), expected)

    def test_missing_and_corrupt_bundle_members_fail(self):
        for missing in (True, False):
            with self.subTest(missing=missing), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.fixture(root)
                if missing:
                    (root / "fixture.txt").unlink()
                else:
                    (root / "fixture.txt").write_bytes(b"CORRUPT")
                with self.assertRaises(ArtifactError) as caught:
                    verify_bundle(root)
                self.assertEqual(caught.exception.code, "missing_artifact" if missing else "checksum_mismatch")

    def test_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ArtifactError):
                local_path(Path(directory), "../outside")
