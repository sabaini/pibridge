from __future__ import annotations

import queue

from pi_rpc import PiClient
from pi_rpc.events import AgentEvent, ExtensionUiRequestEvent
from pi_rpc.protocol_types import (
    ConfirmExtensionUiRequest,
    EditorExtensionUiRequest,
    InputExtensionUiRequest,
    SelectExtensionUiRequest,
)
from pi_rpc.subscriptions import EventSubscription


def handle_event(client: PiClient, event: AgentEvent) -> bool:
    if event.type == "agent_end":
        return False
    if not isinstance(event, ExtensionUiRequestEvent):
        return True

    request = event.request
    if isinstance(request, SelectExtensionUiRequest):
        client.respond_extension_ui_value(request.id, request.options[0])
    elif isinstance(request, ConfirmExtensionUiRequest):
        client.respond_extension_ui_confirmed(request.id, confirmed=True)
    elif isinstance(request, (InputExtensionUiRequest, EditorExtensionUiRequest)):
        client.respond_extension_ui_value(request.id, "example response")
    else:
        print(f"Fire-and-forget UI request: {request}")
    return True


def run_until_idle(
    client: PiClient,
    subscription: EventSubscription[AgentEvent],
    *,
    first_event_timeout: float = 30.0,
    idle_timeout: float = 1.0,
) -> None:
    saw_extension_ui_request = False
    while True:
        timeout = idle_timeout if saw_extension_ui_request else first_event_timeout
        try:
            event = subscription.get(timeout=timeout)
        except queue.Empty:
            if saw_extension_ui_request:
                return
            raise TimeoutError("Timed out waiting for extension UI events") from None
        if not handle_event(client, event):
            return
        if isinstance(event, ExtensionUiRequestEvent):
            saw_extension_ui_request = True



def main() -> None:
    with PiClient() as client:
        subscription = client.subscribe_events(maxsize=200)

        # Replace this with a real prompt or extension command that triggers ctx.ui.*.
        # Extension commands may emit only extension_ui_request events and no agent_end,
        # so this example exits after the stream goes idle.
        client.prompt("/rpc-input")
        run_until_idle(client, subscription)


if __name__ == "__main__":
    main()
