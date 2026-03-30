from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pi_rpc.client import PiClient
from pi_rpc.commands import RpcCommand
from pi_rpc.models import BashResult, LastAssistantTextResult, SessionTransitionResult
from pi_rpc.protocol_types import ImageContent, ModelInfo, UsageCost
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


def test_client_set_model_serializes_provider_and_model_id() -> None:
    client = PiClient()
    fake = FakeProcess(
        RpcResponse(
            command="set_model",
            success=True,
            data=ModelInfo(
                id="canned-responses",
                name="Canned Responses",
                api="mock-api",
                provider="pi-rpc-mock",
                base_url="mock://provider",
                reasoning=False,
                input=("text",),
                context_window=4096,
                max_tokens=1024,
                cost=UsageCost(input=0.0, output=0.0, cache_read=0.0, cache_write=0.0, total=0.0),
            ),
        )
    )
    client._process = fake  # type: ignore[assignment]

    result = client.set_model("pi-rpc-mock", "canned-responses", timeout=1.5)

    command, timeout = fake.calls[-1]
    assert isinstance(command, RpcCommand)
    assert command.type == "set_model"
    assert command.fields == {"provider": "pi-rpc-mock", "modelId": "canned-responses"}
    assert timeout == 1.5
    assert result.provider == "pi-rpc-mock"
    assert result.id == "canned-responses"


def test_client_get_last_assistant_text_returns_text() -> None:
    client = PiClient()
    fake = FakeProcess(RpcResponse(command="get_last_assistant_text", success=True, data=LastAssistantTextResult(text="hello")))
    client._process = fake  # type: ignore[assignment]

    assert client.get_last_assistant_text() == "hello"


def test_client_continue_prompt_serializes_follow_up_stream_and_optional_images() -> None:
    client = PiClient()
    fake = FakeProcess(RpcResponse(command="prompt", success=True, data=None))
    client._process = fake  # type: ignore[assignment]
    images = [ImageContent(type="image", data="base64-image", mime_type="image/png")]

    client.continue_prompt("Keep going", images=images, timeout=4.0)

    command, timeout = fake.calls[-1]
    assert isinstance(command, RpcCommand)
    assert command.type == "prompt"
    assert command.fields == {
        "message": "Keep going",
        "images": images,
        "streamingBehavior": "followUp",
    }
    assert timeout == 4.0


def test_client_context_manager_closes_process() -> None:
    client = PiClient()
    fake = FakeProcess(RpcResponse(command="get_state", success=True, data=None))
    client._process = fake  # type: ignore[assignment]
    with client:
        pass
    assert fake.closed is True
