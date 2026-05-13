from __future__ import annotations

import picable


def test_package_import_smoke() -> None:
    assert picable.PiClient is not None
    assert picable.PiClientOptions is not None
