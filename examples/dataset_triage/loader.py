from __future__ import annotations

import gzip
import hashlib
from io import BytesIO
from typing import Any, BinaryIO

import pandas as pd
from pandas.errors import EmptyDataError, ParserError

try:
    from .models import DatasetLoadError, LoadedDataset, UploadMetadata
except ImportError:  # pragma: no cover - supports `streamlit run examples/dataset_triage/app.py`
    from models import DatasetLoadError, LoadedDataset, UploadMetadata


UploadLike = bytes | bytearray | memoryview | BinaryIO | Any


def load_csv(uploaded_file: UploadLike) -> LoadedDataset:
    raw_bytes = _read_uploaded_bytes(uploaded_file)
    if not raw_bytes:
        raise DatasetLoadError("The uploaded file is empty. Please choose a CSV or CSV.gz file with data.")

    csv_bytes = _maybe_decompress_gzip(raw_bytes)
    if not csv_bytes:
        raise DatasetLoadError("The uploaded file is empty. Please choose a CSV or CSV.gz file with data.")

    metadata = UploadMetadata(
        name=_optional_string(getattr(uploaded_file, "name", None)),
        content_type=_optional_string(getattr(uploaded_file, "type", None)),
        size_bytes=len(raw_bytes),
        fingerprint=hashlib.sha256(csv_bytes).hexdigest(),
    )

    try:
        dataframe = pd.read_csv(BytesIO(csv_bytes), on_bad_lines="error")
    except EmptyDataError as exc:
        raise DatasetLoadError("The uploaded file is empty. Please choose a CSV or CSV.gz file with data.") from exc
    except UnicodeDecodeError as exc:
        raise DatasetLoadError("The uploaded file could not be decoded as text. Please upload a UTF-8 CSV or UTF-8 CSV.gz.") from exc
    except ParserError as exc:
        raise DatasetLoadError(f"CSV parse error: {exc}") from exc
    except ValueError as exc:
        raise DatasetLoadError(f"Could not read the CSV file: {exc}") from exc

    return LoadedDataset(dataframe=dataframe, upload=metadata)


def _read_uploaded_bytes(uploaded_file: UploadLike) -> bytes:
    if isinstance(uploaded_file, bytes):
        return uploaded_file
    if isinstance(uploaded_file, bytearray):
        return bytes(uploaded_file)
    if isinstance(uploaded_file, memoryview):
        return uploaded_file.tobytes()
    if hasattr(uploaded_file, "getvalue"):
        value = uploaded_file.getvalue()
        if isinstance(value, str):
            return value.encode("utf-8")
        if isinstance(value, (bytes, bytearray)):
            return bytes(value)
    if hasattr(uploaded_file, "read"):
        payload = uploaded_file.read()
        if isinstance(payload, str):
            return payload.encode("utf-8")
        if isinstance(payload, (bytes, bytearray)):
            return bytes(payload)
    raise DatasetLoadError("Unsupported upload type. Please provide CSV/CSV.gz bytes or a file-like object.")


def _maybe_decompress_gzip(raw_bytes: bytes) -> bytes:
    if not raw_bytes.startswith(b"\x1f\x8b"):
        return raw_bytes
    try:
        return gzip.decompress(raw_bytes)
    except OSError as exc:
        raise DatasetLoadError("The uploaded .gz file could not be decompressed. Please upload a valid gzip-compressed CSV.") from exc


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) else None
