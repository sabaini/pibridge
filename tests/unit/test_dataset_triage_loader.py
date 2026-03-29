from __future__ import annotations

from io import BytesIO

import pytest

pytest.importorskip("pandas")

from tests.example_support import load_dataset_triage_module

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


def test_load_csv_rejects_empty_uploads() -> None:
    with pytest.raises(models.DatasetLoadError, match="empty"):
        loader.load_csv(FakeUpload(b"", name="empty.csv"))


def test_load_csv_rejects_malformed_csv() -> None:
    broken_csv = b'name,quote\nAlice,"unterminated\nBob,ok\n'

    with pytest.raises(models.DatasetLoadError, match="parse"):
        loader.load_csv(FakeUpload(broken_csv, name="broken.csv"))


def test_load_csv_fingerprint_is_stable_for_matching_content() -> None:
    first = loader.load_csv(FakeUpload(b"customer_id,email\n1,a@example.com\n", name="first.csv"))
    second = loader.load_csv(FakeUpload(b"customer_id,email\n1,a@example.com\n", name="second.csv"))
    changed = loader.load_csv(FakeUpload(b"customer_id,email\n1,updated@example.com\n", name="changed.csv"))

    assert first.upload.fingerprint == second.upload.fingerprint
    assert first.upload.fingerprint != changed.upload.fingerprint
    assert first.upload.size_bytes == second.upload.size_bytes
