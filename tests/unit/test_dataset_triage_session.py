from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from pi_rpc import PiCommandError, PiProcessExitedError, PiTimeoutError
from pi_rpc.events import AgentEndEvent, MessageUpdateEvent, ToolExecutionStartEvent
from pi_rpc.protocol_types import AssistantMessage, AssistantMessageEvent, TextContent, Usage, UsageCost
from tests.example_support import load_dataset_triage_module

session_module = load_dataset_triage_module("pi_session")


@dataclass
class FakeSubscription:
    events: list[object]

    def __post_init__(self) -> None:
        self._index = 0

    def get(self, timeout: float | None = None) -> object:
        if self._index >= len(self.events):
            raise AssertionError("subscription exhausted before agent_end")
        event = self.events[self._index]
        self._index += 1
        if isinstance(event, BaseException):
            raise event
        return event


@dataclass
class FakeClient:
    subscription: FakeSubscription
    last_text: str | None = None
    session_names: list[str] = field(default_factory=list)
    prompted: list[str] = field(default_factory=list)
    follow_ups: list[str] = field(default_factory=list)
    new_session_calls: int = 0
    closed: bool = False
    prompt_error: BaseException | None = None
    follow_up_error: BaseException | None = None

    def subscribe_events(self, maxsize: int = 1000) -> FakeSubscription:
        return self.subscription

    def new_session(self) -> None:
        self.new_session_calls += 1

    def set_session_name(self, name: str) -> None:
        self.session_names.append(name)

    def prompt(self, message: str, *, streaming_behavior: str | None = None) -> None:
        if self.prompt_error is not None:
            raise self.prompt_error
        suffix = f"|{streaming_behavior}" if streaming_behavior is not None else ""
        self.prompted.append(f"{message}{suffix}")

    def follow_up(self, message: str) -> None:
        if self.follow_up_error is not None:
            raise self.follow_up_error
        self.follow_ups.append(message)

    def get_last_assistant_text(self) -> str | None:
        return self.last_text

    def close(self) -> None:
        self.closed = True


def make_assistant_message(text: str) -> AssistantMessage:
    usage = Usage(input=1, output=1, cache_read=0, cache_write=0, total_tokens=2, cost=UsageCost(input=0.0, output=0.0, cache_read=0.0, cache_write=0.0, total=0.0))
    return AssistantMessage(role="assistant", content=(TextContent(type="text", text=text),), api="mock", provider="mock", model="mock", usage=usage, stop_reason="stop", timestamp=0)


def make_text_delta(delta: str) -> MessageUpdateEvent:
    message = make_assistant_message(delta)
    return MessageUpdateEvent(message=message, assistant_message_event=AssistantMessageEvent(type="text_delta", delta=delta), type="message_update")


def make_agent_end(text: str = "") -> AgentEndEvent:
    return AgentEndEvent(messages=(make_assistant_message(text),), type="agent_end")


def build_session(client: FakeClient) -> object:
    return session_module.DatasetTriageSession(client_factory=lambda _options: client)


def test_analyze_profile_accumulates_text_deltas_and_ignores_non_text_events() -> None:
    subscription = FakeSubscription(
        [
            ToolExecutionStartEvent(tool_call_id="1", tool_name="tool", args={}, type="tool_execution_start"),
            make_text_delta("Hello"),
            make_text_delta(" world"),
            make_agent_end("Hello world!"),
        ]
    )
    client = FakeClient(subscription=subscription, last_text="Hello world!")
    session = build_session(client)
    updates: list[str] = []

    final_text = session.analyze_profile("Summarize this dataset", on_update=updates.append)

    assert client.prompted == ["Summarize this dataset"]
    assert updates == ["Hello", "Hello world", "Hello world!"]
    assert final_text == "Hello world!"


def test_ask_follow_up_reuses_existing_client_subscription() -> None:
    subscription = FakeSubscription([make_text_delta("Follow-up"), make_agent_end("Follow-up")])
    client = FakeClient(subscription=subscription, last_text="Follow-up")
    session = build_session(client)

    final_text = session.ask_follow_up("Which column should I clean first?")

    assert client.prompted == ["Which column should I clean first?|followUp"]
    assert final_text == "Follow-up"


def test_reset_for_dataset_starts_new_named_session() -> None:
    client = FakeClient(subscription=FakeSubscription([make_agent_end("ignored")]))
    session = build_session(client)

    session.reset_for_dataset("customers.csv")

    assert client.new_session_calls == 1
    assert client.session_names == ["dataset-triage:customers.csv"]


@pytest.mark.parametrize(
    "error",
    [
        PiTimeoutError(command="prompt", timeout=1.0),
        PiProcessExitedError(message="pi exited unexpectedly", returncode=1),
        PiCommandError(command="follow_up", message="rejected"),
    ],
)
def test_session_wraps_pi_errors_as_ui_safe_failures(error: BaseException) -> None:
    client = FakeClient(subscription=FakeSubscription([]), prompt_error=error, follow_up_error=error)
    session = build_session(client)

    with pytest.raises(session_module.DatasetTriageSessionError, match="Pi request failed"):
        session.analyze_profile("profile")
