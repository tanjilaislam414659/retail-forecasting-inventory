"""Small synthetic ZIPs exercise acquisition without contacting UCI."""

import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import zipfile

from retail_forecasting.acquisition import MAX_BYTES, acquire


class AcquisitionTests(unittest.TestCase):
    def setUp(self):
        cache = Path(__file__).resolve().parents[1] / ".cache"
        cache.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="acquisition-test-", dir=cache)
        self.root = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)

    def response(self, content: bytes):
        response = MagicMock()
        response.__enter__.return_value = response
        response.headers = {"Content-Length": str(len(content))}
        response.url = "https://archive.ics.uci.edu/test-fixture"
        response.read.side_effect = io.BytesIO(content).read
        return response

    @patch("retail_forecasting.acquisition.urlopen")
    def test_extract_is_byte_preserving_idempotent_and_tamper_detecting(self, urlopen):
        workbook = b"synthetic workbook payload; not real retail data"
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as zipped:
            zipped.writestr("online_retail_II.xlsx", workbook)
        urlopen.return_value = self.response(archive.getvalue())
        manifest = acquire(self.root)
        self.assertEqual(manifest["workbook"]["bytes"], len(workbook))
        self.assertEqual(manifest["workbook"]["sha256"], hashlib.sha256(workbook).hexdigest())
        self.assertEqual((self.root / manifest["workbook"]["path"]).read_bytes(), workbook)
        self.assertEqual(acquire(self.root), manifest)
        self.assertEqual(urlopen.call_count, 1)
        (self.root / manifest["workbook"]["path"]).write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "changed raw"):
            acquire(self.root)

    @patch("retail_forecasting.acquisition.urlopen")
    def test_refuses_advertised_oversize_download(self, urlopen):
        response = self.response(b"")
        response.headers["Content-Length"] = str(MAX_BYTES + 1)
        urlopen.return_value = response
        with self.assertRaisesRegex(ValueError, "75 MiB"):
            acquire(self.root)
        response.read.assert_not_called()

    @patch("retail_forecasting.acquisition.urlopen")
    def test_does_not_replace_unmanifested_raw_file(self, urlopen):
        raw = self.root / "data/raw"
        raw.mkdir(parents=True)
        path = raw / "online_retail_II.xlsx"
        path.write_bytes(b"existing user file")
        with self.assertRaisesRegex(ValueError, "refusing to replace"):
            acquire(self.root)
        self.assertEqual(path.read_bytes(), b"existing user file")
        urlopen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
