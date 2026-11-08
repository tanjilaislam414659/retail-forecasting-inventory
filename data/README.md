# Data storage and provenance

Milestone 2 acquired the public UCI Online Retail II workbook. Raw and generated
files stay local and are ignored by Git. Do not place confidential REWE material
or other private data in this project.

Use `data/raw/` for the unchanged ZIP/workbook and `data/processed/` for derived
panels, ledger and audit files. Both are ignored by Git. Commit small
synthetic fixtures only in a clearly named fixture directory if tests need them.

For each public acquisition record the official URL, DOI, author, usage terms,
UTC retrieval timestamp, original filename, byte count, and SHA-256 in a committed
provenance manifest (`docs/data-provenance.json`). Check download size before transferring it; validate workbook
sheets and actual column names before assuming a schema. See
[dataset decision](../docs/dataset-decision.md) for the selected source and attribution.

Customer identifiers are excluded from every generated file. The original public
workbook remains unchanged. See the [preparation protocol](../docs/milestone-2.md)
and [quality report](../docs/data-quality-report.md) for commands and measured results.

Milestone 3 writes a separate modelling view, validation forecasts, scales and
metrics to ignored `data/baselines/`. It does not modify `data/raw/` or
`data/processed/`. The [baseline protocol](../docs/milestone-3.md) documents the
484-row history adjustment and keeps final-test evaluation out of scope.

Milestone 4 adds ignored `data/ridge/` for the single experiment's feature rows,
forecasts, metrics and audit evidence. The fitted pipeline lives separately in
ignored `models/ridge/`. Earlier data and baseline artifacts remain unchanged.
See [Milestone 4](../docs/milestone-4.md).

Milestone 5 reads those saved Ridge rows unchanged and writes ignored
`data/boosting/`, `models/boosting/` and `reports/generated/boosting/`. It does not
regenerate any earlier data/model result or evaluate final test. See
[Milestone 5](../docs/milestone-5.md).

Milestone 6 writes ignored `data/uncertainty/` for historical forecasts/residuals,
fixed group quantiles, daily validation intervals and coverage/width/score tables.
All prior data/models and saved point predictions remain unchanged. See
[Milestone 6](../docs/milestone-6.md). Daily endpoints are not calibrated bounds
for summed 28-day sales.
