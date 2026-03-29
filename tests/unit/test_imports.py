from __future__ import annotations

import pi_rpc


def test_package_import_smoke() -> None:
    assert pi_rpc.PiClient is not None
    assert pi_rpc.PiClientOptions is not None
