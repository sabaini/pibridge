from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pi_rpc.client import PiClient
from pi_rpc.commands import RpcCommand
from pi_rpc.models import BashResult, LastAssistantTextResult, SessionTransitionResult
from pi_rpc.responses import RpcResponse


@dataclass
class FakeProcess:
    response: RpcResponse[Any]

    def __post_init__(self) -> None:
        self.calls: list[tuple[RpcCommand | str, float | None]] = []
        self.closed = False

    def send_command(self, command: RpcCommand | str, timeout: float | None = None) -> RpcResponse[Any]:
        self.calls.append((command, timeout))
        return self.response

    def subscribe_events(self, maxsize: int = 1000) -> object:
        return {"maxsize": maxsize}

    def close(self) -> None:
        self.closed = True


def test_client_methods_emit_expected_payloads() -> None:
    client = PiClient()
    fake = FakeProcess(RpcResponse(command="bash", success=True, data=BashResult(output="ok", exit_code=0, cancelled=False, truncated=False)))
    client._process = fake  # type: ignore[assignment]

    result = client.bash("ls -la", timeout=2.5)

    command, timeout = fake.calls[-1]
    assert isinstance(command, RpcCommand)
    assert command.type == "bash"
    assert command.fields == {"command": "ls -la"}
    assert timeout == 2.5
    assert result.output == "ok"


def test_client_unwraps_cancelled_session_result() -> None:
    client = PiClient()
    fake = FakeProcess(RpcResponse(command="new_session", success=True, data=SessionTransitionResult(cancelled=True)))
    client._process = fake  # type: ignore[assignment]

    result = client.new_session(parent_session="/tmp/parent.jsonl")

    command, _ = fake.calls[-1]
    assert isinstance(command, RpcCommand)
    assert command.type == "new_session"
    assert command.fields == {"parentSession": "/tmp/parent.jsonl"}
    assert result.cancelled is True


def test_client_get_last_assistant_text_returns_text() -> None:
    client = PiClient()
    fake = FakeProcess(RpcResponse(command="get_last_assistant_text", success=True, data=LastAssistantTextResult(text="hello")))
    client._process = fake  # type: ignore[assignment]

    assert client.get_last_assistant_text() == "hello"


def test_client_context_manager_closes_process() -> None:
    client = PiClient()
    fake = FakeProcess(RpcResponse(command="get_state", success=True, data=None))
    client._process = fake  # type: ignore[assignment]
    with client:
        pass
    assert fake.closed is True
