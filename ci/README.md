# Explicit routine CI scope

Run `python ci/run_tests.py` after installing the runtime wheel and its test
dependencies. Required tests fail if any test is skipped or fewer than 16 run.
`test_api.py`, `test_inference.py` and `test_bundle.py` use only small synthetic
fixtures in this directory. `fixtures/manifest.json` records their provenance and
hashes. No UCI data, customers, ignored runtime bundles or historical experiments
are inputs. The artificial quantiles are not calibrated and must never be used as
production artifacts; the production contract/native loader remains unchanged.

Coverage: arithmetic, origin availability/future-mutation invariance, calendar and
interval constraints, valid/invalid HTTP contracts, liveness/readiness behavior,
no-I/O request handling, safe logs and envelope integrity/path safety. Missing
production-contract handling uses the real loader; the small injected test engine
does not exercise every semantic check of the real 100-SKU dataset loader.

Full-data integration/parity lives separately in `scripts/verify_runtime_bundle.py`
and `scripts/verify_service_parity.py`. Actual Docker checks require Docker/daemon
and `scripts/verify_container.py`. Routine Actions intentionally does not execute
the dataset-dependent `tests/test_service.py` or the full research test suite;
these are not silently skipped by discovery. Hosted execution is pending until
the user publishes/runs the prepared workflow.
# Milestone 12 update

Routine CI now has separate **runtime** and **demo** matrix environments. Run
`python ci/run_tests.py --package runtime` for 16 synthetic core/API/bundle tests,
or `python ci/run_tests.py --package demo` for those 16 plus eight synthetic demo
tests. The demo additions use `ci/fixtures/demo/`, explicitly handcrafted reporting
values, and the existing two-SKU synthetic inference engine. They do not load UCI
data, original customer records or ignored experiment outputs. Required failures,
skips and too few tests fail the run.

`ci/check_installed_demo.py` verifies installed HTML/CSS/JavaScript/report assets
and unchanged inference code identities. `ci/check_installed_package.py` retains
the original runtime-wheel check. These distributions overlap in their Python
namespace and are installed in separate environments, not on top of one another.
Local clean-clone evidence and scope are in `docs/milestone-12.md`; hosted GitHub
Actions execution remains pending.
