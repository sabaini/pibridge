from __future__ import annotations

import time

import pytest

from pi_rpc import PiClient
from tests.integration.conftest import MOCK_MODEL_ID, MOCK_PROVIDER_NAME, _prompt_and_get_text, _wait_for_agent_end

pytestmark = pytest.mark.integration


@pytest.fixture
def mock_prompt_map() -> dict[str, object]:
    return {
        "Reply with exactly: OK": "OK",
        "Slow abort prompt": {"chunks": ["partial ", "tail"], "delayMs": 300, "waitForAbort": True},
        "Fail mid stream": {"chunks": ["partial"], "errorAfterChunks": 1, "errorMessage": "mock failure"},
    }


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


def test_abort_stops_an_active_stream_and_preserves_partial_text(mock_pi_client: PiClient) -> None:
    subscription = mock_pi_client.subscribe_events(maxsize=300)

    mock_pi_client.prompt("Slow abort prompt")

    while True:
        event = subscription.get(timeout=30)
        if event.type != "message_update":
            continue
        assistant_event = event.assistant_message_event
        if assistant_event.type != "text_delta":
            continue
        mock_pi_client.abort()
        break

    _wait_for_agent_end(subscription)
    messages = mock_pi_client.get_messages()
    assistant = messages[-1]

    assert mock_pi_client.get_last_assistant_text() == "partial"
    assert assistant.role == "assistant"
    assert assistant.stop_reason == "aborted"


def test_stream_failure_ends_the_turn_and_client_can_continue(mock_pi_client: PiClient) -> None:
    subscription = mock_pi_client.subscribe_events(maxsize=300)

    mock_pi_client.prompt("Fail mid stream")
    _wait_for_agent_end(subscription)

    messages = mock_pi_client.get_messages()
    assistant = messages[-1]

    assert assistant.role == "assistant"
    assert assistant.stop_reason == "error"
    assert assistant.error_message == "mock failure"
    assert mock_pi_client.get_last_assistant_text() == "partial"
    assert _prompt_and_get_text(mock_pi_client, "Reply with exactly: OK") == "OK"
