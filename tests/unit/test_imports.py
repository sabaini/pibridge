from __future__ import annotations

import pibridge


def test_package_import_smoke() -> None:
    assert pibridge.PiClient is not None
    assert pibridge.PiClientOptions is not None
