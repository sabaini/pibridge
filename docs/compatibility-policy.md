# Compatibility policy

## Summary

`pi-rpc-python` does not rely on a version-negotiation handshake. Compatibility is defined by the repository's automated checks and the behavior they exercise against the upstream `pi --mode rpc` CLI.

## Supported contract

The repository currently treats the following as the supported compatibility contract:

- Python: 3.11+
- Pi install path used by required CI on Ubuntu runners: `npm install -g @mariozechner/pi-coding-agent`
- Required upstream behavior:
  - the full typed command/response/event surface covered by unit tests
  - the mock-backed integration suite in `tests/integration/`
  - real-subprocess public-API contract checks for command dispatch, lifecycle, subscriptions, auto-retry controls, and accumulated bash context
  - the recommended immediate streamed follow-up path exposed as `PiClient.continue_prompt()`
  - the RPC-safe extension UI request/response flow exercised by `tests/integration/test_extension_ui.py`
  - end-to-end smoke runs for the shipped `examples/*.py` scripts and the Streamlit dataset-triage app
  - installed-wheel smoke from `tests/packaging/install_smoke.py`, executed from a clean virtualenv/cwd instead of the source tree

This policy is intentionally explicit: if the CI install path or verified upstream behavior changes, update this document, the workflows, and the affected tests together.

## Test tiers

### Required CI tier

`.github/workflows/ci.yml` is the required gate for pull requests and mainline changes. It runs:

- `ruff check .`
- `mypy src`
- `pytest -m 'not integration'`
- `python -m build`
- `python tests/packaging/install_smoke.py`
- `PI_RPC_REQUIRE_INTEGRATION=1 pytest -m integration`

The integration job uses the bundled mock provider fixture by default, so external model credentials are not required for the required compatibility gate. That required integration tier now includes the example smoke suite, the dataset-triage `AppTest` workflow, and the extension/auto-retry-control/subscription contract tests.

### Optional live smoke tier

`.github/workflows/compat-smoke.yml` is an opt-in manual/scheduled workflow for one real provider/model pair. It runs `tests/integration/test_live_smoke.py` against a `live_pi_client`, so it exercises the configured backend instead of the bundled mock fixture. It is not the primary compatibility contract, but it is the early-warning signal for backend drift that mock fixtures cannot catch.

## Command-behavior policy

The package keeps the public low-level RPC methods intact, including `prompt()`, `follow_up()`, and `steer()`.

For immediate streamed follow-ups, the documented and tested recommendation is:

- use `PiClient.continue_prompt()`
- treat `follow_up()` and `steer()` as lower-level protocol-faithful calls whose runtime behavior may remain queue-oriented on supported upstream builds

If upstream Pi changes those semantics, update the integration tests and documentation before claiming expanded behavior.

## Unsupported / deferred areas

The following are still out of scope for the supported contract:

- TUI-only extension APIs such as `ctx.ui.custom()` and direct terminal component hooks that are not represented in RPC
- async-native Python APIs
- undocumented example knobs beyond the shared `PI_RPC_EXAMPLE_*` runtime overrides used by the shipped example scripts
- protocol behavior that is not exercised by the repository's tests

## Updating the policy

When changing the supported contract:

1. update the workflows
2. update this document and the README
3. update integration coverage first
4. rerun the release checklist in `docs/release-checklist.md`
