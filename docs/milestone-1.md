# Milestone 1: foundation verification

Completed locally on **2026-11-01**. No retail dataset download, model training,
paid resource provisioning, or GitHub publication was performed.

## Inspection and environment

- Initial folder listing contained only `.codex/`. It was preserved and excluded
  from Git; no existing project source files were overwritten.
- No applicable `AGENTS.md` was found in this folder or its ancestor directories.
  The new repository agreement is now in `AGENTS.md`.
- Git: **2.51.2.windows.1**. No repository existed initially. Initialized local
  branch `main`; no commits or remotes exist yet. Git identity was not changed.
- `python` resolved to an unusable WindowsApps shortcut; `py --list` reported no
  installed Python. A targeted check of standard Python installation paths found
  a working **CPython 3.13.5** in
  `<installed-python-3.13.exe>`.
- Created `.venv/` from that interpreter. Installed **pip 25.1.1**,
  **setuptools 80.9.0**, **wheel 0.45.1**, and **retail-forecasting 0.1.0** there.
  The application currently has no runtime dependencies.
- No global Python packages, PATH, system settings, execution policy, or Git
  configuration were changed. No confidential course data was accessed.

## Routine setup problems resolved

The coding-agent sandbox denied Python/pip access to temporary files and blocked
PyPI DNS resolution. Approved execution outside the sandbox completed `ensurepip`,
the two small packaging-tool downloads, and local package verification. The local
package installation and wheel checks used `--no-index --no-build-isolation
--no-deps`; they did not access the network. Ordinary VS Code terminal commands
are documented in README. No dataset was fetched as a workaround.

## Checks and observed results

| Check | Result |
| --- | --- |
| Editable installation using pip | Successfully installed `retail-forecasting 0.1.0` into `.venv`. |
| `.venv\Scripts\python.exe -m retail_forecasting check` | `status: ok`, `virtual_environment: true`, Python 3.13.5. |
| `.venv\Scripts\python.exe scripts\verify.py` | PASS for installed module, console command, version, and environment isolation. Commands run from a temporary directory; the module check uses `-I`. |
| `.venv\Scripts\python.exe -m pip check` | `No broken requirements found.` |
| pip wheel build with no dependencies or index | Built `dist/retail_forecasting-0.1.0-py3-none-any.whl`. |
| Wheel installed into fresh `.cache/wheel-check/` environment | Installation succeeded; the same verification script passed using that environment's Python. It is a regular wheel installation, with no editable source dependency. |
| `git check-ignore` with representative paths | Environment, `.codex`, verification cache, wheel, raw/processed data, and `.env` were ignored. Application source and `data/README.md` were not ignored. |
| Git state | Local `main`, no commits, no remote. Generated environments and artifacts absent from normal status output. |

Wheel SHA-256 at verification:

```text
1663a6294df99c8cadfe0d5b032c647f5522aed56f21f5e72b8ceb03bc75a994
```

These are installation smoke checks. No forecasting accuracy, ingestion memory,
training speed, or inventory benefit has been measured. Compatibility was exercised
on this Windows machine with Python 3.13.5; other declared Python versions have not
yet been tested.

## Dataset decision and next milestone

Compared UCI Online Retail, UCI Online Retail II, and M5 using official publisher
and organizer material. Selected **UCI Online Retail II**: explicit CC BY 4.0 terms,
two years of transactions, and a manageable initial scope. Access checks covered
published metadata and download links; no full download or workbook validation was
attempted. M5's current access requirements and reuse terms remain unresolved.
See [the decision record](dataset-decision.md) for sources and limitations.

Next milestone: acquire the selected public workbook with provenance and checksum;
validate sheets and actual schema; audit transaction quality; define sales and
returns handling; construct a bounded daily SKU panel and chronological splits.
Deliver a reproducible ingestion command and an honest data-quality report before
starting model training.
