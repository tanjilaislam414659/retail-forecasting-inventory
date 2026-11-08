# Milestone 11 — local demonstration interface 0.1.0

Completed 2026-11-07. This adds an engineering presentation layer only. No model
training, recalibration, performance evaluation or inventory simulation was run.
No repository/image publication or Milestone 12 work occurred.

## Three bounded views

1. **Forecast explorer:** native selectors for the existing 100 SKUs and 20
   historical origins; the browser calls the unchanged `POST /forecast`. A native
   SVG shows 28 point forecasts and experimental 80%/95% daily intervals, with a
   keyboard-accessible numerical table. Cutoff, method, release and calibration
   identities remain visible. No actual target sales are displayed or used by the
   browser. No simultaneous/total-horizon coverage guarantee is claimed.
2. **Evaluation:** read-only saved validation and consumed final-test results are
   separate. Both show weekday mean and seasonal naive. Recent mean, Ridge and
   Poisson boosting appear only as validation development evidence. The primary
   metric is macro MASE; MAE, pooled WAPE, bias and interval metrics provide context.
   Overlapping forecasts are dependent; row count is not an independent sample size.
3. **Inventory:** lead times 1/3/7 and shortage penalties 1/5 filter 18 saved
   comparisons. Three fixed policies show fulfillment, lost units, average total
   closing stock, order count and synthetic cost. The view explicitly explains
   lost sales, Monday reviews, receipt timing, common initial stock, stale terminal
   forecasts and terminal clipping. It neither runs nor optimizes policies.

The adapter reuses the original FastAPI factory/lifespan, inference function and
artifact validation. Forecast calculations remain outside HTTP route handlers
and browser JavaScript. No separate frontend stack, chart dependency, CDN, external
font or new Python dependency was introduced. Interface distribution/image
`retail-forecasting-demo:0.1.0` is separate from the preserved API/runtime releases.

## Packaging and provenance

- New code: `src/retail_forecasting/demo/`; static HTML/CSS/JavaScript and three
  small aggregate reporting payloads plus their manifest ship in the demo wheel.
- `scripts/package_demo_reports.py` copied existing saved aggregate CSV fields
  once; it refuses overwrites. Its manifest records source hashes and payload
  hashes/byte counts. Three payloads total **13,933 bytes**. No saved forecast rows,
  customer identifiers, raw workbook, research models or inventory ledger ship in
  these reporting copies. They are intentionally versioned small reporting assets.
- Reports load once with SHA-256/length checks. Missing/corrupt reports have explicit
  unavailable cards, independently of other reports. Missing/corrupt forecasting
  artifacts retain the original `/ready` and `/forecast` 503 behavior; saved
  reporting and the static interface remain available. Repair files and restart;
  the service does not regenerate artifacts.
- Docker requires the unchanged Milestone 9 runtime bundle mounted read-only at
  `/runtime` (`artifacts/runtime/milestone-9-v0.1.0`, its manifest and required
  history/cohort/mask/calibration/provenance files). Reporting copies are inside
  the image. No acquisition, raw parsing, fitting or artifact export occurs at
  build/startup/request time.
- Base: official Python **3.13.18-slim-trixie**, pinned index digest
  `sha256:ae14d4ce8771606477a81446e7ef429edd6762305fc50c84507c1041fa8285d1`.
  Existing hash-locked Linux build/runtime dependencies are reused. Windows
  retains its existing Python 3.13.5 environment; Linux wheels/base patch differ.
- Final local image ID returned by Docker image inspection:
  `sha256:8739abed8f1d2baa781a0f22d07620cd48c271cbf77d5c5828c13025c672f6c0`.
  Size: **399,961,668 bytes** (399.96 MB decimal, 381.43 MiB, local Docker logical
  image size; not a registry transfer size). This is a local build, not published.
- Separate wheel/source distribution built in `dist/demo-release/`; wheel
  **43,182 bytes**. Archive inspection confirmed byte parity with current packaged
  Python/static/report sources and absence of research data/experiment modules.
  Use the demo distribution as an alternative runtime, not alongside the
  overlapping original runtime wheel in the same environment.

The frozen root README, original deployment/CI files and archived snapshots were
preserved. Updated run instructions are in `demo/README.md`. The separate demo
release manifest records new source, package, reporting and evidence hashes.

## Checks actually executed

| Check | Result |
|---|---|
| New interface/API/report regressions | **11 passed**, 1.356 s, zero skips |
| Existing full-data service regressions | **14 passed**, 3.029 s, zero skips |
| Existing explicitly synthetic CI suite | **16 passed**, 0.485 s, zero skips |
| Installed package isolation (`scripts/verify.py`) | PASS |
| Existing environment (`python -m pip check`) | No broken requirements |
| JavaScript syntax (`node --check`) | PASS |
| Frozen final/inventory integrity verification | PASS; 321 prior protected artifacts plus inventory inputs/code/results verified |
| Demo wheel/source build and archive byte checks | PASS |
| Actual Linux/amd64 Docker build/Compose start | PASS; healthy |
| Container endpoints/static assets/report parity | PASS, nine endpoints |
| Invalid Docker forecast requests | Five rejected with 422 |
| Docker numerical regression | Six cases, 168 dated rows, 840 values; max absolute difference **0** |
| Docker missing/corrupt calibration copies | Both fail readiness/forecast with 503; health/UI/reporting survive |
| Non-root/read-only/host restriction | UID 10001, read-only root/runtime mount, actual write rejected, host 127.0.0.1 only |

