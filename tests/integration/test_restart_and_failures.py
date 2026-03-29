from __future__ import annotations

import time

import pytest

from pi_rpc import PiClient
from tests.integration.conftest import MOCK_MODEL_ID, MOCK_PROVIDER_NAME, _prompt_and_get_text

pytestmark = pytest.mark.integration


def test_idle_restart_after_manual_kill(mock_pi_client: PiClient) -> None:
    first_state = mock_pi_client.get_state()
    process = mock_pi_client._process  # type: ignore[attr-defined]
    child = process._process  # type: ignore[attr-defined]
    assert child is not None
    child.kill()
    time.sleep(0.2)
    second_state = mock_pi_client.get_state()
    assert first_state.session_id
    assert second_state.session_id
    assert second_state.model is not None
    assert second_state.model.provider == MOCK_PROVIDER_NAME
    assert second_state.model.id == MOCK_MODEL_ID
    assert _prompt_and_get_text(mock_pi_client, "Reply with exactly: OK") == "OK"
