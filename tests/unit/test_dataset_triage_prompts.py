from __future__ import annotations

import pytest

from tests.example_support import load_dataset_triage_module

pd = pytest.importorskip("pandas")

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
    assert "Privacy guardrail" in prompt
    assert "Raw categorical values from likely sensitive columns are redacted by default." in prompt
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
    assert "customer_id: [redacted raw values; unique non-null=5; reason=identifier-like values]" in prompt
    assert "email: [redacted raw values; unique non-null=2; reason=email/contact-like values]" in prompt
    assert "alice@example.com" not in prompt
    assert "C001" not in prompt


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


def test_safe_categorical_highlights_are_prioritized_ahead_of_redacted_sensitive_columns() -> None:
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

    assert "status: active (3), inactive (1), pending (1)" in prompt
    assert "country: US (3), CA (2)" in prompt
