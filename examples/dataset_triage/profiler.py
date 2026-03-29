from __future__ import annotations

import re
from collections import Counter
from typing import Any

import pandas as pd
from pandas.api.types import is_numeric_dtype, is_object_dtype, is_string_dtype

try:
    from .models import ColumnProfile, DatasetProfile
except ImportError:  # pragma: no cover - supports `streamlit run examples/dataset_triage/app.py`
    from models import ColumnProfile, DatasetProfile


MAX_SAMPLE_VALUES = 3
MAX_TOP_VALUES = 5
MIN_IDENTIFIER_ROWS = 5
HIGH_CARDINALITY_RATIO = 0.8
IDENTIFIER_NAME_TOKENS = (
    "id",
    "uuid",
    "guid",
    "key",
    "ref",
    "reference",
    "account",
    "customer_number",
    "order_number",
)
SENSITIVE_NAME_TOKENS = (
    "email",
    "e-mail",
    "phone",
    "mobile",
    "ssn",
    "tax",
    "passport",
)
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
UUID_PATTERN = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)
ALPHANUMERIC_CODE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
DIGITS_PATTERN = re.compile(r"^\d+$")


def build_dataset_profile(dataframe: pd.DataFrame) -> DatasetProfile:
    duplicate_rows = int(dataframe.duplicated().sum())
    numeric_summary: dict[str, dict[str, float | int | None]] = {}
    categorical_top_values: dict[str, tuple[tuple[str, int], ...]] = {}
    columns_profile: list[ColumnProfile] = []
    suspicious_columns: list[ColumnProfile] = []
    sensitive_columns: list[ColumnProfile] = []

    for column_name in dataframe.columns:
        series = dataframe[column_name]
        non_null = series.dropna()
        non_null_count = int(non_null.shape[0])
        null_count = int(series.isna().sum())
        unique_count = int(non_null.nunique(dropna=True))
        null_pct = round((null_count / len(series)) * 100, 2) if len(series) else 0.0
        sample_values = tuple(_stringify(value) for value in non_null.head(MAX_SAMPLE_VALUES).tolist())
        top_values = _top_values(series)
        numeric_values = _numeric_summary(series)
        identifier_like = _looks_like_identifier(column_name, series, non_null, unique_count)
        sensitivity_reasons = _collect_sensitivity_reasons(column_name, non_null, identifier_like)
        sensitive = bool(sensitivity_reasons)
        notes = _collect_notes(
            column_name,
            series,
            non_null,
            unique_count,
            identifier_like=identifier_like,
            sensitive=sensitive,
        )

        if top_values:
            categorical_top_values[str(column_name)] = top_values
        if numeric_values is not None:
            numeric_summary[str(column_name)] = numeric_values

        column_profile = ColumnProfile(
            name=str(column_name),
            dtype=str(series.dtype),
            non_null_count=non_null_count,
            null_count=null_count,
            null_pct=null_pct,
            unique_count=unique_count,
            sample_values=sample_values,
            notes=tuple(notes),
            numeric_summary=numeric_values,
            top_values=top_values,
            identifier_like=identifier_like,
            sensitive=sensitive,
            share_raw_values=not sensitive,
            sensitivity_reasons=tuple(sensitivity_reasons),
        )
        columns_profile.append(column_profile)
        if notes:
            suspicious_columns.append(column_profile)
        if sensitive:
            sensitive_columns.append(column_profile)

    return DatasetProfile(
        rows=int(dataframe.shape[0]),
        columns=int(dataframe.shape[1]),
        duplicate_rows=duplicate_rows,
        numeric_summary=numeric_summary,
        categorical_top_values=categorical_top_values,
        columns_profile=tuple(columns_profile),
        suspicious_columns=tuple(suspicious_columns),
        sensitive_columns=tuple(sensitive_columns),
        details={
            "duplicate_rows_present": duplicate_rows > 0,
            "sensitive_columns_redacted_by_default": [column.name for column in sensitive_columns],
        },
    )


def _collect_notes(
    column_name: str,
    series: pd.Series[Any],
    non_null: pd.Series[Any],
    unique_count: int,
    *,
    identifier_like: bool,
    sensitive: bool,
) -> list[str]:
    notes: list[str] = []
    non_null_count = int(non_null.shape[0])
    null_pct = (float(series.isna().mean()) * 100.0) if len(series) else 0.0

    if len(series) and null_pct >= 40.0:
        notes.append(f"high missingness ({null_pct:.1f}% null)")

    if identifier_like:
        notes.append("likely identifier column")

    if non_null_count >= 3 and _has_low_variance(non_null):
        notes.append("low variance / nearly constant values")

    if non_null_count >= 3 and _has_inconsistent_casing(non_null):
        notes.append("inconsistent casing in categorical values")

    if non_null_count >= MIN_IDENTIFIER_ROWS and _is_high_cardinality_categorical(series, unique_count, non_null_count):
        notes.append("high-cardinality categorical values")

    if non_null_count >= 4 and _looks_like_datetime_text(series, non_null):
        notes.append("looks like datetime text stored as object/string")

    if non_null_count >= 3 and _has_extreme_numeric_range(series):
        notes.append("extreme numeric range relative to the median")

    if sensitive:
        notes.append("raw values withheld from Pi by default")

    return notes


def _collect_sensitivity_reasons(column_name: str, non_null: pd.Series[Any], identifier_like: bool) -> list[str]:
    reasons: list[str] = []
    if identifier_like:
        reasons.append("identifier-like values")
    if _looks_like_email_column(column_name, non_null):
        reasons.append("email/contact-like values")
    return reasons


