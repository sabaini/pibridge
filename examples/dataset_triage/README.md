# Dataset Triage Assistant

A small Streamlit app that profiles an uploaded CSV or gzipped CSV (`.csv.gz`) locally with `pandas`, sends a compact summary to Pi through `pi-rpc-python`, streams Pi's analysis back into the UI, and keeps follow-up questions in the same Pi session.

## Prerequisites

- Python 3.11+
- `pi` on your `PATH`
- A working Pi model/provider configuration that can answer prompts in RPC mode

## Install

From the repository root, the simplest option is:

```bash
just dataset-triage
```

That command creates `.venv` if needed, installs `.[examples]`, and launches the app.

If you prefer to set things up manually:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e .[examples]
```

If you are also doing repository development, install `.[dev,examples]` instead.

## Run

```bash
just dataset-triage
```

Equivalent direct command after manual setup:

```bash
. .venv/bin/activate
streamlit run examples/dataset_triage/app.py
```

Then upload the bundled sample dataset `examples/dataset_triage/sample_data/co2-emissions-per-capita.csv.gz`, or another CSV / gzipped CSV (`.csv.gz`).

## Happy path

1. Upload a CSV or CSV.gz file.
2. Review the preview and compact profile summary.
3. Click **Analyze with Pi** to start a fresh dataset-scoped Pi session.
4. Watch the response stream into the UI.
5. Optionally adjust parse hints (`delimiter`, `encoding`, `header row`) before or after upload; changing them on the same file reloads the bounded local profile.
6. Ask a follow-up question such as `Which three columns should I clean first?`.
   The example uses `PiClient.continue_prompt()`, which is the recommended helper for the verified streaming follow-up path in the current compatibility suite.
7. Download the bounded prompt/transcript Markdown export or prepare a session HTML export after analysis completes.
8. Upload a different file or press **Reset conversation** to start a fresh session.

## What Pi receives

The app does **not** send the full raw dataset by default. It shows the exact prompt in the UI and sends only a bounded summary with:

- at most the first configured profile rows from the upload when bounded loading is active

- dataset dimensions
- duplicate row counts
- dtype overview
- highest-missing columns
- suspicious-column heuristics
- compact numeric highlights
- categorical highlights

Important: this example does **not** perform privacy redaction. If a value appears in the bounded summary or prompt preview, it may be sent to Pi as-is.

## Known limits

- CSV and gzip-compressed CSV (`.csv.gz`) only; no Excel, Parquet, or database sources in the MVP
- Heuristics are intentionally lightweight and explainable, not statistically exhaustive
- No privacy redaction is performed; bounded prompt contents may still include raw values from the uploaded dataset
- Very large CSVs are intentionally profiled from a bounded first-N subset and the UI warns when the local load is capped
- If Pi is unavailable or misconfigured, the app shows a friendly error and allows retrying
- Session HTML export depends on Pi's `export_html()` command; the app surfaces a friendly error if export fails
