from __future__ import annotations

import pytest

from pi_rpc.commands import RpcCommand, serialize_command
from pi_rpc.events import AutoCompactionEndEvent, AutoCompactionStartEvent, ExtensionUiRequestEvent, MessageUpdateEvent, QueueUpdateEvent, parse_event
from pi_rpc.exceptions import PiCommandError, PiProtocolError
from pi_rpc.protocol_types import (
    AssistantMessage,
    BashExecutionMessage,
    BranchSummaryMessage,
    CompactionSummaryMessage,
    ConfirmExtensionUiRequest,
    CustomMessage,
    EditorExtensionUiRequest,
    ImageContent,
    InputExtensionUiRequest,
    NotifyExtensionUiRequest,
    SelectExtensionUiRequest,
    SetEditorTextExtensionUiRequest,
    SetStatusExtensionUiRequest,
    SetTitleExtensionUiRequest,
    SetWidgetExtensionUiRequest,
    ToolCall,
    parse_agent_message,
    parse_assistant_message_event,
    parse_extension_ui_request,
    parse_rpc_slash_command,
    parse_session_state,
    serialize_agent_message,
    serialize_extension_ui_response,
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


@pytest.mark.parametrize(
    ("payload", "expected_type"),
    [
        ({"type": "auto_compaction_start", "reason": "threshold"}, "auto_compaction_start"),
        ({"type": "compaction_start", "reason": "threshold"}, "compaction_start"),
    ],
)
def test_parse_event_accepts_compaction_start_aliases(payload: dict[str, object], expected_type: str) -> None:
    event = parse_event(payload)
    assert isinstance(event, AutoCompactionStartEvent)
    assert event.reason == "threshold"
    assert event.type == expected_type


@pytest.mark.parametrize(
    ("payload", "expected_type"),
    [
        (
            {
                "type": "auto_compaction_end",
                "reason": "threshold",
                "result": {"summary": "Summary", "firstKeptEntryId": "e1", "tokensBefore": 42, "details": {}},
                "aborted": False,
                "willRetry": False,
            },
            "auto_compaction_end",
        ),
        (
            {
                "type": "compaction_end",
                "reason": "threshold",
                "result": {"summary": "Summary", "firstKeptEntryId": "e1", "tokensBefore": 42, "details": {}},
                "aborted": False,
                "willRetry": False,
            },
            "compaction_end",
        ),
    ],
)
def test_parse_event_accepts_compaction_end_aliases(payload: dict[str, object], expected_type: str) -> None:
    event = parse_event(payload)
    assert isinstance(event, AutoCompactionEndEvent)
    assert event.result is not None
    assert event.result.summary == "Summary"
    assert event.type == expected_type


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


@pytest.mark.parametrize(
    ("payload", "match"),
    [
        ({**ASSISTANT_MESSAGE, "stopReason": "mystery"}, "stopReason"),
        ({"type": "mystery", "partial": ASSISTANT_MESSAGE}, "assistantMessageEvent.type"),
        ({"type": "done", "reason": "mystery", "message": ASSISTANT_MESSAGE}, "assistantMessageEvent.reason"),
        ({"name": "fix", "source": "unknown"}, "source"),
        ({"name": "fix", "source": "prompt", "location": "team"}, "location"),
        ({"model": MODEL, "thinkingLevel": "turbo", "isStreaming": False, "isCompacting": False, "steeringMode": "all", "followUpMode": "one-at-a-time", "sessionId": "abc", "autoCompactionEnabled": True, "messageCount": 1, "pendingMessageCount": 0}, "thinkingLevel"),
        ({"model": MODEL, "thinkingLevel": "medium", "isStreaming": False, "isCompacting": False, "steeringMode": "many", "followUpMode": "one-at-a-time", "sessionId": "abc", "autoCompactionEnabled": True, "messageCount": 1, "pendingMessageCount": 0}, "steeringMode"),
        ({"type": "response", "command": "cycle_model", "success": True, "data": {"model": MODEL, "thinkingLevel": "turbo", "isScoped": False}}, "cycle_model.data.thinkingLevel"),
        ({"type": "response", "command": "cycle_thinking_level", "success": True, "data": {"level": "turbo"}}, "cycle_thinking_level.data.level"),
    ],
)
def test_protocol_parsers_reject_unknown_enum_values(payload: dict[str, object], match: str) -> None:
    with pytest.raises(PiProtocolError, match=match):
        if payload.get("type") == "response":
            parse_response(payload)
        elif payload.get("type") == "done" or payload.get("type") == "mystery":
            parse_assistant_message_event(payload)
        elif payload.get("source") is not None:
            parse_rpc_slash_command(payload)
        elif payload.get("sessionId") is not None:
            parse_session_state(payload)
        else:
            parse_agent_message(payload)


@pytest.mark.parametrize(
    ("payload", "expected_type", "expected_fields"),
    [
        (
            {"type": "extension_ui_request", "id": "req-select", "method": "select", "title": "Choose", "options": ["Allow", "Block"], "timeout": 1000},
            SelectExtensionUiRequest,
            {"id": "req-select", "title": "Choose", "options": ("Allow", "Block"), "timeout": 1000},
        ),
        (
            {"type": "extension_ui_request", "id": "req-confirm", "method": "confirm", "title": "Clear session?", "message": "All messages will be lost.", "timeout": 5000},
            ConfirmExtensionUiRequest,
            {"id": "req-confirm", "title": "Clear session?", "message": "All messages will be lost.", "timeout": 5000},
        ),
        (
            {"type": "extension_ui_request", "id": "req-input", "method": "input", "title": "Enter", "placeholder": "type..."},
            InputExtensionUiRequest,
            {"id": "req-input", "title": "Enter", "placeholder": "type...", "timeout": None},
        ),
        (
            {"type": "extension_ui_request", "id": "req-editor", "method": "editor", "title": "Edit", "prefill": "Line 1"},
            EditorExtensionUiRequest,
            {"id": "req-editor", "title": "Edit", "prefill": "Line 1", "timeout": None},
        ),
        (
            {"type": "extension_ui_request", "id": "req-notify", "method": "notify", "message": "Heads up"},
            NotifyExtensionUiRequest,
            {"id": "req-notify", "message": "Heads up", "notify_type": "info"},
        ),
        (
            {"type": "extension_ui_request", "id": "req-status", "method": "setStatus", "statusKey": "demo", "statusText": "running"},
            SetStatusExtensionUiRequest,
            {"id": "req-status", "status_key": "demo", "status_text": "running"},
        ),
        (
            {"type": "extension_ui_request", "id": "req-widget", "method": "setWidget", "widgetKey": "demo", "widgetLines": ["one", "two"]},
            SetWidgetExtensionUiRequest,
            {"id": "req-widget", "widget_key": "demo", "widget_lines": ("one", "two"), "widget_placement": "aboveEditor"},
        ),
        (
            {"type": "extension_ui_request", "id": "req-title", "method": "setTitle", "title": "pi demo"},
            SetTitleExtensionUiRequest,
            {"id": "req-title", "title": "pi demo"},
        ),
        (
            {"type": "extension_ui_request", "id": "req-editor-text", "method": "set_editor_text", "text": "prefilled text"},
            SetEditorTextExtensionUiRequest,
            {"id": "req-editor-text", "text": "prefilled text"},
        ),
    ],
)
def test_parse_extension_ui_request_variants(payload: dict[str, object], expected_type: type[object], expected_fields: dict[str, object]) -> None:
    parsed = parse_extension_ui_request(payload)
    assert isinstance(parsed, expected_type)
    for key, value in expected_fields.items():
        assert getattr(parsed, key) == value


def test_parse_event_supports_extension_ui_requests() -> None:
    event = parse_event({"type": "extension_ui_request", "id": "req-1", "method": "confirm", "title": "Clear session?"})
    assert isinstance(event, ExtensionUiRequestEvent)
    assert event.request.id == "req-1"
    assert event.request.method == "confirm"


def test_parse_event_supports_queue_updates() -> None:
    event = parse_event({"type": "queue_update", "steering": ["Prefer concise wording."], "followUp": ["Repeat it."]})
    assert isinstance(event, QueueUpdateEvent)
    assert event.steering == ("Prefer concise wording.",)
    assert event.follow_up == ("Repeat it.",)


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        (
            {"request_id": "req-1", "value": "Allow"},
            {"type": "extension_ui_response", "id": "req-1", "value": "Allow"},
        ),
        (
            {"request_id": "req-2", "confirmed": True},
            {"type": "extension_ui_response", "id": "req-2", "confirmed": True},
        ),
        (
            {"request_id": "req-3", "cancelled": True},
            {"type": "extension_ui_response", "id": "req-3", "cancelled": True},
        ),
    ],
)
def test_serialize_extension_ui_response_variants(kwargs: dict[str, object], expected: dict[str, object]) -> None:
    assert serialize_extension_ui_response(**kwargs) == expected