def _numeric_summary(series: pd.Series[Any]) -> dict[str, float | int | None] | None:
    if not is_numeric_dtype(series):
        return None
    clean = pd.to_numeric(series.dropna(), errors="coerce").dropna()
    if clean.empty:
        return None
    quantiles = clean.quantile([0.25, 0.5, 0.75])
    return {
        "min": float(clean.min()),
        "p25": float(quantiles.loc[0.25]),
        "median": float(quantiles.loc[0.5]),
        "mean": float(clean.mean()),
        "p75": float(quantiles.loc[0.75]),
        "max": float(clean.max()),
    }


def _top_values(series: pd.Series[Any]) -> tuple[tuple[str, int], ...]:
    if is_numeric_dtype(series):
        return ()
    counts = Counter(_stringify(value) for value in series.dropna().tolist())
    return tuple(counts.most_common(MAX_TOP_VALUES))


def _looks_like_identifier(column_name: str, series: pd.Series[Any], non_null: pd.Series[Any], unique_count: int) -> bool:
    non_null_count = int(non_null.shape[0])
    if non_null_count < MIN_IDENTIFIER_ROWS:
        return False
    if unique_count < max(MIN_IDENTIFIER_ROWS, int(non_null_count * 0.9)):
        return False
    if _looks_like_datetime_text(series, non_null):
        return False

    lowered = column_name.lower().replace("-", "_").replace(" ", "_")
    has_name_signal = any(token in lowered for token in IDENTIFIER_NAME_TOKENS)

    if is_numeric_dtype(series):
        return has_name_signal

    text_values = _non_empty_text_values(non_null)
    if len(text_values) < MIN_IDENTIFIER_ROWS:
        return False

    if _email_match_ratio(text_values) >= 0.8:
        return True

    shape_ratio = _identifier_shape_ratio(text_values)
    if has_name_signal and shape_ratio >= 0.4:
        return True
    return shape_ratio >= 0.85


def _has_low_variance(non_null: pd.Series[Any]) -> bool:
    if non_null.empty:
        return False
    proportions = non_null.astype(str).value_counts(normalize=True, dropna=True)
    return bool(proportions.iloc[0] >= 0.95)


def _has_inconsistent_casing(non_null: pd.Series[Any]) -> bool:
    variants: dict[str, set[str]] = {}
    for value in non_null.astype(str):
        normalized = value.strip().lower()
        variants.setdefault(normalized, set()).add(value.strip())
    return any(len(raw_values) > 1 for raw_values in variants.values() if _has_letters(raw_values))


def _has_letters(raw_values: set[str]) -> bool:
    return any(any(character.isalpha() for character in value) for value in raw_values)


def _is_high_cardinality_categorical(series: pd.Series[Any], unique_count: int, non_null_count: int) -> bool:
    if not (is_object_dtype(series) or is_string_dtype(series)):
        return False
    return (unique_count / non_null_count) >= HIGH_CARDINALITY_RATIO


def _looks_like_datetime_text(series: pd.Series[Any], non_null: pd.Series[Any]) -> bool:
    if not (is_object_dtype(series) or is_string_dtype(series)):
        return False
    parsed = pd.to_datetime(non_null.astype(str), errors="coerce", format="mixed")
    return bool(parsed.notna().mean() >= 0.8)


def _has_extreme_numeric_range(series: pd.Series[Any]) -> bool:
    if not is_numeric_dtype(series):
        return False
    clean = pd.to_numeric(series.dropna(), errors="coerce").dropna()
    if clean.empty:
        return False
    median = float(clean.median())
    scale = max(abs(median), 1.0)
    return (max(abs(float(clean.min())), abs(float(clean.max()))) / scale) >= 50.0


def _looks_like_email_column(column_name: str, non_null: pd.Series[Any]) -> bool:
    text_values = _non_empty_text_values(non_null)
    if not text_values:
        return False
    lowered = column_name.lower()
    match_ratio = _email_match_ratio(text_values)
    return match_ratio >= 0.8 or (any(token in lowered for token in SENSITIVE_NAME_TOKENS) and match_ratio >= 0.5)


def _email_match_ratio(values: list[str]) -> float:
    if not values:
        return 0.0
    matches = sum(1 for value in values if EMAIL_PATTERN.match(value))
    return matches / len(values)


def _identifier_shape_ratio(values: list[str]) -> float:
    if not values:
        return 0.0
    matches = sum(1 for value in values if _looks_like_identifier_value(value))
    return matches / len(values)


def _looks_like_identifier_value(value: str) -> bool:
    stripped = value.strip()
    if not stripped or " " in stripped:
        return False
    if EMAIL_PATTERN.match(stripped) or UUID_PATTERN.match(stripped):
        return True
    if DIGITS_PATTERN.match(stripped):
        return len(stripped) >= 6 or stripped.startswith("0")
    if ALPHANUMERIC_CODE_PATTERN.match(stripped):
        has_letter = any(character.isalpha() for character in stripped)
        has_digit = any(character.isdigit() for character in stripped)
        separators = sum(stripped.count(separator) for separator in ("-", "_", ":", "."))
        return has_letter and (has_digit or separators > 0)
    return False


def _non_empty_text_values(non_null: pd.Series[Any]) -> list[str]:
    values = [str(value).strip() for value in non_null.tolist()]
    return [value for value in values if value]


def _stringify(value: object) -> str:
    if isinstance(value, float):
        return f"{value:.4g}"
    return str(value)
