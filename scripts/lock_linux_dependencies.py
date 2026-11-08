"""Resolve/download dependency wheels, not retail data; record Linux wheel hashes."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
from zipfile import ZipFile
from email.parser import BytesParser


def main():
    root = Path(__file__).resolve().parents[1]
    for scope in ("runtime", "build", "ci"):
        name = "requirements.in" if scope == "runtime" else f"requirements-{scope}.in"
        output = root / "deployment" / f"requirements-{scope}-linux.lock"
        if output.exists():
            raise FileExistsError(f"Refusing to replace existing lock: {output}")
        wheels = root / ".cache/linux-wheels" / scope
        wheels.mkdir(parents=True, exist_ok=True)
        subprocess.run([sys.executable, "-m", "pip", "download", "--only-binary=:all:",
            "--platform", "manylinux_2_28_x86_64", "--platform", "manylinux_2_17_x86_64",
            "--platform", "manylinux2014_x86_64", "--python-version", "313", "--implementation", "cp", "--abi", "cp313",
            "--dest", str(wheels), "-r", str(root / "deployment" / name)], check=True)
        rows = []
        for path in sorted(wheels.glob("*.whl")):
            with ZipFile(path) as wheel:
                metadata_name = next(n for n in wheel.namelist() if n.endswith(".dist-info/METADATA"))
                metadata = BytesParser().parsebytes(wheel.read(metadata_name))
            rows.append((metadata["Name"], metadata["Version"], hashlib.sha256(path.read_bytes()).hexdigest(), path.name))
        with output.open("x", encoding="utf-8") as stream:
            stream.write("# Linux amd64, CPython 3.13; downloaded wheel SHA-256 pins. No source builds.\n")
            for package, version, digest, _ in sorted(rows, key=lambda r: r[0].lower()):
                stream.write(f"{package}=={version} --hash=sha256:{digest}\n")
        with output.with_suffix(".json").open("x", encoding="utf-8") as stream:
            json.dump({"platform": "linux/amd64", "python_abi": "cp313", "wheels": [
                {"name": n, "version": v, "sha256": h, "filename": f} for n, v, h, f in rows]}, stream, indent=2)
            stream.write("\n")
        print(f"Recorded {output.name}: {len(rows)} hashed wheels", flush=True)


if __name__ == "__main__":
    main()
