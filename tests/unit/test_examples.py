from __future__ import annotations

import pathlib


def test_examples_compile() -> None:
    for path in pathlib.Path("examples").rglob("*.py"):
        compile(path.read_text(), str(path), "exec")
