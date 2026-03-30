from __future__ import annotations

import threading
import time
from typing import cast

import pytest

from pi_rpc import PiClient
from pi_rpc.events import AgentEvent, ExtensionUiRequestEvent
from pi_rpc.models import SessionTransitionResult
from pi_rpc.protocol_types import (
    ConfirmExtensionUiRequest,
    EditorExtensionUiRequest,
    InputExtensionUiRequest,
    NotifyExtensionUiRequest,
    SelectExtensionUiRequest,
    SetEditorTextExtensionUiRequest,
    SetStatusExtensionUiRequest,
    SetTitleExtensionUiRequest,
    SetWidgetExtensionUiRequest,
)
from pi_rpc.subscriptions import EventSubscription

pytestmark = pytest.mark.integration


def _wait_for_extension_ui_request(
    subscription: EventSubscription[AgentEvent], method: str, timeout: float = 120.0
) -> ExtensionUiRequestEvent:
    deadline = time.monotonic() + timeout
    last_event: AgentEvent | None = None
    while time.monotonic() < deadline:
        remaining = max(0.1, min(1.0, deadline - time.monotonic()))
        event = subscription.get(timeout=remaining)
        last_event = event
        if isinstance(event, ExtensionUiRequestEvent) and event.request.method == method:
            return event
    raise AssertionError(f"timed out waiting for extension_ui_request method={method!r}; last event: {last_event!r}")


def test_extension_ui_select_round_trip(mock_extension_ui_client: PiClient) -> None:
    subscription = mock_extension_ui_client.subscribe_events(maxsize=50)

    mock_extension_ui_client.prompt("/rpc-select")

    select_event = _wait_for_extension_ui_request(subscription, "select")
    request = cast(SelectExtensionUiRequest, select_event.request)
    assert request.title == "Pick a value"
    assert request.options == ("Allow", "Block")

    mock_extension_ui_client.respond_extension_ui_value(request.id, "Allow")

    notify_event = _wait_for_extension_ui_request(subscription, "notify")
    notify_request = cast(NotifyExtensionUiRequest, notify_event.request)
    assert notify_request.message == "select:Allow"
    assert notify_request.notify_type == "info"


def test_extension_ui_input_round_trip(mock_extension_ui_client: PiClient) -> None:
    subscription = mock_extension_ui_client.subscribe_events(maxsize=50)

    mock_extension_ui_client.prompt("/rpc-input")

    input_event = _wait_for_extension_ui_request(subscription, "input")
    request = cast(InputExtensionUiRequest, input_event.request)
    assert request.title == "Enter a value"
    assert request.placeholder == "type something..."

    mock_extension_ui_client.respond_extension_ui_value(request.id, "bridge")

    notify_event = _wait_for_extension_ui_request(subscription, "notify")
    notify_request = cast(NotifyExtensionUiRequest, notify_event.request)
    assert notify_request.message == "input:bridge"


def test_extension_ui_editor_round_trip(mock_extension_ui_client: PiClient) -> None:
    subscription = mock_extension_ui_client.subscribe_events(maxsize=50)

    mock_extension_ui_client.prompt("/rpc-editor")

    editor_event = _wait_for_extension_ui_request(subscription, "editor")
    request = cast(EditorExtensionUiRequest, editor_event.request)
    assert request.title == "Edit some text"
    assert request.prefill == "Line 1\nLine 2\nLine 3"

    mock_extension_ui_client.respond_extension_ui_value(request.id, "Line A\nLine B")

    notify_event = _wait_for_extension_ui_request(subscription, "notify")
    notify_request = cast(NotifyExtensionUiRequest, notify_event.request)
    assert notify_request.message == "editor:Line A|Line B"


def test_extension_ui_confirm_can_cancel_new_session(mock_extension_ui_client: PiClient) -> None:
    subscription = mock_extension_ui_client.subscribe_events(maxsize=50)
    results: list[object] = []
    errors: list[BaseException] = []

    def run_new_session() -> None:
        try:
            results.append(mock_extension_ui_client.new_session())
        except BaseException as exc:  # pragma: no cover - exercised only on failure
            errors.append(exc)

    worker = threading.Thread(target=run_new_session)
    worker.start()

    confirm_event = _wait_for_extension_ui_request(subscription, "confirm")
    request = cast(ConfirmExtensionUiRequest, confirm_event.request)
    assert request.title == "Clear session?"
    assert request.message == "All messages will be lost."

    mock_extension_ui_client.respond_extension_ui_confirmed(request.id, confirmed=False)

    worker.join(timeout=30)
    assert worker.is_alive() is False
    assert errors == []
    assert len(results) == 1
    result = cast(SessionTransitionResult, results[0])
    assert result.cancelled is True


def test_extension_ui_fire_and_forget_methods_are_published(mock_extension_ui_client: PiClient) -> None:
    subscription = mock_extension_ui_client.subscribe_events(maxsize=50)

    mock_extension_ui_client.prompt("/rpc-fire-and-forget")

    notify_event = _wait_for_extension_ui_request(subscription, "notify")
    status_event = _wait_for_extension_ui_request(subscription, "setStatus")
    widget_event = _wait_for_extension_ui_request(subscription, "setWidget")
    title_event = _wait_for_extension_ui_request(subscription, "setTitle")
    editor_text_event = _wait_for_extension_ui_request(subscription, "set_editor_text")

    notify_request = cast(NotifyExtensionUiRequest, notify_event.request)
    status_request = cast(SetStatusExtensionUiRequest, status_event.request)
    widget_request = cast(SetWidgetExtensionUiRequest, widget_event.request)
    title_request = cast(SetTitleExtensionUiRequest, title_event.request)
    editor_text_request = cast(SetEditorTextExtensionUiRequest, editor_text_event.request)

    assert notify_request.message == "fire:notify"
    assert notify_request.notify_type == "warning"
    assert status_request.status_key == "rpc-demo"
    assert status_request.status_text == "fire:status"
    assert widget_request.widget_key == "rpc-demo"
    assert widget_request.widget_lines == ("--- RPC Demo ---", "fire:widget")
    assert widget_request.widget_placement == "belowEditor"
    assert title_request.title == "pi RPC Demo"
    assert editor_text_request.text == "prefilled text for the user"
