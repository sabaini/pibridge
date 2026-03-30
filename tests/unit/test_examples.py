from __future__ import annotations

import importlib.util
import pathlib

from pi_rpc.events import AgentEndEvent, ExtensionUiRequestEvent
from pi_rpc.protocol_types import ConfirmExtensionUiRequest, NotifyExtensionUiRequest, SelectExtensionUiRequest


def _load_example_module(module_name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
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
