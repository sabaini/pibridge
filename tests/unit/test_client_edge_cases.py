from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from picable.client import PiClient
from picable.commands import RpcCommand
from picable.exceptions import PiTimeoutError
from picable.models import LastAssistantTextResult
from picable.protocol_types import (
    AssistantMessage,
    ModelInfo,
    RpcSessionState,
    TextContent,
    Usage,
    UsageCost,
)
from picable.responses import RpcResponse


def _model() -> ModelInfo:
    zero = UsageCost(input=0.0, output=0.0, cache_read=0.0, cache_write=0.0, total=0.0)
    return ModelInfo(
        id="m",
        name="m",
        api="mock",
        provider="mock",
        base_url="mock://",
        reasoning=False,
        input=("text",),
        context_window=1000,
        max_tokens=100,
        cost=zero,
    )


def _usage() -> Usage:
    zero = UsageCost(input=0.0, output=0.0, cache_read=0.0, cache_write=0.0, total=0.0)
    return Usage(input=0, output=0, cache_read=0, cache_write=0, total_tokens=0, cost=zero)


def _state(*, streaming: bool, pending: int = 0) -> RpcSessionState:
    return RpcSessionState(
        model=_model(),
        thinking_level="medium",
        is_streaming=streaming,
        is_compacting=False,
        steering_mode="all",
        follow_up_mode="all",
        session_id="s",
        auto_compaction_enabled=True,
        message_count=1,
        pending_message_count=pending,
        session_file=None,
        session_name=None,
    )


@dataclass
class SequenceProcess:
    responses: list[RpcResponse[Any]]

    def __post_init__(self) -> None:
        self.calls: list[tuple[RpcCommand | str, float | None]] = []
        self.closed = False

    def send_command(self, command: RpcCommand | str, timeout: float | None = None) -> RpcResponse[Any]:
        self.calls.append((command, timeout))
        assert self.responses, f"unexpected command {command}"
        return self.responses.pop(0)

    def subscribe_events(self, maxsize: int = 1000) -> object:
        return {"maxsize": maxsize}

    def close(self) -> None:
        self.closed = True


def test_prompt_and_wait_waits_for_pi_idle_after_prompt_submission() -> None:
    client = PiClient()
    process = SequenceProcess(
        [
            RpcResponse(command="prompt", success=True, data=None),
            RpcResponse(command="get_state", success=True, data=_state(streaming=True)),
            RpcResponse(command="get_state", success=True, data=_state(streaming=False)),
        ]
    )
    client._process = process  # type: ignore[assignment]

    client.prompt_and_wait("hello", submit_timeout=1.0, wait_timeout=5.0, poll_interval=0)

    assert [c.type for c, _ in process.calls if isinstance(c, RpcCommand)] == ["prompt", "get_state", "get_state"]


def test_wait_until_idle_times_out_if_pi_never_becomes_idle() -> None:
    client = PiClient()
    process = SequenceProcess(
        [
            RpcResponse(command="get_state", success=True, data=_state(streaming=True)),
            RpcResponse(command="get_state", success=True, data=_state(streaming=True)),
        ]
    )
    client._process = process  # type: ignore[assignment]

    with pytest.raises(PiTimeoutError):
        client.wait_until_idle(timeout=0, poll_interval=0)


def test_get_last_assistant_text_falls_back_to_messages_when_rpc_result_is_empty() -> None:
    client = PiClient()
    assistant = AssistantMessage(
        role="assistant",
        content=(TextContent(type="text", text="structured: yaml"),),
        api="mock",
        provider="mock",
        model="m",
        usage=_usage(),
        stop_reason="stop",
        timestamp=1,
    )
    process = SequenceProcess(
        [
            RpcResponse(command="get_last_assistant_text", success=True, data=LastAssistantTextResult(text="")),
            RpcResponse(command="get_messages", success=True, data=[assistant]),
        ]
    )
    client._process = process  # type: ignore[assignment]

    assert client.get_last_assistant_text() == "structured: yaml"
