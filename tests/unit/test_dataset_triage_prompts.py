from __future__ import annotations

import pandas as pd

from tests.example_support import load_dataset_triage_module

profiler = load_dataset_triage_module("profiler")
prompts = load_dataset_triage_module("prompts")


def test_build_initial_analysis_prompt_is_structured_and_bounded() -> None:
    frame = pd.DataFrame(
        [
            {"customer_id": "C001", "country": "US", "score": 10, "signup_date": "2024-01-01", "email": "alice@example.com"},
            {"customer_id": "C002", "country": "us", "score": 11, "signup_date": "2024/01/02", "email": None},
            {"customer_id": "C003", "country": "United States", "score": 9, "signup_date": "01-03-2024", "email": None},
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
    assert "rows: 3" in prompt
    assert "duplicate rows: 0" in prompt
    assert "country" in prompt
    assert "score" in prompt
    assert "Do not invent metrics" in prompt
    assert "alice@example.com,US" not in prompt


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
