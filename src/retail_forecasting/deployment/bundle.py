"""Export byte-preserved runtime inputs; verify mounted inputs and installed code."""

from datetime import datetime, timezone
import hashlib
import importlib
import json
from pathlib import Path

from retail_forecasting.deployment import __version__
from retail_forecasting.service.artifacts import ArtifactError, load_engine


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def local_path(root, name):
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ArtifactError("invalid_bundle_path", "bundle_manifest")
    return path


def verify_bundle(root):
    root = Path(root).resolve()
    try:
        manifest = json.loads((root / "bundle-manifest.json").read_bytes())
    except FileNotFoundError as exc:
        raise ArtifactError("missing_runtime_bundle", "bundle_manifest") from exc
    except (OSError, ValueError) as exc:
        raise ArtifactError("invalid_runtime_bundle", "bundle_manifest") from exc
    try:
        if manifest["runtime_version"] != __version__:
            raise ArtifactError("unsupported_runtime_bundle", "runtime_version")
        for name, entry in manifest["files"].items():
            path = local_path(root, name)
            try:
                blob = path.read_bytes()
            except FileNotFoundError as exc:
                raise ArtifactError("missing_artifact", "runtime_bundle_member") from exc
            if digest(blob) != entry["sha256"] or len(blob) != entry["bytes"]:
                raise ArtifactError("checksum_mismatch", "runtime_bundle_member")
        contract_blob = (root / "service/artifact-contract.json").read_bytes()
        contract = json.loads(contract_blob)
        expected = {entry["path"] for entry in contract["artifacts"].values()}
        expected |= {"service/artifact-contract.json", "provenance/data-provenance.json", "DATASET-ATTRIBUTION.md"}
        if set(manifest["files"]) != expected or digest(contract_blob) != manifest["source_contract_sha256"]:
            raise ArtifactError("invalid_runtime_bundle", "member_set_or_contract")
    except ArtifactError:
        raise
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise ArtifactError("invalid_runtime_bundle", "bundle_manifest") from exc
    return manifest


def export_bundle(source_root, destination):
    """Copy only pinned bytes; no acquisition, fitting or data preparation."""
    source_root, destination = Path(source_root).resolve(), Path(destination).resolve()
    load_engine(source_root)  # All existing native artifact checks, before export.
    contract_blob = (source_root / "service/artifact-contract.json").read_bytes()
    contract = json.loads(contract_blob)
    if destination.exists():
        manifest = verify_bundle(destination)
        if manifest["source_contract_sha256"] != digest(contract_blob):
            raise ValueError("Existing bundle belongs to a different contract")
        return manifest
    freeze = json.loads((source_root / contract["artifacts"]["release_freeze"]["path"]).read_bytes())
    sources = {entry["path"]: (source_root / entry["path"], entry["sha256"]) for entry in contract["artifacts"].values()}
    sources["service/artifact-contract.json"] = (source_root / "service/artifact-contract.json", digest(contract_blob))
    sources["provenance/data-provenance.json"] = (source_root / "docs/data-provenance.json", freeze["sha256"]["docs/data-provenance.json"])
    attribution = source_root / "deployment/DATASET-ATTRIBUTION.md"
    sources["DATASET-ATTRIBUTION.md"] = (attribution, digest(attribution.read_bytes()))
    prepared = {}
    for name, (source, expected) in sources.items():
        if not source.resolve().is_relative_to(source_root):
            raise ValueError("Source path escapes project")
        blob = source.read_bytes()
        if digest(blob) != expected:
            raise ArtifactError("checksum_mismatch", "export_source")
        prepared[name] = blob
    destination.mkdir(parents=True, exist_ok=False)
    records = {}
    for name, blob in sorted(prepared.items()):
        target = local_path(destination, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(blob)
        target.chmod(0o644)
        records[name] = {"sha256": digest(blob), "bytes": len(blob)}
    for folder in destination.rglob("*"):
        if folder.is_dir():
            folder.chmod(0o755)
    destination.chmod(0o755)
    manifest = {"runtime_version": __version__, "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_contract_sha256": digest(contract_blob), "files": records,
        "scope": "Byte-preserved processed historical-demo inputs and provenance; mount read-only. No raw workbook or saved forecasts.",
        "total_member_bytes": sum(row["bytes"] for row in records.values())}
    with (destination / "bundle-manifest.json").open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, indent=2)
        stream.write("\n")
    verify_bundle(destination)
    return manifest


def load_runtime_engine(root):
    """Extra deployment integrity checks, followed by all unchanged API checks."""
    try:
        verify_bundle(root)
        identities = json.loads(Path(__file__).with_name("runtime-code.json").read_bytes())
        if digest((Path(root) / "service/artifact-contract.json").read_bytes()) != identities["service_contract_sha256"]:
            raise ArtifactError("checksum_mismatch", "service_contract")
        for name, expected in identities["installed_module_sha256"].items():
            module = importlib.import_module(name)
            if digest(Path(module.__file__).read_bytes()) != expected:
                raise ArtifactError("checksum_mismatch", "installed_inference_code")
        return load_engine(Path(root))
    except ArtifactError:
        raise
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise ArtifactError("invalid_runtime_bundle", "runtime_integrity") from exc
