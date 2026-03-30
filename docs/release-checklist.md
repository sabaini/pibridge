# Release checklist

Use this checklist before cutting a release or tagging a compatibility update.

## 1. Environment

- [ ] Create/activate a clean virtual environment
- [ ] Install development and example dependencies

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev,examples]'
```

## 2. Automated validation

Run the same commands required by CI:

```bash
ruff check .
mypy src
pytest -m 'not integration'
python -m build
```

Run required integration coverage with a real `pi` binary installed:

```bash
PI_RPC_REQUIRE_INTEGRATION=1 pytest -m integration
```

If you are validating a live backend for the smoke workflow contract, also run:

```bash
PI_RPC_PROVIDER=<provider> PI_RPC_MODEL=<model> PI_RPC_REQUIRE_INTEGRATION=1 pytest -m integration tests/integration/test_live_smoke.py
```

## 3. Dataset-triage example walkthrough

Run the example locally:

```bash
just dataset-triage
```

Verify the following manually:

- [ ] bundled sample dataset loads successfully
- [ ] changing delimiter / encoding / header options on the same file forces a reload
- [ ] large synthetic CSVs show bounded-load warnings before Pi is called
- [ ] prompt preview clearly states when profiling is based on a bounded first-N sample
- [ ] initial analysis streams successfully
- [ ] follow-up questions work through `continue_prompt()` in the same session
- [ ] Markdown transcript download works
- [ ] session HTML export works, or a friendly error is shown when export fails
- [ ] no-redaction warning is still present in the UI/docs

## 4. Documentation

Confirm these documents match the shipped behavior:

- [ ] `README.md`
- [ ] `docs/pi-rpc-python.md`
- [ ] `docs/compatibility-policy.md`
- [ ] `docs/release-checklist.md`
- [ ] `docs/dataset-triage-assistant.md`
- [ ] `examples/dataset_triage/README.md`

## 5. Compatibility / workflow review

- [ ] `.github/workflows/ci.yml` still matches the documented command set
- [ ] `.github/workflows/compat-smoke.yml` still references the intended secret names and runs `tests/integration/test_live_smoke.py` against the configured provider/model pair
- [ ] the current `pi` installation command in CI still works (`npm install -g @mariozechner/pi-coding-agent`)
- [ ] any compatibility-policy changes were reflected in tests first

## 6. Packaging / release notes

- [ ] inspect `dist/` artifacts from `python -m build`
- [ ] summarize notable user-facing changes, including any compatibility-policy updates
- [ ] call out migrations such as the recommended use of `continue_prompt()` for immediate streamed follow-ups
