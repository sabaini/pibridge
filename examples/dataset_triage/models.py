from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd


class DatasetLoadError(ValueError):
    """Raised when an uploaded dataset cannot be loaded safely."""


@dataclass(frozen=True)
class UploadMetadata:
    name: str | None
    content_type: str | None
    size_bytes: int
    fingerprint: str


@dataclass(frozen=True)
class LoadedDataset:
    dataframe: pd.DataFrame
    upload: UploadMetadata


@dataclass(frozen=True)
class ColumnProfile:
    name: str
    dtype: str
    non_null_count: int
    null_count: int
    null_pct: float
    unique_count: int
    sample_values: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    numeric_summary: dict[str, float | int | None] | None = None
    top_values: tuple[tuple[str, int], ...] = ()
    identifier_like: bool = False
    sensitive: bool = False
    share_raw_values: bool = True
    sensitivity_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class DatasetProfile:
    rows: int
    columns: int
    duplicate_rows: int
    numeric_summary: dict[str, dict[str, float | int | None]] = field(default_factory=dict)
    categorical_top_values: dict[str, tuple[tuple[str, int], ...]] = field(default_factory=dict)
    columns_profile: tuple[ColumnProfile, ...] = ()
    suspicious_columns: tuple[ColumnProfile, ...] = ()
    sensitive_columns: tuple[ColumnProfile, ...] = ()
    details: dict[str, Any] = field(default_factory=dict)
