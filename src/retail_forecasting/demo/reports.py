"""Load hash-verified saved reports once; failure is isolated to each report."""

import hashlib
import json
from pathlib import Path


def load_reports(directory: Path):
    names = ("validation", "final-test", "inventory")
    unavailable = lambda code: {"status": "unavailable", "code": code,
        "message": "Saved reporting artifacts are unavailable or invalid. Restore the packaged files and restart; no results are regenerated."}
    try:
        manifest = json.loads((directory / "manifest.json").read_bytes())
        if manifest["report_version"] != "0.1.0":
            raise ValueError("Unsupported reports")
    except (OSError, ValueError, KeyError, TypeError):
        return {name: unavailable("invalid_or_missing_report_manifest") for name in names}
    output = {}
    for name in names:
        try:
            raw = (directory / (name + ".json")).read_bytes()
            expected = manifest["payloads"][name + ".json"]
            if hashlib.sha256(raw).hexdigest() != expected["sha256"] or len(raw) != expected["bytes"]:
                raise ValueError("Checksum mismatch")
            payload = json.loads(raw)
            output[name] = {"status": "available", "data": payload}
        except (OSError, ValueError, KeyError, TypeError):
            output[name] = unavailable("invalid_or_missing_report")
    return output
