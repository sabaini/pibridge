from __future__ import annotations

import threading
import time

import pytest

from pi_rpc import PiClient
from pi_rpc.exceptions import PiProcessExitedError, PiProtocolError, PiSubscriptionOverflowError
from tests.integration.conftest import _collect_events_until_agent_end

pytestmark = pytest.mark.integration


@pytest.fixture
def mock_prompt_map() -> dict[str, object]:
    return {
        "Fan out a short stream": {"chunks": ["fan", "-", "out"], "delayMs": 50},
        "Overflow a slow subscriber": {"chunks": ["one", "two", "three", "four"], "delayMs": 25},
    }


def _event_signature(event: object) -> tuple[str, str | None]:
    event_type = getattr(event, "type", None)
    if event_type != "message_update":
        return (str(event_type), None)
    assistant_event = getattr(event, "assistant_message_event", None)
    return ("message_update", getattr(assistant_event, "delta", None))



def test_multiple_subscribers_receive_the_same_event_order(mock_pi_client: PiClient) -> None:
    first = mock_pi_client.subscribe_events(maxsize=200)
    second = mock_pi_client.subscribe_events(maxsize=200)

    mock_pi_client.prompt("Fan out a short stream")

    first_events = _collect_events_until_agent_end(first)
    second_events = _collect_events_until_agent_end(second)

    assert [_event_signature(event) for event in first_events] == [_event_signature(event) for event in second_events]



def test_slow_subscriber_overflow_does_not_break_fast_subscriber(mock_pi_client: PiClient) -> None:
    slow = mock_pi_client.subscribe_events(maxsize=1)
    fast = mock_pi_client.subscribe_events(maxsize=200)

    mock_pi_client.prompt("Overflow a slow subscriber")

    fast_events = _collect_events_until_agent_end(fast)

    assert fast_events[-1].type == "agent_end"
    assert mock_pi_client.get_last_assistant_text() == "onetwothreefour"
    assert slow.get(timeout=1.0).type == "agent_start"
    with pytest.raises(PiSubscriptionOverflowError):
        slow.get(timeout=1.0)



def test_client_close_wakes_blocked_subscriptions_and_future_commands_fail(mock_pi_client: PiClient) -> None:
    subscription = mock_pi_client.subscribe_events(maxsize=10)
    assert subscription.drain() == []
    result: dict[str, BaseException] = {}
    started = threading.Event()

    def wait_for_event() -> None:
        started.set()
        while True:
            try:
                subscription.get(timeout=1.0)
            except BaseException as exc:  # pragma: no branch - thread handoff only
                result["error"] = exc
                return

    worker = threading.Thread(target=wait_for_event, daemon=True)
    worker.start()
    assert started.wait(timeout=1)
    time.sleep(0.1)

    mock_pi_client.close()
    worker.join(timeout=5)

    assert worker.is_alive() is False
    assert isinstance(result.get("error"), PiProtocolError)
    with pytest.raises(PiProcessExitedError):
        mock_pi_client.get_state()
