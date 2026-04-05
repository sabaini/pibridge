from __future__ import annotations

import queue
from dataclasses import dataclass
from pathlib import Path

from pi_rpc import PiClient

try:
    from examples.runtime_config import build_example_client_options
except ImportError:  # pragma: no cover - supports `python examples/review_gate_ui.py`
    from runtime_config import build_example_client_options
from pi_rpc.events import AgentEvent, ExtensionUiRequestEvent
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


@dataclass(frozen=True)
class ReviewGateAnswers:
    review_mode: str = "full"
    branch_label: str = "feature/extension-ui-rpc-support"
    additional_instructions: str = "Focus on correctness, resilience, and concrete operator-facing impact."
    confirmed: bool = True


DEFAULT_ANSWERS = ReviewGateAnswers()


def choose_review_mode(request: SelectExtensionUiRequest, answers: ReviewGateAnswers) -> str:
    if answers.review_mode in request.options:
        return answers.review_mode
    return request.options[0]


def handle_review_gate_event(client: PiClient, event: AgentEvent, answers: ReviewGateAnswers = DEFAULT_ANSWERS) -> bool:
    if event.type == "agent_end":
        print("[agent_end]")
        return False
    if not isinstance(event, ExtensionUiRequestEvent):
        print(f"[event] {event}")
        return True

    request = event.request
    if isinstance(request, SelectExtensionUiRequest):
        choice = choose_review_mode(request, answers)
        print(f"[dialog/select] {request.title!r} -> {choice!r}")
        client.respond_extension_ui_value(request.id, choice)
    elif isinstance(request, ConfirmExtensionUiRequest):
        print(f"[dialog/confirm] {request.title!r} -> {answers.confirmed}")
        client.respond_extension_ui_confirmed(request.id, confirmed=answers.confirmed)
    elif isinstance(request, InputExtensionUiRequest):
        print(f"[dialog/input] {request.title!r} -> {answers.branch_label!r}")
        client.respond_extension_ui_value(request.id, answers.branch_label)
    elif isinstance(request, EditorExtensionUiRequest):
        print(f"[dialog/editor] {request.title!r} -> {answers.additional_instructions!r}")
        client.respond_extension_ui_value(request.id, answers.additional_instructions)
    elif isinstance(request, NotifyExtensionUiRequest):
        print(f"[notify/{request.notify_type}] {request.message}")
    elif isinstance(request, SetStatusExtensionUiRequest):
        print(f"[status] {request.status_key} = {request.status_text!r}")
    elif isinstance(request, SetWidgetExtensionUiRequest):
        print(f"[widget/{request.widget_placement}] {request.widget_key}: {request.widget_lines}")
    elif isinstance(request, SetTitleExtensionUiRequest):
        print(f"[title] {request.title}")
    elif isinstance(request, SetEditorTextExtensionUiRequest):
        print("[editor_text]")
        print(request.text)
    else:  # pragma: no cover - kept as a defensive fallback for future request types
        print(f"[extension_ui_request] {request}")
    return True


def run_until_idle(
    client: PiClient,
    subscription: EventSubscription[AgentEvent],
    *,
    answers: ReviewGateAnswers = DEFAULT_ANSWERS,
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
                print("[idle] review gate interaction finished")
                return
            raise TimeoutError("Timed out waiting for review-gate extension UI events") from None
        if not handle_review_gate_event(client, event, answers=answers):
            return
        if isinstance(event, ExtensionUiRequestEvent):
            saw_extension_ui_request = True



def main() -> None:
    extension_path = Path(__file__).with_name("extensions") / "review_gate.ts"
    options = build_example_client_options(no_session=True, extra_args=("-e", str(extension_path)))

    with PiClient(options) as client:
        commands = {command.name for command in client.get_commands()}
        if "review-gate" not in commands:
            raise RuntimeError(f"Expected /review-gate to be available from {extension_path}")

        subscription = client.subscribe_events(maxsize=200)
        client.prompt("/review-gate")
        run_until_idle(client, subscription)
        print("[done/review_gate_ui]")


if __name__ == "__main__":
    main()
