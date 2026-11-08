# Milestone 8 — local historical forecasting API, service 0.1.0

The `retail-forecasting-api` distribution is versioned separately from the
unchanged `retail-forecasting==0.1.0` project and the frozen point release
`weekday-mean-1.0+fcd91ea17928`. It is a local historical demonstration for the
100 selected SKUs and 20 previously evaluated validation/final origins. It is
**not a live retail-data service or production-ready application**.

## Preservation and boundaries

The original final bundle, all 163 pre-unblinding hashes, prior models/results,
preparation rules, onset mask, cohort, original-training scales and quantiles
remain unchanged. No model was retrained on project sales, no calibration was
fitted, and no performance evaluation was repeated. Numerical parity is regression
verification, not new performance evidence. Existing model unit tests use their
original synthetic fixtures only.

An additional byte-preserved 70-file source/configuration/provenance snapshot is
stored at `artifacts/frozen-release/milestone-7-fcd91ea17928/`, with its own hash
manifest. Original evaluation datasets/artifacts remain in their existing paths.
`scripts/snapshot_release_for_service.py` verifies or copies this snapshot without
overwriting anything. Frozen root README, AGENTS.md, pyproject, lock and earlier
source remain unchanged; the current user authorization adds this separately
versioned API despite the earlier milestone's narrower scope. New operating
instructions are in `service/README.md`.

`service/artifact-contract.json` pins required history, cohort, mask, quantiles,
calibration record, release manifests, original inference code and configurations
by SHA-256. It also identifies the source snapshot. `service/release-0.1.0.json`
records the service source, contract, dependencies and verification evidence.
Generated smoke/parity logs and responses remain ignored under
`reports/generated/service/`; no data, environment or model enters Git.

## Inference and lifecycle

The reusable `service.inference.infer_one` computes the existing weekday mean
using the preceding 56 calendar days, eight occurrences of each forecast weekday.
It calls the byte-unchanged baseline and interval functions. All 28 predictions
are issued from that pre-origin history; their future realized sales are never
used. `InferenceEngine.predict` passes only dates strictly before origin, and the
reusable function and original baseline enforce that boundary again.

The original per-SKU/horizon-week training residual quantiles define the same
max(0, point + quantile) daily 80% and 95% endpoints. There is no rounding, forced
point containment, weekday-specific zero rule, tuning or calibration update.
The calibration identifier is:

```text
sha256:8fba3ffbd0e1dd9d3827432f1c41d4c03326c904840dfd64db7cc0d2e701ea55
```

FastAPI lifespan loads and validates the artifacts once. The loader checks hashes,
release linkage, cohort/mask reconciliation including SKU 21166, calendar coverage,
finite nonnegative integer sales, all 800 calibration group/level rows and nested
quantiles. After applying the preserved mask, in-memory history is restricted to
2011-04-11 through 2011-11-06: dates that may feed a supported origin's lookback.
Each request further restricts it to dates before its own origin. Prior validation
or earlier test sales may therefore feed later origins, exactly as before.

Startup and requests never read saved evaluation forecast files, raw workbook or
transaction audit/customer records. Startup has no download, training, evaluation
or recalibration operation. Requests perform no disk reads or CSV parsing.
No import-time artifact load occurs. Missing, corrupt or unreadable required
artifacts leave the process alive but unready; no substitute data or partial
forecasts are served. Restore the pinned files and restart to recover.

## HTTP contract

| Endpoint | Behaviour |
| --- | --- |
| `GET /health` | 200 process health and service version; independent of artifacts |
| `GET /ready` | 200 after validated loading, otherwise 503 with safe error code |
| `GET /metadata` | Supported 100 SKUs, 20 origins, horizon, release/calibration IDs and limitations; 503 when unready |
| `POST /forecast` | One SKU/origin, exactly 28 dated predictions and both experimental daily intervals |

The typed Pydantic schemas forbid unexpected request fields. SKU must be a string;
origin must be an exact valid `YYYY-MM-DD` calendar-date string. Only supported
origins are accepted. `horizon_days` defaults to 28 and, if supplied, must be the
integer 28: booleans, floats, strings and other horizons are rejected. Invalid
requests return 422 with field/code/message details without echoing submitted
values. Unknown cohort/origin errors direct the caller to `/metadata`.

Responses include SKU, origin, inclusive history cutoff (origin minus one day),
method/release/calibration identifiers, service version, historical-demo and
experimental-interval labels. No target actuals or customer identifiers are returned.
Bounds are finite, nonnegative, ordered and nested. These checks do not force the
point forecast inside its interval.

Each request receives a generated `X-Request-ID`. Minimal JSON logs contain request
ID, status/outcome, service version and elapsed milliseconds. Startup logs contain
readiness and load time; artifact failures use safe logical artifact names. Logs
exclude request bodies, URLs/queries, credentials, headers and complete histories.
Uvicorn access logging is disabled. There is no remote telemetry.

## Windows installation, run and example

