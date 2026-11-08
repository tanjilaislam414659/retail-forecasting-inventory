# Milestone 9 — Docker packaging and CI preparation

Engineering distribution: **retail-forecasting-runtime 0.1.0**, separate from the
unchanged API 0.1.0 and frozen weekday-mean point release. The original forecaster,
calibration, final results, 163-file freeze and 70-file archive remain unchanged.
No real-data training, recalibration, acquisition or final performance evaluation
was performed. Forecast parity here is numerical regression verification.

## Actual container verification status

**Docker execution now passes.** After the user started Docker Desktop, the
existing pinned image built and ran on Linux amd64. Health, readiness, metadata,
valid/invalid forecasts, six-case numerical parity, missing/corrupt artifact
handling, effective non-root execution, read-only mounting/filesystem and
loopback-only publication were verified. All test containers were stopped and
removed afterward. No system software was installed by the agent.

The earlier unavailable-Docker result remains preserved in its original evidence
directory and in `artifacts/engineering/milestone-9-pre-container-verification/`,
which archives the pre-update report, README, helper and original engineering
release record. New actual evidence supersedes only that earlier blocker.

**Hosted GitHub Actions is pending.** The workflow was authored and its Python
steps rehearsed locally on Windows; no repository/image was published and no
hosted run was triggered. Linux container execution is now verified; hosted
Ubuntu-runner/Actions execution remains unverified.

## Files and identity

- Root `Dockerfile`, `.dockerignore`, `compose.yaml`: minimal multi-stage image,
  default-deny build context, non-root UID/GID 10001:10001, readiness health check,
  read-only filesystem and runtime bind, internal 0.0.0.0:8000 and host
  **127.0.0.1:8000 only**.
- `packaging/runtime/pyproject.toml`: minimal independent installable package.
  It contains frozen baseline/interval modules, the unchanged API modules and
  the new deployment adapter. Research experiments, plotting, acquisition and
  preparation modules and all datasets are excluded.
- `deployment/requirements-*-linux.lock` and wheel inventories: exact runtime,
  build and CI versions plus downloaded-wheel SHA-256 hashes. `deployment/README.md`
  provides Windows operation instructions and limitations.
- `src/retail_forecasting/deployment/`: copy-only bundle export/verification,
  installed-code validation, container launcher and standard-library readiness probe.
- `ci/` and `.github/workflows/ci.yml`: visibly synthetic fixtures/tests,
  installed-wheel checks and pinned official Actions commits.
- `scripts/build_runtime_package.py`, `export_runtime_bundle.py`,
  `validate_packaging.py`, `check_ci_without_data.py`, `verify_runtime_bundle.py`,
  `verify_container.py`: explicit build, copy, validation and integration commands.

The official Python Docker registry resolved on **2026-11-04** to
**Python 3.13.18-slim-trixie**, Debian slim, linux/amd64:

```text
Index:        sha256:ae14d4ce8771606477a81446e7ef429edd6762305fc50c84507c1041fa8285d1
linux/amd64:  sha256:aaf08c5490d52cd92bc27142a5215b1e47355a5eaf9adfad2a0fbc022d0b5490
Config:       sha256:bdfc738a8a869292ec1b01f1b8e620db533e09d1fe68fe980a7118b22dae9cec
```

