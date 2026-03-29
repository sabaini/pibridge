from __future__ import annotations

import json
from typing import Any


class JsonlReader:
    """Byte-oriented JSONL reader that splits on LF only."""

    def __init__(self) -> None:
        self._buffer = bytearray()

    def feed(self, chunk: bytes) -> list[str]:
        if not isinstance(chunk, (bytes, bytearray)):
            raise TypeError("chunk must be bytes")
        self._buffer.extend(chunk)
        records: list[str] = []
        while True:
            newline_index = self._buffer.find(b"\n")
            if newline_index < 0:
                break
            line = bytes(self._buffer[:newline_index])
            del self._buffer[: newline_index + 1]
            if line.endswith(b"\r"):
                line = line[:-1]
            records.append(line.decode("utf-8"))
        return records

    def finalize(self) -> list[str]:
        if self._buffer:
            raise ValueError("incomplete JSONL record at end of stream")
        return []


def serialize_json_line(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
