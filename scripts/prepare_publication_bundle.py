"""Create a local attributed ZIP from existing verified runtime bytes; no rebuild."""

import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

from retail_forecasting.deployment.bundle import verify_bundle


def main():
    root = Path(__file__).resolve().parents[1]
    source = root / "artifacts/runtime/milestone-9-v0.1.0"
    manifest = verify_bundle(source)
    output = root / "artifacts/publication"
    output.mkdir(parents=True, exist_ok=True)
    target = output / "retail-forecasting-runtime-v0.1.0.zip"
    names = sorted([*manifest["files"], "bundle-manifest.json"])
    assert len(names) == 17 and "DATASET-ATTRIBUTION.md" in names
    csv_headers = {}
    for name in names:
        if name.endswith((".csv", ".csv.gz")):
            blob = (source / name).read_bytes()
            if name.endswith(".gz"):
                blob = gzip.decompress(blob)
            headers = next(csv.reader(io.StringIO(blob.decode("utf-8-sig"))))
            assert not any(key.lower().replace(" ", "").replace("_", "") in {"customerid", "email", "address", "invoiceno", "invoice"} for key in headers), name
            csv_headers[name] = headers
    # Never overwrite an earlier candidate attachment.
    with ZipFile(target, "x", compression=ZIP_DEFLATED) as archive:
        for name in names:
            info = ZipInfo("milestone-9-v0.1.0/" + name, date_time=(2000, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, (source / name).read_bytes())
    with ZipFile(target) as archive:
        for name in names:
            assert archive.read("milestone-9-v0.1.0/" + name) == (source / name).read_bytes()
    record = {"status": "prepared locally, not published", "zip": target.relative_to(root).as_posix(),
        "bytes": target.stat().st_size, "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "members": len(names), "original_member_bytes": manifest["total_member_bytes"],
        "source_bundle_manifest_sha256": hashlib.sha256((source / "bundle-manifest.json").read_bytes()).hexdigest(),
        "csv_headers_reviewed": csv_headers, "raw_workbook_customer_records_saved_forecasts_included": False,
        "attribution": "Chen, D. (2012), UCI Online Retail II, CC BY 4.0; transformations and provenance inside bundle"}
    with (output / "runtime-bundle.json").open("x", encoding="utf-8") as stream:
        json.dump(record, stream, indent=2)
        stream.write("\n")
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
