from __future__ import annotations

import pytest

from pi_rpc.commands import RpcCommand, serialize_command
from pi_rpc.events import MessageUpdateEvent, parse_event
from pi_rpc.exceptions import PiCommandError, PiProtocolError
from pi_rpc.protocol_types import (
    AssistantMessage,
    BashExecutionMessage,
    BranchSummaryMessage,
    CompactionSummaryMessage,
    CustomMessage,
    ImageContent,
    ToolCall,
    parse_agent_message,
    serialize_agent_message,
)
from pi_rpc.responses import parse_response

MODEL = {
    "id": "claude-sonnet-4-20250514",
    "name": "Claude Sonnet 4",
    "api": "anthropic-messages",
    "provider": "anthropic",
    "baseUrl": "https://api.anthropic.com",
    "reasoning": True,
    "input": ["text", "image"],
    "contextWindow": 200000,
    "maxTokens": 16384,
    "cost": {"input": 3.0, "output": 15.0, "cacheRead": 0.3, "cacheWrite": 3.75, "total": 0.0},
}

ASSISTANT_MESSAGE = {
    "role": "assistant",
    "content": [
        {"type": "text", "text": "Hello"},
        {"type": "thinking", "thinking": "Thinking..."},
        {"type": "toolCall", "id": "call_1", "name": "bash", "arguments": {"command": "ls"}},
    ],
    "api": "anthropic-messages",
    "provider": "anthropic",
    "model": "claude-sonnet-4-20250514",
    "usage": {
        "input": 1,
        "output": 2,
        "cacheRead": 0,
        "cacheWrite": 0,
        "totalTokens": 3,
        "cost": {"input": 0.1, "output": 0.2, "cacheRead": 0.0, "cacheWrite": 0.0, "total": 0.3},
    },
    "stopReason": "stop",
    "timestamp": 123,
}


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        (RpcCommand(type="prompt", id="1", fields={"message": "hi"}), {"id": "1", "type": "prompt", "message": "hi"}),
        (
            RpcCommand(
                type="prompt",
                fields={
                    "message": "look",
                    "images": [ImageContent(type="image", data="abc", mime_type="image/png")],
                    "streamingBehavior": "steer",
                },
            ),
            {
                "type": "prompt",
                "message": "look",
                "images": [{"type": "image", "data": "abc", "mimeType": "image/png"}],
                "streamingBehavior": "steer",
            },
        ),
        (RpcCommand(type="set_model", fields={"provider": "anthropic", "modelId": "claude"}), {"type": "set_model", "provider": "anthropic", "modelId": "claude"}),
        (RpcCommand(type="set_follow_up_mode", fields={"mode": "all"}), {"type": "set_follow_up_mode", "mode": "all"}),
        (RpcCommand(type="compact", fields={"customInstructions": "focus"}), {"type": "compact", "customInstructions": "focus"}),
        (RpcCommand(type="bash", fields={"command": "ls -la"}), {"type": "bash", "command": "ls -la"}),
        (RpcCommand(type="fork", fields={"entryId": "abc"}), {"type": "fork", "entryId": "abc"}),
        (RpcCommand(type="get_commands"), {"type": "get_commands"}),
    ],
)
def test_serialize_command_covers_command_families(command: RpcCommand, expected: dict[str, object]) -> None:
    assert serialize_command(command) == expected


