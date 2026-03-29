from __future__ import annotations

import pandas as pd

from tests.example_support import load_dataset_triage_module

profiler = load_dataset_triage_module("profiler")


def test_build_dataset_profile_surfaces_expected_suspicious_columns() -> None:
    frame = pd.DataFrame(
        [
            {"customer_id": "C001", "email": "alice@example.com", "country": "US", "status": "active", "score": 10, "signup_date": "2024-01-01", "order_ref": "ORD-1001"},
            {"customer_id": "C002", "email": None, "country": "us", "status": "active", "score": 11, "signup_date": "2024/01/02", "order_ref": "ORD-1002"},
            {"customer_id": "C003", "email": None, "country": "United States", "status": "active", "score": 9, "signup_date": "01-03-2024", "order_ref": "ORD-1003"},
            {"customer_id": "C004", "email": None, "country": "US", "status": "active", "score": 10, "signup_date": "2024-01-04", "order_ref": "ORD-1004"},
            {"customer_id": "C005", "email": "eve@example.com", "country": None, "status": "active", "score": 9999, "signup_date": "2024-01-05", "order_ref": "ORD-1005"},
            {"customer_id": "C005", "email": "eve@example.com", "country": None, "status": "active", "score": 9999, "signup_date": "2024-01-05", "order_ref": "ORD-1005"},
        ]
    )

    profile = profiler.build_dataset_profile(frame)

    assert profile.rows == 6
    assert profile.columns == 7
    assert profile.duplicate_rows == 1
    assert {column.name for column in profile.columns_profile} == set(frame.columns)
    assert {column.name for column in profile.suspicious_columns} >= {"customer_id", "email", "country", "status", "score", "signup_date", "order_ref"}

    notes_by_column = {column.name: set(column.notes) for column in profile.columns_profile}
    assert any("likely identifier" in note for note in notes_by_column["customer_id"])
    assert any("high missingness" in note for note in notes_by_column["email"])
    assert any("inconsistent casing" in note for note in notes_by_column["country"])
    assert any("low variance" in note for note in notes_by_column["status"])
    assert any("extreme numeric range" in note for note in notes_by_column["score"])
    assert any("looks like datetime text" in note for note in notes_by_column["signup_date"])
    assert any("high-cardinality categorical" in note for note in notes_by_column["order_ref"])

    numeric_summary = profile.numeric_summary["score"]
    assert numeric_summary["max"] == 9999.0
    assert numeric_summary["median"] == 10.5

    assert profile.categorical_top_values["country"][0][0] == "US"
    assert profile.categorical_top_values["country"][0][1] == 2
