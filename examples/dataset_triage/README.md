# Dataset Triage Assistant

A small Streamlit app that profiles an uploaded CSV or gzipped CSV (`.csv.gz`) locally with `pandas`, sends a compact redacted summary to Pi through `pi-rpc-python`, streams Pi's analysis back into the UI, and keeps follow-up questions in the same Pi session.

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

Then upload a CSV such as `examples/dataset_triage/sample_data/customers.csv`, or a gzipped CSV (`.csv.gz`).

## Happy path

1. Upload a CSV or CSV.gz file.
2. Review the preview and compact profile summary.
3. Click **Analyze with Pi** to start a fresh dataset-scoped Pi session.
4. Watch the response stream into the UI.
5. Ask a follow-up question such as `Which three columns should I clean first?`.
   The example uses `prompt(..., streaming_behavior="followUp")`, which is the verified streaming follow-up path in the current compatibility suite.
6. Upload a different file or press **Reset conversation** to start a fresh session.

## What Pi receives

The app does **not** send the full raw dataset by default. It shows the exact prompt in the UI and sends only a bounded summary with:

- dataset dimensions
- duplicate row counts
- dtype overview
- highest-missing columns
- suspicious-column heuristics
- compact numeric highlights
- categorical highlights only for non-sensitive columns
- redacted placeholders plus heuristic notes for likely sensitive columns such as IDs and emails

## Known limits

- CSV and gzip-compressed CSV (`.csv.gz`) only; no Excel, Parquet, or database sources in the MVP
- Heuristics are intentionally lightweight and explainable, not statistically exhaustive
- Very large CSVs may be slow to load locally in Streamlit
- If Pi is unavailable or misconfigured, the app shows a friendly error and allows retrying
