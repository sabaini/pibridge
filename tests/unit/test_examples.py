from __future__ import annotations

import importlib.util
import pathlib
import sys

from pi_rpc.events import AgentEndEvent, ExtensionUiRequestEvent
from pi_rpc.protocol_types import (
    ConfirmExtensionUiRequest,
    EditorExtensionUiRequest,
    InputExtensionUiRequest,
    NotifyExtensionUiRequest,
    SelectExtensionUiRequest,
)


def _load_example_module(module_name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_examples_compile() -> None:
    for path in pathlib.Path("examples").rglob("*.py"):
        compile(path.read_text(), str(path), "exec")


def test_extension_ui_example_exits_on_agent_end() -> None:
    module = _load_example_module("examples.extension_ui", pathlib.Path("examples/extension_ui.py"))

    class FakeClient:
        def respond_extension_ui_value(self, request_id: str, value: str) -> None:
            raise AssertionError("should not respond after agent_end")

        def respond_extension_ui_confirmed(self, request_id: str, confirmed: bool = True) -> None:
            raise AssertionError("should not respond after agent_end")

        def respond_extension_ui_cancelled(self, request_id: str) -> None:
            raise AssertionError("should not respond after agent_end")

    assert module.handle_event(FakeClient(), AgentEndEvent(messages=())) is False


def test_extension_ui_example_handles_dialog_requests() -> None:
    module = _load_example_module("examples.extension_ui", pathlib.Path("examples/extension_ui.py"))

    class FakeClient:
        def __init__(self) -> None:
            self.calls: list[tuple[str, tuple[object, ...]]] = []

        def respond_extension_ui_value(self, request_id: str, value: str) -> None:
            self.calls.append(("value", (request_id, value)))

        def respond_extension_ui_confirmed(self, request_id: str, confirmed: bool = True) -> None:
            self.calls.append(("confirmed", (request_id, confirmed)))

        def respond_extension_ui_cancelled(self, request_id: str) -> None:
            self.calls.append(("cancelled", (request_id,)))

    client = FakeClient()

    assert module.handle_event(
        client,
        ExtensionUiRequestEvent(request=SelectExtensionUiRequest(id="ui-1", title="Choose", options=("Allow", "Deny"))),
    ) is True
    assert module.handle_event(
        client,
        ExtensionUiRequestEvent(request=ConfirmExtensionUiRequest(id="ui-2", title="Continue?")),
    ) is True

    assert client.calls == [
        ("value", ("ui-1", "Allow")),
        ("confirmed", ("ui-2", True)),
    ]



def test_extension_ui_example_run_until_idle_stops_after_extension_ui_inactivity() -> None:
    module = _load_example_module("examples.extension_ui", pathlib.Path("examples/extension_ui.py"))

    class FakeClient:
        def __init__(self) -> None:
            self.calls: list[tuple[str, tuple[object, ...]]] = []

        def respond_extension_ui_value(self, request_id: str, value: str) -> None:
            self.calls.append(("value", (request_id, value)))

        def respond_extension_ui_confirmed(self, request_id: str, confirmed: bool = True) -> None:
            self.calls.append(("confirmed", (request_id, confirmed)))

        def respond_extension_ui_cancelled(self, request_id: str) -> None:
            self.calls.append(("cancelled", (request_id,)))

    class FakeSubscription:
        def __init__(self) -> None:
            self.calls = 0
            self.events = [
                ExtensionUiRequestEvent(request=SelectExtensionUiRequest(id="ui-1", title="Choose", options=("Allow", "Deny"))),
                ExtensionUiRequestEvent(request=NotifyExtensionUiRequest(id="ui-2", message="select:Allow")),
            ]

        def get(self, timeout: float | None = None):
            self.calls += 1
            if self.events:
                return self.events.pop(0)
            raise module.queue.Empty

    client = FakeClient()
    subscription = FakeSubscription()

    module.run_until_idle(client, subscription, first_event_timeout=1.0, idle_timeout=0.01)

    assert client.calls == [("value", ("ui-1", "Allow"))]
    assert subscription.calls >= 3



def test_review_gate_example_chooses_configured_mode_when_available() -> None:
    module = _load_example_module("examples.review_gate_ui", pathlib.Path("examples/review_gate_ui.py"))

    request = SelectExtensionUiRequest(id="ui-1", title="Pick a review mode", options=("correctness", "security", "full"))
    answers = module.ReviewGateAnswers(review_mode="security")

    assert module.choose_review_mode(request, answers) == "security"



def test_review_gate_example_handles_dialogs_and_stops_after_idle() -> None:
    module = _load_example_module("examples.review_gate_ui", pathlib.Path("examples/review_gate_ui.py"))

    class FakeClient:
        def __init__(self) -> None:
            self.calls: list[tuple[str, tuple[object, ...]]] = []

        def respond_extension_ui_value(self, request_id: str, value: str) -> None:
            self.calls.append(("value", (request_id, value)))

        def respond_extension_ui_confirmed(self, request_id: str, confirmed: bool = True) -> None:
            self.calls.append(("confirmed", (request_id, confirmed)))

        def respond_extension_ui_cancelled(self, request_id: str) -> None:
            self.calls.append(("cancelled", (request_id,)))

    class FakeSubscription:
        def __init__(self) -> None:
            self.calls = 0
            self.events = [
                ExtensionUiRequestEvent(
                    request=SelectExtensionUiRequest(id="ui-1", title="Pick a review mode", options=("correctness", "security", "full"))
                ),
                ExtensionUiRequestEvent(request=ConfirmExtensionUiRequest(id="ui-2", title="Run the review gate?")),
                ExtensionUiRequestEvent(request=InputExtensionUiRequest(id="ui-3", title="Branch / ticket label")),
                ExtensionUiRequestEvent(request=EditorExtensionUiRequest(id="ui-4", title="Additional review instructions")),
                ExtensionUiRequestEvent(request=NotifyExtensionUiRequest(id="ui-5", message="review gate prepared a prompt", notify_type="info")),
            ]

        def get(self, timeout: float | None = None):
            self.calls += 1
            if self.events:
                return self.events.pop(0)
            raise module.queue.Empty

    client = FakeClient()
    subscription = FakeSubscription()
    answers = module.ReviewGateAnswers(
        review_mode="full",
        branch_label="feature/demo",
        additional_instructions="Focus on correctness and security.",
        confirmed=True,
    )

    module.run_until_idle(client, subscription, answers=answers, first_event_timeout=1.0, idle_timeout=0.01)

    assert client.calls == [
        ("value", ("ui-1", "full")),
        ("confirmed", ("ui-2", True)),
        ("value", ("ui-3", "feature/demo")),
        ("value", ("ui-4", "Focus on correctness and security.")),
    ]
    assert subscription.calls >= 6
