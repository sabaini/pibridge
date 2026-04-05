from __future__ import annotations

import os

import pytest

from pi_rpc import PiClient
from tests.integration.conftest import MOCK_MODEL_ID, MOCK_PROVIDER_NAME, _live_override_enabled, _wait_for_agent_end

pytestmark = pytest.mark.integration


LIVE_TOKEN_ALPHA = "LIVE-SMOKE-ALPHA"
LIVE_TOKEN_BETA = "LIVE-SMOKE-BETA"


def test_smoke_prompt_and_continue_prompt_exercise_configured_backend(smoke_pi_client: PiClient) -> None:
    subscription = smoke_pi_client.subscribe_events(maxsize=300)

    smoke_pi_client.prompt(f"Reply with a short sentence that includes the exact token {LIVE_TOKEN_ALPHA}.")
    _wait_for_agent_end(subscription)
    first_text = smoke_pi_client.get_last_assistant_text()
    assert first_text is not None
    assert LIVE_TOKEN_ALPHA in first_text.upper()

    first_state = smoke_pi_client.get_state()

    smoke_pi_client.continue_prompt(f"Reply with a short sentence that includes the exact token {LIVE_TOKEN_BETA}.")
    _wait_for_agent_end(subscription)
    second_text = smoke_pi_client.get_last_assistant_text()
    assert second_text is not None
    assert LIVE_TOKEN_BETA in second_text.upper()

    second_state = smoke_pi_client.get_state()
    assert second_state.session_id == first_state.session_id
    assert second_state.model is not None
    if _live_override_enabled():
        assert second_state.model.provider == os.environ["PI_RPC_PROVIDER"]
        assert second_state.model.id == os.environ["PI_RPC_MODEL"]
    else:
        assert second_state.model.provider == MOCK_PROVIDER_NAME
        assert second_state.model.id == MOCK_MODEL_ID
