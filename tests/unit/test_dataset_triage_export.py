from __future__ import annotations

from tests.example_support import load_dataset_triage_module

export = load_dataset_triage_module("export")
models = load_dataset_triage_module("models")


def test_build_export_markdown_is_deterministic_and_includes_prompt_transcript_and_notices() -> None:
    markdown = export.build_export_markdown(
        dataset_name="customers.csv.gz",
        analysis_prompt="Summarize the dataset",
        conversation_history=(
            {"role": "user", "text": "Analyze the uploaded dataset."},
            {"role": "assistant", "text": "It looks like a customer export."},
        ),
        load_notices=(models.LoadNotice(level="warning", code="row_limit", message="Profiled only the first 5000 rows."),),
    )

    assert markdown == """# Dataset Triage Export

- Dataset: customers.csv.gz
- Privacy note: this example does not redact prompt or transcript values.

## Loader notices
- [warning] Profiled only the first 5000 rows.

## Prompt sent to Pi

```text
Summarize the dataset
```

## Conversation

### 1. User

Analyze the uploaded dataset.

### 2. Assistant

It looks like a customer export."""


def test_build_export_basename_sanitizes_dataset_names() -> None:
    assert export.build_export_basename("nested/path/customer export.csv.gz") == "customer-export.csv"
    assert export.build_export_basename(None) == "dataset"
