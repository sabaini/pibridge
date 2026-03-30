from __future__ import annotations

import pytest

from tests.example_support import load_dataset_triage_module

pd = pytest.importorskip("pandas")

models = load_dataset_triage_module("models")
profiler = load_dataset_triage_module("profiler")
prompts = load_dataset_triage_module("prompts")


def test_build_initial_analysis_prompt_is_structured_bounded_and_sanitized() -> None:
    frame = pd.DataFrame(
        [
            {"customer_id": "C001", "country": "US", "score": 10, "signup_date": "2024-01-01", "email": "alice@example.com"},
            {"customer_id": "C002", "country": "us", "score": 11, "signup_date": "2024/01/02", "email": None},
            {"customer_id": "C003", "country": "United States", "score": 9, "signup_date": "01-03-2024", "email": None},
            {"customer_id": "C004", "country": "US", "score": 10, "signup_date": "2024-01-04", "email": "eve@example.com"},
            {"customer_id": "C005", "country": None, "score": 10, "signup_date": "2024-01-05", "email": None},
        ]
    )
    profile = profiler.build_dataset_profile(frame)

    prompt = prompts.build_initial_analysis_prompt(profile, dataset_name="customers.csv")

    assert "You are helping triage a CSV dataset." in prompt
    assert "Dataset profile:" in prompt
    assert "Please provide:" in prompt
    assert "1. A short overview" in prompt
    assert "2. The top 3-5 data quality concerns" in prompt
    assert "3. Recommended cleanup steps." in prompt
    assert "4. If useful, example pandas code" in prompt
    assert "customers.csv" in prompt
    assert "rows: 5" in prompt
    assert "duplicate rows: 0" in prompt
    assert "country: US (2), us (1), United States (1)" in prompt
    assert "customer_id: C001 (1), C002 (1), C003 (1), C004 (1), C005 (1)" in prompt
    assert "email: alice@example.com (1), eve@example.com (1)" in prompt


def test_build_initial_analysis_prompt_truncates_wide_schema_and_long_categorical_values() -> None:
    long_value = "very-long-category-value-" * 4
    frame = pd.DataFrame(
        [
            {**{f"column_{index}": index for index in range(14)}, "category": long_value},
            {**{f"column_{index}": index + 1 for index in range(14)}, "category": long_value.lower()},
            {**{f"column_{index}": index + 2 for index in range(14)}, "category": "short"},
        ]
    )
    profile = profiler.build_dataset_profile(frame)

    prompt = prompts.build_initial_analysis_prompt(profile, dataset_name="wide.csv")

    assert "column_0 (int64)" in prompt
    assert "column_11 (int64)" in prompt
    assert "column_12 (int64)" not in prompt
    assert "+ 3 more columns omitted" in prompt
    assert long_value not in prompt
    assert "very-long-category-value-very-long-c..." in prompt


def test_build_initial_analysis_prompt_adds_sample_caveat_when_profile_is_bounded() -> None:
    frame = pd.DataFrame(
        [
            {"customer_id": "C001", "country": "US", "status": "active"},
            {"customer_id": "C002", "country": "us", "status": "active"},
            {"customer_id": "C003", "country": "US ", "status": "active"},
        ]
    )
    profile = profiler.build_dataset_profile(frame)
    load_metadata = models.CsvLoadMetadata(
        options=models.CsvLoadOptions(max_rows=3),
        loaded_rows=3,
        row_limit=3,
        truncated=True,
        notices=(models.LoadNotice(level="warning", code="row_limit", message="Profiled only the first 3 rows."),),
    )

    prompt = prompts.build_initial_analysis_prompt(profile, dataset_name="sampled.csv", load_metadata=load_metadata)

    assert "Dataset profile is based on the first 3 rows only" in prompt
    assert "sampled.csv" in prompt


def test_categorical_highlights_are_shared_without_redaction() -> None:
    frame = pd.DataFrame(
        [
            {
                "customer_id": "C001",
                "email": "alice@example.com",
                "order_ref": "ORD-1001",
                "external_id": "EXT-1",
                "session_id": "SESSION-1",
                "status": "active",
                "country": "US",
            },
            {
                "customer_id": "C002",
                "email": "bob@example.com",
                "order_ref": "ORD-1002",
                "external_id": "EXT-2",
                "session_id": "SESSION-2",
                "status": "inactive",
                "country": "CA",
            },
            {
                "customer_id": "C003",
                "email": "carol@example.com",
                "order_ref": "ORD-1003",
                "external_id": "EXT-3",
                "session_id": "SESSION-3",
                "status": "active",
                "country": "US",
            },
            {
                "customer_id": "C004",
                "email": "dave@example.com",
                "order_ref": "ORD-1004",
                "external_id": "EXT-4",
                "session_id": "SESSION-4",
                "status": "active",
                "country": "CA",
            },
            {
                "customer_id": "C005",
                "email": "eve@example.com",
                "order_ref": "ORD-1005",
                "external_id": "EXT-5",
                "session_id": "SESSION-5",
                "status": "pending",
                "country": "US",
            },
        ]
    )
    profile = profiler.build_dataset_profile(frame)

    prompt = prompts.build_initial_analysis_prompt(profile, dataset_name="budget.csv")

    assert "customer_id: C001 (1), C002 (1), C003 (1), C004 (1), C005 (1)" in prompt
    assert "email: alice@example.com (1), bob@example.com (1), carol@example.com (1), dave@example.com (1), eve@example.com (1)" in prompt
    assert "identifier-like values" in prompt
    assert "[redacted raw values" not in prompt
