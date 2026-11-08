"""Bounded official-source acquisition with immutable-file checks and provenance."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
from urllib.request import Request, urlopen
import zipfile

SOURCE_URL = "https://archive.ics.uci.edu/static/public/502/online%2Bretail%2Bii.zip"
SOURCE_PAGE = "https://archive.ics.uci.edu/dataset/502/online+retail+ii"
MAX_BYTES = 75 * 1024 * 1024


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def acquire(root: Path) -> dict:
    """Download once, retain ZIP and unchanged workbook; verify on repeat runs."""
    raw = root / "data/raw"
    raw.mkdir(parents=True, exist_ok=True)
    manifest_path = root / "docs/data-provenance.json"
    archive = raw / "online_retail_ii.zip"
    workbook = raw / "online_retail_II.xlsx"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for key, path in (("archive", archive), ("workbook", workbook)):
            if not path.exists() or sha256(path) != manifest[key]["sha256"]:
                raise ValueError(f"Missing or changed raw {key}; refusing to overwrite.")
        print("Existing source files match provenance; no download needed.", flush=True)
        return manifest
    if archive.exists() or workbook.exists():
        raise ValueError("Unmanifested raw files exist; refusing to replace them.")

    request = Request(SOURCE_URL, headers={"User-Agent": "RetailForecastingPortfolio/0.1"})
    partial = archive.with_suffix(".zip.part")
    with urlopen(request, timeout=120) as response:
        advertised = response.headers.get("Content-Length")
        if advertised and int(advertised) > MAX_BYTES:
            raise ValueError("Source exceeds the 75 MiB acquisition cap.")
        count = 0
        with partial.open("wb") as destination:
            while block := response.read(1024 * 1024):
                count += len(block)
                if count > MAX_BYTES:
                    raise ValueError("Source exceeds the 75 MiB acquisition cap.")
                destination.write(block)
        if advertised and int(advertised) != count:
            raise ValueError("Incomplete download: Content-Length does not match.")
        resolved = response.url
        headers = {k: response.headers.get(k) for k in ("Content-Type", "ETag", "Last-Modified")}
    # The archive and extracted workbook are never opened for modification later.
    with zipfile.ZipFile(partial) as zipped:
        members = [item for item in zipped.infolist() if item.filename.lower().endswith(".xlsx")]
        if len(members) != 1 or members[0].file_size > MAX_BYTES:
            raise ValueError("Expected exactly one bounded workbook in the archive.")
        member = members[0]
        with zipped.open(member) as source, workbook.open("xb") as destination:
            shutil.copyfileobj(source, destination)
        if workbook.stat().st_size != member.file_size:
            raise ValueError("Extracted workbook size mismatch.")
    partial.rename(archive)
    manifest = {
        "dataset": "UCI Online Retail II", "author": "Daqing Chen",
        "citation": "Chen, D. (2012). Online Retail II. UCI Machine Learning Repository.",
        "doi": "https://doi.org/10.24432/C5CG6D",
        "license": "CC BY 4.0", "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "source_page": SOURCE_PAGE, "source_url": SOURCE_URL, "resolved_url": resolved,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "http_headers": headers,
        "archive": {"path": archive.relative_to(root).as_posix(), "bytes": archive.stat().st_size,
                    "sha256": sha256(archive)},
        "workbook": {"path": workbook.relative_to(root).as_posix(), "archive_member": member.filename,
                     "bytes": workbook.stat().st_size, "sha256": sha256(workbook)},
        "transformation": "Workbook extracted byte-for-byte from ZIP; no workbook edits.",
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2), flush=True)
    return manifest
