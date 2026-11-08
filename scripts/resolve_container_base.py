"""Resolve anonymous official Python image metadata; never pull an image or data."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen


def main():
    root = Path(__file__).resolve().parents[1]
    output = root / "deployment/base-image.json"
    if output.exists():
        print(output.read_text())
        print("Existing pinned resolution retained; no overwrite or registry refresh.")
        return
    token_url = "https://auth.docker.io/token?service=registry.docker.io&scope=repository:library/python:pull"
    with urlopen(token_url, timeout=30) as response:
        token = json.load(response)["token"]
    headers = {"Authorization": "Bearer " + token,
        "Accept": "application/vnd.oci.image.index.v1+json,application/vnd.docker.distribution.manifest.list.v2+json,application/vnd.oci.image.manifest.v1+json,application/vnd.docker.distribution.manifest.v2+json"}

    def fetch(path):
        request = Request("https://registry-1.docker.io/v2/library/python/" + path, headers=headers)
        with urlopen(request, timeout=30) as response:
            raw = response.read()
            return raw, dict(response.headers)

    tag = "3.13-slim-trixie"
    raw, response_headers = fetch("manifests/" + tag)
    digest = "sha256:" + hashlib.sha256(raw).hexdigest()
    advertised = next(value for key, value in response_headers.items() if key.lower() == "docker-content-digest")
    if digest != advertised:
        raise ValueError("Registry manifest digest mismatch")
    index = json.loads(raw)
    platform = next(item for item in index["manifests"] if item["platform"].get("os") == "linux" and item["platform"].get("architecture") == "amd64")
    manifest_raw, _ = fetch("manifests/" + platform["digest"])
    if "sha256:" + hashlib.sha256(manifest_raw).hexdigest() != platform["digest"]:
        raise ValueError("Platform manifest digest mismatch")
    manifest = json.loads(manifest_raw)
    config_raw, _ = fetch("blobs/" + manifest["config"]["digest"])
    if "sha256:" + hashlib.sha256(config_raw).hexdigest() != manifest["config"]["digest"]:
        raise ValueError("Image configuration digest mismatch")
    config = json.loads(config_raw)
    env = dict(entry.split("=", 1) for entry in config["config"]["Env"])
    record = {"resolved_at_utc": datetime.now(timezone.utc).isoformat(), "official_repository": "docker.io/library/python",
        "requested_tag": tag, "python_version": env["PYTHON_VERSION"],
        "resolved_version_tag": env["PYTHON_VERSION"] + "-slim-trixie", "index_digest": digest,
        "linux_amd64_manifest_digest": platform["digest"], "config_digest": manifest["config"]["digest"],
        "platform": "linux/amd64", "source": "Docker Hub official library/python registry API; anonymous manifest/config metadata only",
        "note": "No image pulled or container executed by this resolver."}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(record, stream, indent=2)
        stream.write("\n")
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
