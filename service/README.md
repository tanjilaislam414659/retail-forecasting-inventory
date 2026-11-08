# Local historical forecasting API — service 0.1.0

This is a separately versioned engineering layer around the frozen weekday-mean
release, not a live retail service. See `docs/milestone-8.md` for measured checks,
timings, artifact preservation and operating limitations. Earlier root packaging,
README, code, configurations and evaluation results remain byte-identical.

From the repository root in Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pip install -r service/requirements-lock.txt
.\.venv\Scripts\python.exe -m pip install --no-build-isolation --no-deps -e ./service
.\.venv\Scripts\python.exe -m retail_forecasting.service --root . --port 8000
```

The launcher always binds to **127.0.0.1**, with one worker and no reload. It loads
verified processed history/calibration once per lifespan. It never downloads,
parses the workbook, fits, recalibrates or regenerates evaluation artifacts.

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/ready
Invoke-RestMethod http://127.0.0.1:8000/metadata
$body = @{sku="21212"; origin="2011-11-07"; horizon_days=28} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/forecast -ContentType "application/json" -Body $body
```

API docs: http://127.0.0.1:8000/docs (Swagger UI) or `/redoc`.
The machine-readable schema at `/openapi.json` works without loading external
browser assets; interactive Swagger/ReDoc assets use their standard external CDNs.
Only `/forecast` is POST. Unknown SKUs, unsupported origins/horizons, non-ISO dates,
incorrect types and extra JSON fields return 422 with structured errors. Health is
independent of artifacts. Missing/corrupt artifacts leave health at 200 but return
503 for ready/metadata/forecast. Restart after repairing artifacts; there is no
automatic reload or fallback. Server logs show the safe artifact error code.

Responses contain 28 daily point forecasts, experimental 80%/95% daily bounds,
history cutoff, service version, release/calibration IDs and demonstration labels.
They contain no target actuals or customer identifiers. No rounding, point
containment rule, Saturday rule or aggregate interval claim is added.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts/verify_service_parity.py
.\.venv\Scripts\python.exe scripts/smoke_local_api.py
```

Parity verifies numbers against saved artifacts with explicit tolerances; it
does not calculate performance metrics or perform a second final evaluation.
The smoke script starts and stops its own loopback-only server on an available
port, preserving any existing process. Outputs are ignored under
`reports/generated/service/`. Keep both the public processed inputs and pinned
`service/artifact-contract.json`; the repository does not redistribute data in Git.

This is a local portfolio demonstration, not production-ready. It has no live
ingestion, authentication, rate limiting, multi-worker coordination or inventory
decision engine. Observed sales are not latent demand. Interval coverage is
experimental, particularly weak for some SKUs/weekdays; no joint, total-sales,
conformal or finite-sample coverage guarantee is made.