The existing `.venv` was retained. Dependencies are pinned in
`service/pyproject.toml` and `service/requirements-lock.txt`, which includes the
unchanged base lock. Key versions: FastAPI 0.121.1, Pydantic 2.12.4,
Starlette 0.49.3, Uvicorn 0.38.0, HTTPX 0.28.1; Windows CPython 3.13.5.
No base dependency was upgraded or global setting changed.

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m pip install -r service/requirements-lock.txt
.\.venv\Scripts\python.exe -m pip install --no-build-isolation --no-deps -e ./service
.\.venv\Scripts\python.exe -m retail_forecasting.service --root . --port 8000
```

The launcher binds only to **127.0.0.1**, one worker, no reload. The equivalent
installed console launcher is `.\.venv\Scripts\retail-forecasting-api.exe`.
Visit `http://127.0.0.1:8000/docs`, `/redoc`, or `/openapi.json` after starting it.
The OpenAPI JSON needs no external browser asset; interactive Swagger/ReDoc use
their standard external CDNs. The actual forecasting service makes no outbound
network calls.

```powershell
$body = @{sku="21212"; origin="2011-11-07"; horizon_days=28} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/forecast -ContentType "application/json" -Body $body
```

Measured first prediction from that 28-day response:

```json
{
  "target_date": "2011-11-07",
  "horizon_day": 1,
  "predicted_sales": 109.625,
  "interval_80": {"lower": 0.0, "upper": 328.0999999999999},
  "interval_95": {"lower": 0.0, "upper": 590.5000000000006}
}
```

Its history cutoff is 2011-11-06, and the last target is 2011-12-04. The full
response is saved in the smoke evidence, not truncated or rounded by the API.

## Measured verification

**66 tests pass: 52 preserved earlier tests plus 14 new service tests.** New tests
cover valid/invalid requests, OpenAPI schemas, liveness versus readiness,
missing/corrupt contract/history/calibration/code fixtures, load-once/no-I/O
requests, no saved-forecast reads, date alignment, finite/nonnegative/nested
intervals, missing-group refusal, future-sales mutation invariance through both
inference and HTTP, pre-origin-only inference arguments, parity and credential-free
structured logging. An initial new test used unsupported `DatetimeIndex.lt`; its
assertion was corrected to `<`. This was test-only development, with no change to
frozen rules or results.

Full parity verification checks **2,000 SKU/origin cases**, **56,000 dated point
predictions** and **112,000 level-specific daily intervals** against the saved
point/interval outputs. No actual-sales columns are loaded for parity and no
performance metrics are computed. Explicit tolerances are **rtol=1e-12,
atol=1e-9**. Maximum absolute differences: point **0**, lower endpoint
**5.684341886080802e-14**, upper endpoint **1.1368683772161603e-13**.
These tiny CSV floating-point differences are within tolerance. The existing
Milestone 7 checker correction remains preserved; no new evaluation defect or
statistical result correction is introduced.

Real HTTP smoke test: health, ready, metadata, OpenAPI, docs and forecast returned
200; invalid SKU/origin/horizon cases returned 422. The test started a hidden
loopback-only server on available port 56382 and stopped only that subprocess.
Final-code measurements:

| Measurement | Observed |
| --- | ---: |
| Artifact validation/loading | 611.776 ms |
| Process launch to ready HTTP response | 1,858.804 ms |
| Warm forecast HTTP median, 20 sequential requests | 17.165 ms |
| Warm forecast HTTP p95 | 18.621 ms |
| Warm forecast HTTP minimum / maximum | 15.552 / 21.264 ms |

These local CPU wall times include client parsing for HTTP requests; they are
not a concurrency/load benchmark. Full 2,000-case numerical inference verification
took 30.566 seconds, separately from artifact load (0.799 seconds).
Environment/module/console isolation verification and `pip check` pass. API
TestClient/event-loop execution required running outside the restricted sandbox;
the same local tests and smoke test then passed. This changes no system settings.

Evidence:

- `reports/generated/service/parity-20261102T071446148590Z/parity.json`
- `reports/generated/service/smoke-20261102T071525485878Z/smoke.json`
- The same smoke directory's `example-response.json`, `metadata.json`, `server.log`.
- `service/release-0.1.0.json` for source/input identities, dependencies and checks.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts/verify_service_parity.py
.\.venv\Scripts\python.exe scripts/smoke_local_api.py
.\.venv\Scripts\python.exe scripts/verify.py
.\.venv\Scripts\python.exe -m pip check
```

## Remaining limitations

This is a historical single-process demonstration with local filesystem artifacts.
There is no live ingestion, automatic artifact reload, authentication, rate limiting,
load/stress testing, multi-worker coordination, deployment or monitoring backend.
Artifact validation is startup integrity checking, not a security boundary against
a malicious local operator. A new worker/start requires another verified load.
The data/source snapshot must be available at the documented relative paths; it
is not a self-contained data-distributing wheel. Large request-body limits are
not implemented for this loopback demonstration.

All forecast limitations remain: observed sales are not latent demand, conditional
coverage is weak for some SKUs/weekdays, bands may be broad, and daily intervals
give no total-sales/joint/conformal/finite-sample guarantee. Final outcomes were
already consumed; engineering parity adds no fresh forecasting evidence. Docker,
dashboard, cloud/public hosting and inventory simulation are outside this milestone.

Framework choices follow the official [FastAPI lifespan documentation](https://fastapi.tiangolo.com/advanced/events/),
[lifespan testing documentation](https://fastapi.tiangolo.com/advanced/testing-events/)
and [Pydantic model validation documentation](https://docs.pydantic.dev/latest/concepts/models/).
