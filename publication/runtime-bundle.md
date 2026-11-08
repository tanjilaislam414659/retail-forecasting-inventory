# Data and runtime access

## Immediate dataset-free use

The committed small aggregate reports and actual screenshots are sufficient to
inspect validation/final-test evidence and inventory scenarios. The service can
serve those views with no UCI download. `/health` is process liveness; `/ready` and
forecasts correctly return 503 until the required frozen runtime bundle is present.
Synthetic CI is an engineering test, not an alternative scientific release.

## Forecast demonstration with a verified bundle

The full-data history/calibration artifacts are intentionally outside Git. In the
original research workspace, the existing explicit copy-only exporter is:

```powershell
.\.venv\Scripts\python.exe scripts/export_runtime_bundle.py
```

It verifies/reuses matching existing artifacts and never trains or regenerates
them. It cannot reconstruct missing calibration from a raw data download.

Download [runtime ZIP](https://github.com/tanjilaislam414659/retail-forecasting-inventory/releases/download/v0.1.0/retail-forecasting-runtime-v0.1.0.zip)
and [SHA256SUMS.txt](https://github.com/tanjilaislam414659/retail-forecasting-inventory/releases/download/v0.1.0/SHA256SUMS.txt)
from [v0.1.0](https://github.com/tanjilaislam414659/retail-forecasting-inventory/releases/tag/v0.1.0).
The SHA-256 is `f9dfddfc9dfc7d0bf3ed8406bd28951e409a94fd49dfee63af1772fea87871c1`
(339,046 bytes). The release ZIP adds MIT/CC BY 4.0 notices outside the original
frozen bundle directory. All original runtime members are byte-identical; the
original prepared ZIP remains preserved separately and has its original hash.
The committed `publication/runtime-attachment.json` provides the publication hash.

Before extracting a supplied ZIP, compare `Get-FileHash -Algorithm SHA256` with
the separately supplied checksum. Extract only a trusted, verified attachment:

```powershell
New-Item -ItemType Directory -Force artifacts/runtime | Out-Null
Expand-Archive .\retail-forecasting-runtime-v0.1.0.zip artifacts/runtime
# Result: artifacts/runtime/milestone-9-v0.1.0/bundle-manifest.json
.\.venv\Scripts\python.exe -m retail_forecasting.demo --root artifacts/runtime/milestone-9-v0.1.0 --runtime-bundle --port 8000
```

The unchanged loader checks the bundle envelope, required member hashes, installed
inference code, 100-SKU cohort, history mask and frozen calibration. Keep these
checks intact. The bundle holds 16 members plus its manifest, approximately 427 KB
of member content. It has no raw workbook, customer IDs, saved evaluation forecasts
or fitted candidate models. Docker mounts the extracted directory read-only.

## Public raw-data acquisition (separate research route)

Source: Chen, D. (2012), [UCI Online Retail II](https://doi.org/10.24432/C5CG6D),
[official UCI page](https://archive.ics.uci.edu/dataset/502/online+retail+ii),
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Original retrieval,
45,622,278-byte workbook and SHA-256 are in `docs/data-provenance.json`.
The source has customer identifiers; keep raw/customer-level records outside Git.
Only aggregated SKU/day positive sales enter forecasting outputs.

For an intentionally new research environment, `requirements-dev.txt` and `pyproject.toml` define scientific dependencies.
Use a separate research environment and install the root project editable there. After
that installation, the explicit public acquisition command is:

```powershell
.\.venv\Scripts\python.exe -m retail_forecasting acquire
```

This is an optional approximately 45.6 MB download, not a CI, container, startup or
request operation. It records source/time/bytes/SHA-256 and preserves raw bytes.
It was **not run during publication preparation**. Downloading the workbook alone
does not recreate the frozen runtime bundle. Preparation, calibration and the
consumed final test are separate historical stages: do not run them merely to
start the portfolio demo or present repeated assessment as new held-out evidence.
