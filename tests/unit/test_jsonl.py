from __future__ import annotations

import io
import json

import pytest

from pi_rpc.jsonl import JsonlReader, serialize_json_line


def test_jsonl_reader_accepts_crlf_and_partial_chunks() -> None:
    reader = JsonlReader()
    assert reader.feed(b'{"a":1}\r') == []
    assert reader.feed(b'\n{"b":2}\n') == ['{"a":1}', '{"b":2}']
    assert reader.finalize() == []


def test_jsonl_reader_handles_utf8_multibyte_boundaries() -> None:
    payload = {"text": "pi 🧪"}
    data = serialize_json_line(payload)
    split = data.index("🧪".encode()) + 2
    reader = JsonlReader()
    assert reader.feed(data[:split]) == []
    records = reader.feed(data[split:])
    assert [json.loads(record) for record in records] == [payload]


@pytest.mark.parametrize("separator", ["\u2028", "\u2029"])
def test_jsonl_reader_does_not_split_on_unicode_separators(separator: str) -> None:
    payload = {"text": f"hello{separator}world"}
    data = serialize_json_line(payload)
    reader = JsonlReader()
    records = reader.feed(data)
    assert [json.loads(record) for record in records] == [payload]


def test_serialize_json_line_round_trip_via_bytesio() -> None:
    payloads = [{"a": 1}, {"text": "hello"}]
    pipe = io.BytesIO(b"".join(serialize_json_line(payload) for payload in payloads))
    reader = JsonlReader()
    records = reader.feed(pipe.read())
    assert [json.loads(record) for record in records] == payloads


def test_jsonl_reader_finalize_rejects_incomplete_record() -> None:
    reader = JsonlReader()
    reader.feed(b'{"a":1}')
    with pytest.raises(ValueError):
        reader.finalize()
