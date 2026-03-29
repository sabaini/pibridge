from __future__ import annotations

import pytest

from tests.example_support import load_dataset_triage_module

pd = pytest.importorskip("pandas")

profiler = load_dataset_triage_module("profiler")


def test_build_dataset_profile_surfaces_expected_suspicious_and_sensitive_columns() -> None:
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
    assert {column.name for column in profile.sensitive_columns} == {"customer_id", "email", "order_ref"}

    columns_by_name = {column.name: column for column in profile.columns_profile}
    customer_id = columns_by_name["customer_id"]
    email = columns_by_name["email"]
    signup_date = columns_by_name["signup_date"]
    order_ref = columns_by_name["order_ref"]

    assert customer_id.identifier_like is True
    assert customer_id.sensitive is True
    assert customer_id.share_raw_values is False
    assert "identifier-like values" in customer_id.sensitivity_reasons
    assert any("likely identifier" in note for note in customer_id.notes)
    assert any("raw values withheld" in note for note in customer_id.notes)

    assert email.identifier_like is False
    assert email.sensitive is True
    assert "email/contact-like values" in email.sensitivity_reasons
    assert any("high missingness" in note for note in email.notes)

    assert signup_date.identifier_like is False
    assert signup_date.sensitive is False
    assert any("looks like datetime text" in note for note in signup_date.notes)

    assert order_ref.identifier_like is True
    assert order_ref.sensitive is True

    numeric_summary = profile.numeric_summary["score"]
    assert numeric_summary["max"] == 9999.0
    assert numeric_summary["median"] == 10.5
    assert profile.categorical_top_values["country"][0] == ("US", 2)
    assert profile.details["sensitive_columns_redacted_by_default"] == ["customer_id", "email", "order_ref"]


def test_identifier_heuristics_avoid_small_datasets_and_safe_unique_columns() -> None:
    small_frame = pd.DataFrame(
        [
            {"value": 10, "report_date": "2024-01-01", "city": "Paris"},
            {"value": 11, "report_date": "2024-01-02", "city": "Berlin"},
            {"value": 12, "report_date": "2024-01-03", "city": "Rome"},
            {"value": 13, "report_date": "2024-01-04", "city": "Madrid"},
        ]
    )

    profile = profiler.build_dataset_profile(small_frame)
    columns_by_name = {column.name: column for column in profile.columns_profile}

    assert columns_by_name["value"].identifier_like is False
    assert columns_by_name["value"].sensitive is False
    assert columns_by_name["report_date"].identifier_like is False
    assert columns_by_name["report_date"].sensitive is False
    assert any("looks like datetime text" in note for note in columns_by_name["report_date"].notes)
    assert columns_by_name["city"].identifier_like is False


def test_numeric_identifier_columns_need_name_signal_but_string_codes_can_still_be_detected() -> None:
    frame = pd.DataFrame(
        [
            {"order_id": 10001, "quantity": 1, "reference_code": "RF-10001"},
            {"order_id": 10002, "quantity": 2, "reference_code": "RF-10002"},
            {"order_id": 10003, "quantity": 3, "reference_code": "RF-10003"},
            {"order_id": 10004, "quantity": 4, "reference_code": "RF-10004"},
            {"order_id": 10005, "quantity": 5, "reference_code": "RF-10005"},
        ]
    )

    profile = profiler.build_dataset_profile(frame)
    columns_by_name = {column.name: column for column in profile.columns_profile}

    assert columns_by_name["order_id"].identifier_like is True
    assert columns_by_name["order_id"].sensitive is True
    assert columns_by_name["reference_code"].identifier_like is True
    assert columns_by_name["reference_code"].sensitive is True
    assert columns_by_name["quantity"].identifier_like is False
    assert columns_by_name["quantity"].sensitive is False
