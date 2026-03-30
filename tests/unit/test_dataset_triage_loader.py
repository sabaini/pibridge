from __future__ import annotations

import gzip
from io import BytesIO

import pytest

from tests.example_support import load_dataset_triage_module

pytest.importorskip("pandas")

loader = load_dataset_triage_module("loader")
models = load_dataset_triage_module("models")


class FakeUpload(BytesIO):
    def __init__(self, content: bytes, *, name: str = "customers.csv", content_type: str = "text/csv") -> None:
        super().__init__(content)
        self.name = name
        self.type = content_type
        self.size = len(content)

    def getvalue(self) -> bytes:
        return super().getvalue()


@pytest.mark.parametrize(
    ("factory", "expected_name"),
    [
        (lambda: FakeUpload(b"customer_id,email\n1,a@example.com\n2,b@example.com\n"), "customers.csv"),
        (
            lambda: FakeUpload(
                gzip.compress(b"customer_id,email\n1,a@example.com\n2,b@example.com\n"),
                name="customers.csv.gz",
                content_type="application/gzip",
            ),
            "customers.csv.gz",
        ),
        (lambda: b"customer_id,email\n1,a@example.com\n2,b@example.com\n", None),
    ],
)
def test_load_csv_parses_valid_inputs(factory, expected_name: str | None) -> None:
    loaded = loader.load_csv(factory())

    assert loaded.dataframe.shape == (2, 2)
    assert list(loaded.dataframe.columns) == ["customer_id", "email"]
    assert loaded.upload.name == expected_name
    assert loaded.upload.size_bytes > 0
    assert loaded.upload.fingerprint
    assert loaded.load.options.separator == ","
    assert loaded.load.truncated is False
    assert loaded.load.notices == ()


def test_load_csv_parses_alternate_separator_encoding_and_headerless_input() -> None:
    latin1_csv = "1;Jos\xe9\n2;Ana\n".encode("latin-1")

    loaded = loader.load_csv(
        FakeUpload(latin1_csv, name="customers.csv"),
        options=models.CsvLoadOptions(separator=";", encoding="latin-1", has_header=False),
    )

    assert loaded.dataframe.shape == (2, 2)
    assert list(loaded.dataframe.columns) == [0, 1]
    assert loaded.dataframe.iloc[0, 1] == "José"
    assert loaded.load.options.has_header is False


def test_load_csv_rejects_empty_uploads() -> None:
    with pytest.raises(models.DatasetLoadError, match="empty"):
        loader.load_csv(FakeUpload(b"", name="empty.csv"))


def test_load_csv_rejects_malformed_csv() -> None:
    broken_csv = b'name,quote\nAlice,"unterminated\nBob,ok\n'

    with pytest.raises(models.DatasetLoadError, match="parse"):
        loader.load_csv(FakeUpload(broken_csv, name="broken.csv"))


def test_load_csv_rejects_invalid_gzip_uploads() -> None:
    with pytest.raises(models.DatasetLoadError, match="decompressed"):
        loader.load_csv(FakeUpload(b"\x1f\x8bnot-really-gzip", name="broken.csv.gz", content_type="application/gzip"))


def test_load_csv_fingerprint_is_stable_for_matching_content() -> None:
    first = loader.load_csv(FakeUpload(b"customer_id,email\n1,a@example.com\n", name="first.csv"))
    second = loader.load_csv(FakeUpload(b"customer_id,email\n1,a@example.com\n", name="second.csv"))
    gzipped = loader.load_csv(FakeUpload(gzip.compress(b"customer_id,email\n1,a@example.com\n"), name="second.csv.gz", content_type="application/gzip"))
    changed = loader.load_csv(FakeUpload(b"customer_id,email\n1,updated@example.com\n", name="changed.csv"))

    assert first.upload.fingerprint == second.upload.fingerprint
    assert first.upload.fingerprint == gzipped.upload.fingerprint
    assert first.upload.fingerprint != changed.upload.fingerprint
    assert first.upload.size_bytes == second.upload.size_bytes
    assert first.load_signature != second.load_signature
    assert second.load_signature != gzipped.load_signature


def test_load_csv_applies_row_caps_and_emits_bounded_load_notices() -> None:
    rows = ["customer_id,email"] + [f"{index},user{index}@example.com" for index in range(6)]
    csv_payload = "\n".join(rows).encode("utf-8")

    loaded = loader.load_csv(
        FakeUpload(csv_payload, name="large.csv"),
        options=models.CsvLoadOptions(max_rows=3, large_file_warning_bytes=10),
    )

    assert loaded.dataframe.shape == (3, 2)
    assert loaded.load.loaded_rows == 3
    assert loaded.load.row_limit == 3
    assert loaded.load.truncated is True
    assert [notice.code for notice in loaded.load.notices] == ["row_limit", "large_file"]
