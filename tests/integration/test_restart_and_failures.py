from __future__ import annotations

import time

import pytest

from pi_rpc import PiClient

pytestmark = pytest.mark.integration


def test_idle_restart_after_manual_kill(pi_client: PiClient) -> None:
    first_state = pi_client.get_state()
    process = pi_client._process  # type: ignore[attr-defined]
    child = process._process  # type: ignore[attr-defined]
    assert child is not None
    child.kill()
    time.sleep(0.2)
    second_state = pi_client.get_state()
    assert first_state.session_id
    assert second_state.session_id
