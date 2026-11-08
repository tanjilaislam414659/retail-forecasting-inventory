"""Offline Git content/history and README-link audit; never prints secret values."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess


def git(root, *args, data=None):
    return subprocess.check_output(["git", *args], cwd=root, input=data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    objects = {}
    for line in git(root, "rev-list", "--objects", "--all").decode().splitlines():
        oid, _, name = line.partition(" ")
        objects[oid] = name
    process = subprocess.Popen(["git", "cat-file", "--batch"], cwd=root, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    rules = {
        "private_key": rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
        "github_token": rb"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})",
        "aws_access_id": rb"AKIA[A-Z0-9]{16}",
        "google_api_key": rb"AIza[A-Za-z0-9_-]{30,}",
        "slack_token": rb"xox[baprs]-[A-Za-z0-9-]{20,}",
        "credential_url": rb"https?://[^\s/:]+:[^\s/@]+@",
    }
    findings, reviewed_literals, denied_paths, local_path_blobs, blobs, total_bytes = [], [], [], [], 0, 0
    reviewed = {("ci/test_api.py", "f86c480065748b64dc7ead7b2354b5bcbd416d803d497212fa4e15f15b57ef7a"):
        "Reviewed handcrafted SECRET-body placeholder in rejected-request logging test; not a real credential"}
    allowed_csv = {"ci/fixtures/history.csv", "ci/fixtures/quantiles.csv"}
    for oid, name in objects.items():
        process.stdin.write((oid + "\n").encode()); process.stdin.flush()
        header = process.stdout.readline().decode().split()
        size = int(header[2]); blob = process.stdout.read(size); process.stdout.read(1)
        if header[1] != "blob":
            continue
        blobs += 1; total_bytes += size
        parts = PurePosixPath(name).parts
        forbidden = any(p in {".venv", ".codex", ".agents", ".aws", "__pycache__", "node_modules"} for p in parts)
        forbidden |= name.endswith((".xlsx", ".xls", ".parquet", ".pkl", ".joblib", ".pem", ".key", ".csv.gz"))
        forbidden |= bool(parts and parts[0] in {"artifacts", "models"})
        forbidden |= name.endswith(".csv") and name not in allowed_csv
        forbidden |= PurePosixPath(name).name == ".env"
        if forbidden:
            denied_paths.append({"object": oid, "path": name})
        if b"\x00" in blob or name.lower().endswith((".jpg", ".png")):
            continue
        for label, pattern in rules.items():
            if re.search(pattern, blob):
                findings.append({"object": oid, "path": name, "rule": label})
        assignments = re.finditer(rb'''(?i)\b(?:password|api[_-]?key|secret|access[_-]?token)\b["']?\s*[:=]\s*["']([^"'\r\n]{8,})''', blob)
        for match in assignments:
            value = match.group(1)
            fingerprint = hashlib.sha256(value).hexdigest()
            if (name, fingerprint) in reviewed:
                reviewed_literals.append({"path": name, "object": oid, "value_sha256": fingerprint, "reason": reviewed[name, fingerprint]})
                continue
            if not re.search(rb"(?i)synthetic|fake|example|placeholder|test.only|test.secret|must.not.log", value):
                findings.append({"object": oid, "path": name, "rule": "credential_literal_review", "value_sha256": fingerprint})
        # Exact local interpreter paths in historical documentation are disclosed,
        # not treated as credentials. Do not print their usernames or values.
        if re.search(rb"[A-Za-z]:[\\/]Users[\\/][^\s'\"/\\]+", blob):
            local_path_blobs.append({"object": oid, "path": name})
    process.stdin.close(); process.wait()
    assert process.returncode == 0
    tracked = git(root, "ls-files", "-z").decode().split("\0")[:-1]
    for name in allowed_csv:
        import csv
        with (root / name).open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        assert rows and all(row["sku"].startswith("SYNTHETIC_") for row in rows)
        assert not any("customer" in field.lower() for field in rows[0])
    candidates = [".env", ".venv/test", ".codex/test", "data/raw/test.xlsx", "data/processed/customer.csv", "models/test.joblib", "artifacts/runtime/test", "reports/generated/test", ".cache/test"]
    ignored = git(root, "check-ignore", "--stdin", data=("\n".join(candidates) + "\n").encode()).decode().splitlines()
    assert set(ignored) == set(candidates), "Required exclusions are missing"
    broken = []
    for name in ["README.md", "publication/README.md", "publication/runtime-bundle.md", "publication/portfolio-copy.md", "publication/release-notes.md", "demo/README.md"]:
        file = root / name
        for target in re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", file.read_text(encoding="utf-8")):
            if "://" in target or target.startswith("#"):
                continue
            if not (file.parent / target.split("#")[0]).exists():
                broken.append({"file": name, "target": target})
    authors = git(root, "log", "--all", "--format=%ae").decode().splitlines()
    record = {"checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if not findings and not denied_paths and not broken else "REVIEW_REQUIRED",
        "commits": int(git(root, "rev-list", "--all", "--count")), "shallow": git(root, "rev-parse", "--is-shallow-repository").decode().strip(),
        "tracked_files": len(tracked), "unique_reachable_blobs": blobs, "reachable_blob_bytes": total_bytes,
        "secret_pattern_findings": findings, "forbidden_history_paths": denied_paths,
        "explicitly_reviewed_test_literals": reviewed_literals,
        "historical_local_path_blobs": local_path_blobs, "broken_document_links": broken,
        "required_ignore_examples_passed": len(candidates), "commit_author_emails_all_localhost": all(a.endswith("@localhost") for a in authors),
        "license_file_present": any(PurePosixPath(p).name.upper() in {"LICENSE", "LICENSE.MD", "LICENSE.TXT", "COPYING"} for p in tracked),
        "only_tracked_csv_schemas": "Explicit synthetic SKU histories and handcrafted quantiles; no customer identifiers",
        "limitations": "Heuristic secret-pattern/path audit of reachable Git history, plus schema/fixture review; not a proof that arbitrary encoded secrets cannot exist. Ignored personal files/credentials are not inspected. Working-copy additions must be committed before final audit."}
    output = args.output or root / "reports/generated/publication/git-audit.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in record.items() if k != "historical_local_path_blobs"}, indent=2))
    print("Historical local-path blob count:", len(local_path_blobs))
    if record["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
