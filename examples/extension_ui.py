from __future__ import annotations

from pi_rpc import PiClient
from pi_rpc.events import AgentEvent, ExtensionUiRequestEvent
from pi_rpc.protocol_types import (
    ConfirmExtensionUiRequest,
    EditorExtensionUiRequest,
    InputExtensionUiRequest,
    SelectExtensionUiRequest,
)


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


def main() -> None:
    with PiClient() as client:
        subscription = client.subscribe_events(maxsize=200)

        # Replace this with a real prompt or extension command that triggers ctx.ui.*.
        client.prompt("/rpc-input")

        while True:
            event = subscription.get(timeout=30)
            if not handle_event(client, event):
                break


if __name__ == "__main__":
    main()
