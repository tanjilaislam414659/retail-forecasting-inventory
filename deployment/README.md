# Container packaging and CI — engineering runtime 0.1.0

This distribution packages the unchanged API 0.1.0 and frozen weekday-mean
forecaster. It is a historical demonstration, not production-ready or a live feed.
Experimental daily intervals retain all documented limitations. No training,
recalibration, data acquisition or final performance evaluation belongs in image
build, startup, requests or routine CI.

## Current execution status

Docker Desktop is now verified on Linux amd64. The existing image built and ran;
health/readiness, six-case parity, missing/corrupt artifacts, effective UID/GID
10001, read-only mounts/root filesystem and loopback-only publication passed.
All test containers were stopped and removed. Docker reported 399,768,129 bytes
for the image; first healthy HTTP response took 2.428 seconds, while Compose's
wait-for-healthy operation took 7.279 seconds. Hosted GitHub Actions remains
pending: nothing has been published or triggered. See `docs/milestone-9.md`.

## Windows commands

Run from the repository root after Docker Desktop/Linux containers are available:

```powershell
# Explicit copy-only export from existing verified artifacts; never a data rebuild.
.\.venv\Scripts\python.exe scripts/export_runtime_bundle.py
docker compose config
docker compose build
docker compose up -d --wait --wait-timeout 90
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/ready
Invoke-RestMethod http://127.0.0.1:8000/metadata
$body = @{sku="21212"; origin="2011-11-07"; horizon_days=28} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/forecast -ContentType application/json -Body $body
docker compose down
```

Open `/docs` or `/openapi.json` after startup. Internally the new runtime entry
point binds to **0.0.0.0:8000**; Compose publishes only **127.0.0.1:8000**.
The original local API launcher still binds only to 127.0.0.1. The image runs as
numeric non-root UID/GID 10001:10001. It uses `/ready` for health checking.
The container root filesystem and runtime bind mount are read-only, with only
a small tmpfs at `/tmp`. No full research workspace is mounted or copied.

## Required runtime bundle

Default mount: `artifacts/runtime/milestone-9-v0.1.0` to `/runtime`, read-only.
The exporter refuses to overwrite partial/different bundles and verifies existing
exports. It copies bytes without changing scientific artifacts:

- Existing daily panel, 100-SKU cohort, modelling-history mask/scales and original
  residual-quantile table/calibration record (five files).
- Three fixed specifications, unchanged point/interval source files, final freeze
  and completion manifests, and archived snapshot manifest (eight files).
- Original API artifact contract, original dataset-provenance JSON and UCI/CC BY
  attribution (three files).
- A new bundle manifest hashing all 16 members. It contains no raw workbook,
  customer identifiers, saved evaluation forecasts, trained candidates or plots.

All paths remain relative to the mounted root. Every original native API check
still runs. Deployment adds envelope-member hashes and comparison of the installed
inference/API source against pinned code bytes, so copying a verified source file
into a mount cannot substitute for verifying the actual installed code.
Required metadata/manifests reference the original full research artifacts by
hash; the referenced full datasets/models are not runtime dependencies.

A missing mount path makes Compose refuse creation. Missing/corrupt members leave
the process alive with `/health` 200 but `/ready` and forecasts 503; the health
check fails. No fallback or checksum bypass is implemented. Restore pinned files
and restart. The image contains no dataset; keep the exported public-data bundle
separately with its attribution and mount it read-only.

## Reproducibility and Linux differences

The official Python base is **3.13.18-slim-trixie**, pinned to its immutable index
digest in both Dockerfile stages. `deployment/base-image.json` records the anonymous
registry resolution, linux/amd64 manifest digest and config digest. Only metadata
was retrieved; resolving a digest is not pulling/running an image.

Linux amd64 CPython 3.13 wheels were actually downloaded and SHA-256 locked.
`requirements-runtime-linux.lock` contains only serving dependencies; NumPy 2.3.4,
pandas 2.3.3 and API pins match Windows. NumPy/pandas/pydantic-core use Linux wheels
instead of Windows wheels. The container's Python patch (3.13.18), glibc, timezone
and OS differ from Windows CPython 3.13.5. Real-container parity now passes for
six representative SKU/origin cases (168 forecast days), with zero observed
numeric difference at rtol=1e-12, atol=1e-9. This is not an exhaustive cross-OS
bit-identity guarantee. Only Linux amd64 is locked/supported by this packaging.

Installations use `--require-hashes --only-binary=:all:` with complete transitive
locks; no scientific dependency is compiled. Build-only tools and CI-only HTTPX/
YAML checks have separate locks. The cross-target resolver retained a small
colorama build-tool dependency; it is not part of serving dependencies. Researchers'
Matplotlib, sklearn, scipy, openpyxl and raw-data tooling are excluded from the
minimal runtime package/image. Exact locks and Docker base need a deliberate new
engineering version for updates; no mutable latest-image update is automatic.

`.dockerignore` defaults to excluding everything, then permits only Dockerfile,
the minimal packaging metadata/locks/README and curated source modules. Environment,
cache, secrets, `.git`, all data/artifact directories and generated outputs stay
out of the build context. Package building similarly stages an explicit source
allowlist and preserves the original code bytes.

## CI and local checks

`.github/workflows/ci.yml` prepares Ubuntu/Python 3.13.18 checks with pinned official
Actions SHAs and read-only repository permissions. It installs hash-locked Linux
dependencies, builds an sdist and wheel, installs the wheel, runs `pip check`, the
explicit synthetic suite, static configuration validation and installed-package
checks. It stores Python distributions as workflow artifacts; it never publishes
to PyPI or a container registry. Hosted execution remains pending.

`ci/fixtures/` contains 182 visibly synthetic history rows and 16 handcrafted
quantile rows for two synthetic SKUs. These are artificial arithmetic examples,
not fitted intervals or replacement production artifacts. HTTP tests inject a
test engine through the existing app factory; the real production loader/checks
remain unchanged and are also tested for missing-contract handling. Routine CI
does not call the root full-data test suite and does not silently skip it. Its
separate scope is unit/API/envelope integrity; it fails on any skip or too few
tests. Full native 100-SKU semantics and parity are integration responsibilities.

```powershell
.\.venv\Scripts\python.exe ci/run_tests.py
.\.venv\Scripts\python.exe scripts/validate_packaging.py
.\.venv\Scripts\python.exe scripts/build_runtime_package.py --output dist/runtime
# Full-data integration, explicitly outside routine CI:
.\.venv\Scripts\python.exe scripts/verify_runtime_bundle.py
# Requires Docker and daemon; builds/runs only local test containers:
.\.venv\Scripts\python.exe scripts/verify_container.py
# Actual Compose health, UID/GID, read-only writes and loopback port checks:
.\.venv\Scripts\python.exe scripts/verify_compose_runtime.py
```

The package build needs the pinned build frontend, setuptools, wheel and
pyproject-hooks in the project environment. The Linux lock cannot install native
Linux wheels into Windows; existing Windows `.venv` dependencies are retained.
`scripts/check_ci_without_data.py` reproduces the installed-wheel synthetic checks
in a clean temporary checkout/environment without research datasets or source
imports. Local Windows checks do not constitute a hosted Ubuntu Actions run.

Remaining limitations include pending hosted Actions/Ubuntu-runner checks,
representative rather than exhaustive Linux parity, single-process operation,
no live ingestion, no authentication/rate limiting, no stress benchmark and
experimental uncertainty. No dashboard, cloud deployment or inventory simulation
is included.
