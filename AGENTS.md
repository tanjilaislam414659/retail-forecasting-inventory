# Working agreement

- Work in this repository and preserve existing user files. Do not inspect unrelated
  personal files, credentials, or confidential REWE course data.
- Use public retail data with verified terms. Record official source, attribution,
  license, retrieval date, checksum, and transformations when data is acquired.
- Use `.venv\Scripts\python.exe` on Windows. Never install packages globally or
  change PATH, execution policies, or other global settings. CPU and free tools only.
- Keep code in `src/retail_forecasting`; keep reusable logic out of notebooks.
  Declare dependencies in `pyproject.toml` and pin reproducibility tooling deliberately.
- Keep data, environments, secrets, and generated models out of Git. Preserve `.codex`.
  Do not publish, push, provision paid resources, or send messages without authorization.
- Milestone 7 authorizes one frozen final evaluation of weekday mean, the fixed
  seasonal-naive reference and unchanged experimental historical-error intervals.
  Freeze code/config/input/calibration hashes before accessing final outcomes.
  Preserve prior artifacts, cohort, history mask and scales. Repeat commands must
  verify saved artifacts instead of evaluating again. Log genuine implementation
  corrections after unblinding and preserve original results. No tuning, model
  switching, recalibration, preparation changes, aggregate interval claims,
  weekday-zero rules or API/dashboard work is authorized.
- Use time-ordered splits and rolling-origin evaluation for forecasting. Fit
  transformations on training data only and use only features available at forecast time.
- Treat observed sales separately from latent demand. Label synthetic data,
  inventory assumptions, and simulated results explicitly. Never invent metrics.
- Verify installation with `scripts/verify.py` using the project environment and run
  `python -m pip check`. Add focused tests when substantive data/model logic arrives.
- Explain decisions plainly. Update README and milestone notes to reflect actual
  commands, results, limitations, and the next useful step.