@pytest.mark.parametrize(
    ("call", "match"),
    [
        (lambda: parse_extension_ui_request({"type": "extension_ui_request", "id": "req-1", "method": "select", "title": "Choose", "options": ["Allow", 1]}), "options"),
        (lambda: parse_extension_ui_request({"type": "extension_ui_request", "id": "req-2", "method": "confirm", "title": "Clear", "timeout": True}), "timeout"),
        (lambda: parse_extension_ui_request({"type": "extension_ui_request", "id": "req-3", "method": "notify", "message": "Heads up", "notifyType": "loud"}), "notifyType"),
        (lambda: parse_extension_ui_request({"type": "extension_ui_request", "id": "req-4", "method": "setWidget", "widgetKey": "demo", "widgetPlacement": "sidebar"}), "widgetPlacement"),
        (lambda: parse_extension_ui_request({"type": "extension_ui_request", "id": "req-5", "method": "mystery"}), "method"),
        (lambda: parse_extension_ui_request({"type": "extension_ui_request", "id": "", "method": "confirm", "title": "Clear"}), "non-empty"),
        (lambda: serialize_extension_ui_response(request_id="req-6"), "exactly one"),
        (lambda: serialize_extension_ui_response(request_id="req-7", value="Allow", confirmed=True), "exactly one"),
        (lambda: serialize_extension_ui_response(request_id="req-8", cancelled=False), "cancelled"),
        (lambda: serialize_extension_ui_response(request_id="", value="Allow"), "non-empty"),
    ],
)
def test_extension_ui_protocol_helpers_reject_malformed_payloads(call: object, match: str) -> None:
    with pytest.raises(PiProtocolError, match=match):
        assert callable(call)
        call()