@pytest.mark.parametrize(
    "payload",
    [
        {"id": "1", "type": "response", "command": "prompt", "success": True},
        {"type": "response", "command": "new_session", "success": True, "data": {"cancelled": False}},
        {"type": "response", "command": "get_state", "success": True, "data": {"model": MODEL, "thinkingLevel": "medium", "isStreaming": False, "isCompacting": False, "steeringMode": "all", "followUpMode": "one-at-a-time", "sessionId": "abc", "autoCompactionEnabled": True, "messageCount": 5, "pendingMessageCount": 0}},
        {"type": "response", "command": "get_messages", "success": True, "data": {"messages": [ASSISTANT_MESSAGE]}},
        {"type": "response", "command": "set_model", "success": True, "data": MODEL},
        {"type": "response", "command": "cycle_model", "success": True, "data": {"model": MODEL, "thinkingLevel": "high", "isScoped": False}},
        {"type": "response", "command": "get_available_models", "success": True, "data": {"models": [MODEL]}},
        {"type": "response", "command": "cycle_thinking_level", "success": True, "data": {"level": "high"}},
        {"type": "response", "command": "compact", "success": True, "data": {"summary": "Summary", "firstKeptEntryId": "e1", "tokensBefore": 100, "details": {}}},
        {"type": "response", "command": "bash", "success": True, "data": {"output": "ok", "exitCode": 0, "cancelled": False, "truncated": False}},
        {
            "type": "response",
            "command": "get_session_stats",
            "success": True,
            "data": {
                "sessionFile": "session.jsonl",
                "sessionId": "abc",
                "userMessages": 1,
                "assistantMessages": 1,
                "toolCalls": 0,
                "toolResults": 0,
                "totalMessages": 2,
                "tokens": {"input": 1, "output": 2, "cacheRead": 0, "cacheWrite": 0, "total": 3},
                "cost": 0.01,
            },
        },
        {"type": "response", "command": "export_html", "success": True, "data": {"path": "/tmp/out.html"}},
        {"type": "response", "command": "fork", "success": True, "data": {"text": "original", "cancelled": False}},
        {"type": "response", "command": "get_fork_messages", "success": True, "data": {"messages": [{"entryId": "e1", "text": "hello"}]}},
        {"type": "response", "command": "get_last_assistant_text", "success": True, "data": {"text": "hello"}},
        {"type": "response", "command": "get_commands", "success": True, "data": {"commands": [{"name": "fix", "source": "prompt", "location": "project", "path": "/tmp/fix.md"}]}},
    ],
)
def test_parse_response_success_variants(payload: dict[str, object]) -> None:
    response = parse_response(payload)
    assert response.success is True


def test_parse_response_error_raises_command_error() -> None:
    response = parse_response({"type": "response", "command": "set_model", "success": False, "error": "not found"})
    with pytest.raises(PiCommandError):
        response.raise_for_error()


def test_parse_event_streaming_message_update_variant() -> None:
    event = parse_event(
        {
            "type": "message_update",
            "message": ASSISTANT_MESSAGE,
            "assistantMessageEvent": {
                "type": "text_delta",
                "contentIndex": 0,
                "delta": "Hello ",
                "partial": ASSISTANT_MESSAGE,
            },
        }
    )
    assert isinstance(event, MessageUpdateEvent)
    assert event.assistant_message_event.delta == "Hello "


@pytest.mark.parametrize(
    ("raw", "expected_type"),
    [
        ({"role": "bashExecution", "command": "ls", "output": "ok", "exitCode": 0, "cancelled": False, "truncated": False, "timestamp": 1}, BashExecutionMessage),
        ({"role": "custom", "customType": "note", "content": "hello", "display": True, "timestamp": 1}, CustomMessage),
        ({"role": "branchSummary", "summary": "sum", "fromId": "a1", "timestamp": 1}, BranchSummaryMessage),
        ({"role": "compactionSummary", "summary": "sum", "tokensBefore": 10, "timestamp": 1}, CompactionSummaryMessage),
    ],
)
def test_parse_special_agent_messages(raw: dict[str, object], expected_type: type[object]) -> None:
    parsed = parse_agent_message(raw)
    assert isinstance(parsed, expected_type)
    assert serialize_agent_message(parsed)["role"] == raw["role"]


def test_parse_assistant_message_round_trips() -> None:
    parsed = parse_agent_message(ASSISTANT_MESSAGE)
    assert isinstance(parsed, AssistantMessage)
    wire = serialize_agent_message(parsed)
    reparsed = parse_agent_message(wire)
    assert reparsed == parsed
    assert isinstance(parsed.content[2], ToolCall)


def test_parse_agent_message_rejects_unknown_role() -> None:
    with pytest.raises(PiProtocolError):
        parse_agent_message({"role": "mystery"})