The 14 service tests include future-sales mutation invariance, strictly pre-origin
inputs, interval alignment and numerical parity with existing frozen outputs.
Regression comparisons are not new performance evaluations. Docker parity used
SKUs 21212, 21166 and 21533 at 2011-06-06 and 2011-11-07, with explicit
`rtol=1e-12`, `atol=1e-9`, covering point values and all four interval endpoints.
Saved reporting payloads also matched their local packaged values exactly.

Final-image Docker evidence:
`reports/generated/demo/docker-smoke-20261107T184518837570Z/results.json` and
`docker-log.json`. Compose recreation-to-healthy took **6,736 ms**, including the
health-check wait. Original readiness loader reported **798.3 ms**; this is artifact
validation/loading time rather than complete process/container startup. Six warm
HTTP forecast requests: median **18.70 ms**, range **17.33–21.27 ms**, including
loopback transport. These small local checks are not load benchmarks.

The initial restricted process sandbox stalled TestClient thread startup; that
attempt was terminated, and the suite passed with the required local-process
access. No application failure was hidden. Routine UI corrections were confined
to the new adapter: unavailable metadata labels, malformed-report handling and
hidden skip-link rendering. No frozen forecasting/evaluation correction occurred.

### Browser and accessibility review

The actual Docker-served interface was checked in the in-app browser at desktop
1280×900, tablet 768×1024 and mobile 390×844. All three views had no document-level
horizontal overflow at the tested widths; narrow numerical tables scroll inside
focusable regions. Native keyboard testing confirmed Tab reaches the submit
button, Enter submits SKU 21166/2011-06-06 and renders 28 dated rows, Enter opens
the numerical table, and the skip link appears on focus and moves to main content.
Scenario filtering at lead 7/penalty 5 showed the existing saved values (including
buffered cost 152,620.93). Browser error/warning logs were empty on the main app.

Disposable containers demonstrated an explicit API-unavailable/retry state and a
corrupt-validation-report state with the final-test card still available. Unit
tests separately cover missing/corrupt reports/manifests and cached report loads.
Loading messages and `aria-busy`/live regions are implemented; no artificial slow
network benchmark or exhaustive assistive-technology certification is claimed.

Representative captures use a fixed presentation rule: default SKU **21212** at
the latest supported origin **2011-11-07**; complete saved evaluation; inventory
default lead **3**/penalty **1**. These are navigation examples, not selected for
favorable model/policy performance. Screenshots are local generated evidence,
kept outside Git:

- `reports/generated/demo/screenshots/forecast-desktop.jpg`
- `reports/generated/demo/screenshots/evaluation-desktop.jpg`
- `reports/generated/demo/screenshots/inventory-desktop.jpg`
- `reports/generated/demo/screenshots/forecast-mobile.jpg`
- `reports/generated/demo/screenshots/forecast-unavailable.jpg`
- `reports/generated/demo/screenshots/evaluation-unavailable.jpg`

Temporary viewport overrides were reset. The Compose stack and disposable test
containers were stopped/removed after verification; Docker Desktop was left running.

## Reproduce locally on Windows

From the repository root, using the preserved environment:

```powershell
.\.venv\Scripts\python.exe -m retail_forecasting.demo --root . --port 8000
# Open http://127.0.0.1:8000/ ; Ctrl+C stops the local server.
```

Or use the existing runtime bundle with Docker Desktop running:

```powershell
docker compose -f demo/compose.yaml build
docker compose -f demo/compose.yaml up -d --wait --wait-timeout 90
Start-Process http://127.0.0.1:8000/
# Existing API docs: http://127.0.0.1:8000/docs
.\.venv\Scripts\python.exe scripts/verify_demo_container.py --container retail-forecasting-demo-local-demo-1
docker compose -f demo/compose.yaml down
```

The smoke checker requires local Docker access; it tests the already running image
and creates/removes disposable failure-test containers. It never performs an
experiment. The checked development Compose project used the explicit name
`retail-forecasting-demo-m11`; the instructions above use the file's default name.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_demo.py -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_service.py -v
.\.venv\Scripts\python.exe ci/run_tests.py
.\.venv\Scripts\python.exe scripts/verify.py
.\.venv\Scripts\python.exe -m pip check
```

The first two test commands require the existing local research artifacts. The
16-test CI command uses committed synthetic fixtures and does not download data.
The original hosted workflow remains unchanged; new demo checks were run locally.
**Hosted GitHub Actions execution remains pending.** No passing hosted run is claimed.

## Limits retained in the interface

This is a historical portfolio demonstration, not a live data service or
production-ready application. There is no live optimization, inventory execution,
authentication, public hosting, load/concurrency benchmark or full browser/screen
reader compatibility audit. Supported dates/SKUs remain fixed. Startup readiness
retains its forecasting-artifact meaning; report availability is section-specific.

Intervals remain empirical, experimental and uneven across products/weekdays.
Daily bounds do not provide simultaneous or total-horizon coverage. Observed
positive sales are not verified uncensored demand. Simulation parameters/costs
are artificial, and simulated comparisons do not establish real business savings.
Final test is consumed and displayed without re-evaluation. Validation remains
development evidence. Attribution is visible in every view: Chen, D. (2012),
[UCI Online Retail II](https://doi.org/10.24432/C5CG6D),
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
