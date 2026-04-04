from __future__ import annotations

import queue

import pytest

from pi_rpc import PiClient
from pi_rpc.events import QueueUpdateEvent
from tests.integration.conftest import _prompt_and_get_text, _wait_for_agent_end, _wait_for_event, mock_assistant_message, mock_context_key, mock_user_message

pytestmark = pytest.mark.integration


def test_prompt_streams_expected_canned_answer(mock_pi_client: PiClient) -> None:
    assert _prompt_and_get_text(mock_pi_client, "Reply with exactly: OK") == "OK"


@pytest.fixture
def mock_context_map() -> dict[str, object]:
    return {
        mock_context_key(
            mock_user_message("Respond with the word BRIDGE."),
            mock_assistant_message("BRIDGE"),
            mock_user_message("Repeat the previous assistant response exactly."),
        ): "BRIDGE",
        mock_context_key(
            mock_user_message("Respond with the word BRIDGE."),
            mock_assistant_message("BRIDGE"),
            mock_user_message("Use the verified follow-up path."),
        ): "FOLLOW-UP",
    }


@pytest.fixture
def mock_prompt_map() -> dict[str, object]:
    return {
        "Reply with exactly: OK": "OK",
        "Respond with the word BRIDGE.": "BRIDGE",
        "Stream slowly so we can queue steering.": {"chunks": ["hello ", "world"], "delayMs": 300, "waitForAbort": True},
    }


def test_multiple_prompts_return_matching_canned_answers(mock_pi_client: PiClient) -> None:
    assert _prompt_and_get_text(mock_pi_client, "Respond with the word BRIDGE.") == "BRIDGE"
    assert _prompt_and_get_text(mock_pi_client, "Repeat the previous assistant response exactly.") == "BRIDGE"


def test_prompt_follow_up_streaming_behavior_reuses_context(mock_pi_client: PiClient) -> None:
    subscription = mock_pi_client.subscribe_events(maxsize=300)

    mock_pi_client.prompt("Respond with the word BRIDGE.")
    _wait_for_agent_end(subscription)

    mock_pi_client.prompt("Use the verified follow-up path.", streaming_behavior="followUp")
    _wait_for_agent_end(subscription)

    assert mock_pi_client.get_last_assistant_text() == "FOLLOW-UP"


def test_continue_prompt_reuses_context_and_streams_immediately(mock_pi_client: PiClient) -> None:
    subscription = mock_pi_client.subscribe_events(maxsize=300)

    mock_pi_client.prompt("Respond with the word BRIDGE.")
    _wait_for_agent_end(subscription)

    mock_pi_client.continue_prompt("Use the verified follow-up path.")
    _wait_for_agent_end(subscription)

    assert mock_pi_client.get_last_assistant_text() == "FOLLOW-UP"


def test_steer_queues_a_pending_message_during_active_stream(mock_pi_client: PiClient) -> None:
    subscription = mock_pi_client.subscribe_events(maxsize=300)

    mock_pi_client.prompt("Stream slowly so we can queue steering.")

    while True:
        event = subscription.get(timeout=30)
        if event.type != "message_update":
            continue
        assistant_event = event.assistant_message_event
        if assistant_event.type != "text_delta":
            continue
        mock_pi_client.steer("Prefer concise wording.")
        state = mock_pi_client.get_state()
        assert state.is_streaming is True
        assert state.pending_message_count == 1
        mock_pi_client.abort()
        break

    _wait_for_agent_end(subscription)
    assert mock_pi_client.get_last_assistant_text() == "hello"


def test_follow_up_command_currently_queues_pending_work_without_immediate_stream(mock_pi_client: PiClient) -> None:
    subscription = mock_pi_client.subscribe_events(maxsize=300)

    mock_pi_client.prompt("Respond with the word BRIDGE.")
    _wait_for_agent_end(subscription)

    mock_pi_client.follow_up("Repeat the previous assistant response exactly.")

    _wait_for_event(subscription, "compaction_start")
    _wait_for_event(subscription, "compaction_end")
    queue_update = _wait_for_event(subscription, "queue_update")

    assert isinstance(queue_update, QueueUpdateEvent)
    assert queue_update.follow_up == ("Repeat the previous assistant response exactly.",)
    assert queue_update.steering == ()

    with pytest.raises(queue.Empty):
        subscription.get(timeout=1.0)

    state = mock_pi_client.get_state()
    assert state.is_streaming is False
    assert state.pending_message_count == 1