The Dockerfile pins the index digest in both stages; Compose selects linux/amd64.
`deployment/base-image.json` records the public anonymous registry metadata.
Manifest/config bytes were checked against their advertised digests. This resolves
the base identity. The original resolution retrieved metadata only; the follow-up
container verification has now actually built and executed the pinned image.
Source: [official Python image](https://hub.docker.com/_/python).

All original source/configuration bytes stay intact. The existing `.gitattributes`
rules were retained with a final `* -text` override so Git does not normalize bytes
covered by frozen hashes when cloning across Windows/Linux. This changes Git
packaging behavior, not scientific artifacts or system settings. Source and small
synthetic fixtures are included in a local Git commit; ignored datasets, snapshots,
caches, models and generated evidence are excluded. No push or remote publication.

## Runtime data bundle

The explicit exporter copied **16 existing files, 427,125 member bytes**, plus
`bundle-manifest.json`, to ignored `artifacts/runtime/milestone-9-v0.1.0/`.
The directory is mounted read-only at `/runtime`; the full research workspace is
not mounted or copied into the image.

Five files provide the unchanged daily panel, cohort, modelling-history mask/scales,
quantiles and calibration record. Eight provide three specifications, two frozen
source modules and three lineage manifests. Three provide the API contract,
original provenance and UCI/CC BY 4.0 attribution. The bundle contains no raw
workbook, customer identifiers, saved forecasts, candidate-model binaries or plots.
All paths are relative. Code copies required by the original loader retain their
original paths; deployment additionally hashes the actually imported installed
code, so integrity is not bypassed by checking only unused mounted source copies.

The exporter validates native inputs, copies bytes only and refuses partial or
different existing bundles. Re-export verified the existing bundle without a
single byte change. Startup verifies the bundle envelope and installed code, then
runs every unchanged original API check. No data preprocessing or calibration is
performed at build, startup or request time. Missing/corrupt data produces health
200 but readiness/forecast 503, and fails the container readiness probe.

## Checks actually executed

| Check | Actual outcome |
| --- | --- |
| Original freeze/final-output and archived-source integrity | Passed; no evaluation run |
| Original API 0.1.0 release source/configuration hashes | Passed |
| Linux CPython 3.13 wheel resolution/download | 18 runtime, 6 build, 28 CI wheels pinned |
| Offline Linux runtime hash-lock dependency replay | Passed from cached wheels; no Linux execution |
| Static Compose/Actions YAML and package/Docker configuration checks | Passed; not a Docker daemon parser or hosted run |
| Minimal Python sdist and wheel build | Passed; wheel built from the sdist |
| Synthetic tests | 16 passed, zero skipped |
| Clean temporary checkout/venv rehearsal | Passed: offline dependency install, build/install wheel, pip check, 16 tests, static checks, installed-package/source-hash checks |
| Full native runtime-bundle host integration | Passed: readiness/metadata, six parity cases, invalid request, missing/corrupt copies |
| Project installation/console isolation and pip check | Passed |
| Docker build/run/health/container parity | Passed on Docker Desktop Linux amd64; six cases / 168 days |
| Effective UID/GID and read-only write probes | Passed: 10001:10001; `/runtime` and `/app` rejected writes with EROFS (30) |
| Compose loopback publication and cleanup | Passed: 127.0.0.1:8000 only; containers removed |
| Hosted Actions run | Pending, no publication requested |

The clean Windows rehearsal had **no data, models, artifacts or research-source
imports**. It installed an actual wheel into a separate project-cache virtual
environment; code/import checks confirmed site-packages and byte-exact frozen
inference/API modules. That temporary environment was deleted afterward. The
existing project `.venv` was preserved, adding only pinned build/YAML tools; no
base research dependency version or global setting changed.

Full-data host integration covered three SKUs (21212, 21166, 21533) at the first
validation and last final origin: **six cases / 168 daily predictions**, including
both interval levels. Maximum numeric difference against the local service was
**0**, using **rtol=1e-12, atol=1e-9**. No target actuals or performance scores were
used. Missing calibration copy returned `missing_artifact`; corrupted copy returned
`checksum_mismatch`; both produced readiness/forecast 503 and health 200.
Host artifact loading measured **881.648 ms**. This is not container startup timing.

Evidence directories under ignored `reports/generated/deployment/`:

- `ci-rehearsal-20261104T183139243192Z/`: clean installed-wheel rehearsal and command log.
- `bundle-integration-20261104T183002416536Z/`: portable runtime/native integrity/parity.
- `docker-check-20261104T183003891107Z/`: exact blocker, container execution false,
  image size and startup time null (historical, superseded).
- `docker-check-20261104T194756704833Z/`: actual image build, endpoint/parity and
  missing/corrupt artifact checks passed.
- `compose-check-20261104T194820619330Z/`: actual healthy Compose runtime,
  permissions/mount/write probes, timing, example response and cleanup evidence.

## Measured Docker results

Docker Desktop 4.98.0 / Engine 29.9.2 / Compose 5.6.1 used the desktop-linux
context. A read-only platform probe confirmed **Linux x86_64, Python 3.13.18,
effective UID/GID 10001:10001**. The original Dockerfile, Compose configuration,
dependency locks, runtime code, forecaster, calibration and data bundle required
no changes to work.

```text
Tested image ID: sha256:1654cb28fdfd8979101b9f1d0bb8ded7c3139e41164d2aa24227c524de4dbe44
```

| Measurement | Observed |
| --- | ---: |
| Image size reported by Docker inspect | 399,768,129 bytes (399.8 MB / 381.2 MiB) |
| Container launch to first health HTTP response | 2,428.382 ms |
| Compose operation through Docker healthy status | 7,279.453 ms |
| In-container artifact validation/loading | 873.737 ms |
| Warm forecast HTTP median, 20 sequential requests | 22.483 ms |
| Warm forecast HTTP p95 | 26.541 ms |

These are local Docker Desktop wall-time measurements, not a load benchmark.
The Compose timing includes network/container creation and health polling; it
must not be substituted for the in-application artifact-load time. Docker's size
is its reported image size, not registry download size or total Desktop cache use.

Real-container parity covers SKUs 21212, 21166 and 21533 at 2011-06-06 and
2011-11-07: **six cases, 168 dated predictions and 336 level-specific daily
intervals**. Point and both-level endpoint comparisons showed maximum absolute
numeric difference **0**, using **rtol=1e-12, atol=1e-9**, against the local
service's recomputed forecasts. Dates/horizon alignment and 28-value response
lengths passed. Responses retain historical-demo and experimental-interval labels
and release/calibration identities; no target actuals or customer identifiers are
returned. This is regression verification, not a new final performance evaluation.

Normal health/readiness/metadata/forecast requests returned 200. Unknown SKU,
unsupported origin, unsupported horizon and unexpected-field requests returned
422. Separate mounted **test copies** with missing/corrupt calibration returned
health 200, readiness/forecast 503, and nonzero readiness-probe exits; the codes
were `missing_artifact` and `checksum_mismatch`. Original bundle bytes remained
unchanged. No checksum bypass, regeneration or fallback was used.

Inspection confirmed a bind mount at `/runtime` with **RW=false**, a read-only
container root filesystem, internal **0.0.0.0:8000**, and the sole host binding
**127.0.0.1:8000**. Actual exclusive-create attempts under `/runtime` and `/app`
both failed with **EROFS (errno 30)**. The running process reported UID/GID 10001,
independently of the image's configured USER field. Compose reached Docker
`healthy` state. The verification scripts used only their own test containers;
all were stopped and removed. The local image remains available, unpublished.

Three verification-helper defects surfaced during the first real execution:
Windows cp1252 decoding of Docker's UTF-8 output, a transient startup connection
reset outside the retry handling, and reopening an already-used HTTPX client.
The helper now uses explicit UTF-8 decoding, retries transport errors only during
the bounded startup wait, and closes used clients without reopening them. The
original helper is archived, failed-run evidence directories remain preserved,
and the successful runs follow these fixes. These changed verification plumbing
only; no Dockerfile, dependency, runtime calculation or frozen evaluation artifact
was corrected. `deployment/container-verification-20261104.json` records this
verification revision separately from the original 0.1.0 engineering release.

Initial local checks caught an unquoted YAML colon in the pip command and a
sandbox temporary-directory permission error in package building. The YAML now
uses a block scalar; the build backend uses project-cache temporary files. These
engineering fixes changed no evaluation rule or frozen result. API/event-loop
tests were executed outside the restricted sandbox after prior sandbox behavior
was established; no machine setting was changed.

## CI coverage and platform differences

Routine CI uses **182 explicitly synthetic history rows** and **16 artificial
quantile rows** for two synthetic SKUs. The expected weekday means and bounds are
hand-calculable; quantiles are constants, not recalibration of the public data.
Coverage includes calculation arithmetic, complete dates, future-mutation leakage
guards, interval ordering/nonnegativity, unchanged points, request validation,
readiness/error/logging behavior, and envelope integrity/path safety. Tests inject
a synthetic engine through the existing factory; production loading is unchanged.
No silent skip: missing dependencies, failed tests, any skip or fewer than 16 tests
fail the runner. `ci/README.md` states the scope separately from full-data checks.

The prepared workflow runs Ubuntu 24.04/Python 3.13.18, uses official Actions
commits, read-only contents permission and no retained checkout credentials. It
installs hash-locked wheels, builds and installs the minimal distribution, runs
the explicit tests, validates configuration and checks installed package contents.
Only the Python distributions would be uploaded as workflow artifacts. There is
no PyPI/container-registry publication or research-data download step.

Windows remains CPython 3.13.5. Serving package versions match the Windows service,
but NumPy/pandas/pydantic-core wheels and OS/glibc differ. Linux amd64 only is
supported by the current lock. Scientific/plotting dependencies are excluded from
runtime. A small optional Windows colorama build-tool dependency was conservatively
locked too; it is not a serving dependency. Representative Linux container parity
now passes as recorded above. Hosted Actions/Ubuntu-runner execution is pending.

## Commands and remaining limitations

```powershell
.\.venv\Scripts\python.exe scripts/export_runtime_bundle.py
docker compose config
docker compose build
docker compose up -d --wait --wait-timeout 90
$body = @{sku="21212"; origin="2011-11-07"; horizon_days=28} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/forecast -ContentType application/json -Body $body
docker compose down
```

For full local container checks once Docker is available:
`.\.venv\Scripts\python.exe scripts/verify_container.py`. It builds the local
image, tests health/readiness/metadata and valid/invalid requests, compares six
cases with the local service, checks missing/corrupt copies, records actual size
and startup, and removes only its own test containers. Its Docker branch has now
passed on this machine. `scripts/verify_compose_runtime.py` separately verifies
the actual Compose health state, effective UID/GID, read-only mount/filesystem,
denied writes, loopback-only port binding and cleanup.

For a fresh Windows dataset-free rehearsal, first cache dependencies with
`.\.venv\Scripts\python.exe -m pip download --only-binary=:all: --dest .cache/ci-windows-wheels -r deployment/requirements-ci.in`,
then run `.\.venv\Scripts\python.exe scripts/check_ci_without_data.py`. This is
a local rehearsal, not an Actions run.

Remaining limitations: hosted workflow execution pending; representative rather
than exhaustive Linux parity; no arm64 lock, load/stress test, production monitoring,
authentication, rate limiting, live ingestion or production-readiness claim. The
underlying observed-sales/experimental uncertainty limitations remain. There is
no dashboard or inventory simulation.
