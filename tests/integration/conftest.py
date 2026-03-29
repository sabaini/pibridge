from __future__ import annotations

import os
import shutil
from collections.abc import Iterator

import pytest

from pi_rpc import PiClient, PiClientOptions

REQUIRED_ENV_VARS = ["PI_RPC_INTEGRATION", "PI_RPC_PROVIDER", "PI_RPC_MODEL"]


def _integration_ready() -> tuple[bool, str]:
    if os.environ.get("PI_RPC_INTEGRATION") != "1":
        return False, "set PI_RPC_INTEGRATION=1 to run real pi integration tests"
    if shutil.which("pi") is None:
        return False, "pi executable not found on PATH"
    missing = [name for name in REQUIRED_ENV_VARS[1:] if not os.environ.get(name)]
    if missing:
        return False, f"missing required env vars: {', '.join(missing)}"
    return True, ""


@pytest.fixture(scope="session")
def integration_ready() -> None:
    ready, reason = _integration_ready()
    if not ready:
        pytest.skip(reason)


@pytest.fixture
def pi_client(integration_ready: None) -> Iterator[PiClient]:
    options = PiClientOptions(
        provider=os.environ["PI_RPC_PROVIDER"],
        model=os.environ["PI_RPC_MODEL"],
        command_timeout=float(os.environ.get("PI_RPC_COMMAND_TIMEOUT", "120")),
    )
    with PiClient(options) as client:
        yield client
