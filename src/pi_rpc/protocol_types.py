from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, cast

from .exceptions import PiProtocolError

ThinkingLevel = Literal["off", "minimal", "low", "medium", "high", "xhigh"]
QueueMode = Literal["all", "one-at-a-time"]
StreamingBehavior = Literal["steer", "followUp"]
NotifyType = Literal["info", "warning", "error"]
WidgetPlacement = Literal["aboveEditor", "belowEditor"]
AssistantStopReason = Literal["stop", "length", "toolUse", "error", "aborted"]
AssistantEventType = Literal[
    "start",
    "text_start",
    "text_delta",
    "text_end",
    "thinking_start",
    "thinking_delta",
    "thinking_end",
    "toolcall_start",
    "toolcall_delta",
    "toolcall_end",
    "done",
    "error",
]


@dataclass(frozen=True)
class TextContent:
    type: Literal["text"]
    text: str
    text_signature: str | None = None


@dataclass(frozen=True)
class ThinkingContent:
    type: Literal["thinking"]
    thinking: str
    thinking_signature: str | None = None
    redacted: bool = False


@dataclass(frozen=True)
class ImageContent:
    type: Literal["image"]
    data: str
    mime_type: str


@dataclass(frozen=True)
class ToolCall:
    type: Literal["toolCall"]
    id: str
    name: str
    arguments: dict[str, Any]
    thought_signature: str | None = None


ContentBlock = TextContent | ThinkingContent | ImageContent | ToolCall


@dataclass(frozen=True)
class UsageCost:
    input: float
    output: float
    cache_read: float
    cache_write: float
    total: float


@dataclass(frozen=True)
class Usage:
    input: int
    output: int
    cache_read: int
    cache_write: int
    total_tokens: int
    cost: UsageCost


@dataclass(frozen=True)
class ModelInfo:
    id: str
    name: str
    api: str
    provider: str
    base_url: str
    reasoning: bool
    input: tuple[str, ...]
    context_window: int
    max_tokens: int
    cost: UsageCost
    headers: dict[str, str] | None = None
    compat: dict[str, Any] | None = None


@dataclass(frozen=True)
class UserMessage:
    role: Literal["user"]
    content: str | tuple[TextContent | ImageContent, ...]
    timestamp: int


@dataclass(frozen=True)
class AssistantMessage:
    role: Literal["assistant"]
    content: tuple[TextContent | ThinkingContent | ToolCall, ...]
    api: str
    provider: str
    model: str
    usage: Usage
    stop_reason: AssistantStopReason
    timestamp: int
    response_id: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class ToolResultMessage:
    role: Literal["toolResult"]
    tool_call_id: str
    tool_name: str
    content: tuple[TextContent | ImageContent, ...]
    is_error: bool
    timestamp: int
    details: Any | None = None


@dataclass(frozen=True)
class BashExecutionMessage:
    role: Literal["bashExecution"]
    command: str
    output: str
    exit_code: int | None
    cancelled: bool
    truncated: bool
    timestamp: int
    full_output_path: str | None = None
    exclude_from_context: bool = False


@dataclass(frozen=True)
class CustomMessage:
    role: Literal["custom"]
    custom_type: str
    content: str | tuple[TextContent | ImageContent, ...]
    display: bool
    timestamp: int
    details: Any | None = None


@dataclass(frozen=True)
class BranchSummaryMessage:
    role: Literal["branchSummary"]
    summary: str
    from_id: str
    timestamp: int


@dataclass(frozen=True)
class CompactionSummaryMessage:
    role: Literal["compactionSummary"]
    summary: str
    tokens_before: int
    timestamp: int


AgentMessage = UserMessage | AssistantMessage | ToolResultMessage | BashExecutionMessage | CustomMessage | BranchSummaryMessage | CompactionSummaryMessage


@dataclass(frozen=True)
class RpcSlashCommand:
    name: str
    source: Literal["extension", "prompt", "skill"]
    description: str | None = None
    location: Literal["user", "project", "path"] | None = None
    path: str | None = None


@dataclass(frozen=True)
class RpcSessionState:
    model: ModelInfo | None
    thinking_level: ThinkingLevel
    is_streaming: bool
    is_compacting: bool
    steering_mode: QueueMode
    follow_up_mode: QueueMode
    session_id: str
    auto_compaction_enabled: bool
    message_count: int
    pending_message_count: int
    session_file: str | None = None
    session_name: str | None = None


@dataclass(frozen=True)
class AssistantMessageEvent:
    type: AssistantEventType
    partial: AssistantMessage | None = None
    content_index: int | None = None
    delta: str | None = None
    content: str | None = None
    tool_call: ToolCall | None = None
    reason: str | None = None
    message: AssistantMessage | None = None
    error: AssistantMessage | None = None


@dataclass(frozen=True)
class ToolExecutionResult:
    content: tuple[TextContent | ImageContent, ...]
    details: Any | None = None


@dataclass(frozen=True)
class ExtensionUiRequest:
    id: str
    method: str
    payload: dict[str, Any] = field(default_factory=dict)


def _expect_type(value: Any, expected: type, field_name: str) -> Any:
    if not isinstance(value, expected):
        raise PiProtocolError(f"Expected {field_name} to be {expected.__name__}, got {type(value).__name__}")
    return value


def _require_mapping(payload: Any, label: str = "payload") -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise PiProtocolError(f"Expected {label} to be an object, got {type(payload).__name__}")
    return payload


def _require_str(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise PiProtocolError(f"Expected '{key}' to be a string")
    return value


def _optional_str(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise PiProtocolError(f"Expected '{key}' to be a string when present")
    return value


def _require_bool(payload: dict[str, Any], key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise PiProtocolError(f"Expected '{key}' to be a boolean")
    return value


def _require_int(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise PiProtocolError(f"Expected '{key}' to be an integer")
    return value


def _optional_int(payload: dict[str, Any], key: str) -> int | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise PiProtocolError(f"Expected '{key}' to be an integer when present")
    return value


def _require_list(payload: dict[str, Any], key: str) -> list[Any]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise PiProtocolError(f"Expected '{key}' to be a list")
    return value


def parse_usage_cost(payload: Any) -> UsageCost:
    payload = _require_mapping(payload, "cost")
    return UsageCost(
        input=float(payload.get("input", 0.0)),
        output=float(payload.get("output", 0.0)),
        cache_read=float(payload.get("cacheRead", 0.0)),
        cache_write=float(payload.get("cacheWrite", 0.0)),
        total=float(payload.get("total", 0.0)),
    )


def serialize_usage_cost(cost: UsageCost) -> dict[str, Any]:
    return {
        "input": cost.input,
        "output": cost.output,
        "cacheRead": cost.cache_read,
        "cacheWrite": cost.cache_write,
        "total": cost.total,
    }


def parse_usage(payload: Any) -> Usage:
    payload = _require_mapping(payload, "usage")
    return Usage(
        input=_require_int(payload, "input"),
        output=_require_int(payload, "output"),
        cache_read=_require_int(payload, "cacheRead"),
        cache_write=_require_int(payload, "cacheWrite"),
        total_tokens=_require_int(payload, "totalTokens"),
        cost=parse_usage_cost(payload.get("cost", {})),
    )


def serialize_usage(usage: Usage) -> dict[str, Any]:
    return {
        "input": usage.input,
        "output": usage.output,
        "cacheRead": usage.cache_read,
        "cacheWrite": usage.cache_write,
        "totalTokens": usage.total_tokens,
        "cost": serialize_usage_cost(usage.cost),
    }


def parse_model(payload: Any) -> ModelInfo:
    payload = _require_mapping(payload, "model")
    inputs = payload.get("input")
    if not isinstance(inputs, list) or not all(isinstance(item, str) for item in inputs):
        raise PiProtocolError("Expected 'input' to be a list of strings")
    headers = payload.get("headers")
    if headers is not None:
        headers = _require_mapping(headers, "headers")
        for key, value in headers.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise PiProtocolError("Expected 'headers' to contain string keys and values")
    compat = payload.get("compat")
    if compat is not None and not isinstance(compat, dict):
        raise PiProtocolError("Expected 'compat' to be an object when present")
    return ModelInfo(
        id=_require_str(payload, "id"),
        name=_require_str(payload, "name"),
        api=_require_str(payload, "api"),
        provider=_require_str(payload, "provider"),
        base_url=_require_str(payload, "baseUrl"),
        reasoning=_require_bool(payload, "reasoning"),
        input=tuple(inputs),
        context_window=_require_int(payload, "contextWindow"),
        max_tokens=_require_int(payload, "maxTokens"),
        cost=parse_usage_cost(payload.get("cost", {})),
        headers=dict(headers) if headers else None,
        compat=dict(compat) if compat else None,
    )


def serialize_model(model: ModelInfo) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": model.id,
        "name": model.name,
        "api": model.api,
        "provider": model.provider,
        "baseUrl": model.base_url,
        "reasoning": model.reasoning,
        "input": list(model.input),
        "contextWindow": model.context_window,
        "maxTokens": model.max_tokens,
        "cost": serialize_usage_cost(model.cost),
    }
    if model.headers is not None:
        payload["headers"] = dict(model.headers)
    if model.compat is not None:
        payload["compat"] = dict(model.compat)
    return payload


def parse_text_content(payload: Any) -> TextContent:
    payload = _require_mapping(payload, "text content")
    if payload.get("type") != "text":
        raise PiProtocolError("Expected content block type 'text'")
    return TextContent(type="text", text=_require_str(payload, "text"), text_signature=_optional_str(payload, "textSignature"))


def parse_thinking_content(payload: Any) -> ThinkingContent:
    payload = _require_mapping(payload, "thinking content")
    if payload.get("type") != "thinking":
        raise PiProtocolError("Expected content block type 'thinking'")
    redacted = payload.get("redacted", False)
    if not isinstance(redacted, bool):
        raise PiProtocolError("Expected 'redacted' to be a boolean when present")
    return ThinkingContent(
        type="thinking",
        thinking=_require_str(payload, "thinking"),
        thinking_signature=_optional_str(payload, "thinkingSignature"),
        redacted=redacted,
    )


def parse_image_content(payload: Any) -> ImageContent:
    payload = _require_mapping(payload, "image content")
    if payload.get("type") != "image":
        raise PiProtocolError("Expected content block type 'image'")
    return ImageContent(type="image", data=_require_str(payload, "data"), mime_type=_require_str(payload, "mimeType"))


def parse_tool_call(payload: Any) -> ToolCall:
    payload = _require_mapping(payload, "tool call")
    if payload.get("type") != "toolCall":
        raise PiProtocolError("Expected content block type 'toolCall'")
    arguments = payload.get("arguments", {})
    arguments = _require_mapping(arguments, "tool arguments")
    return ToolCall(
        type="toolCall",
        id=_require_str(payload, "id"),
        name=_require_str(payload, "name"),
        arguments=dict(arguments),
        thought_signature=_optional_str(payload, "thoughtSignature"),
    )


def parse_user_content(payload: Any) -> str | tuple[TextContent | ImageContent, ...]:
    if isinstance(payload, str):
        return payload
    if not isinstance(payload, list):
        raise PiProtocolError("Expected user content to be a string or a list")
    blocks: list[TextContent | ImageContent] = []
    for block in payload:
        block = _require_mapping(block, "user content block")
        block_type = block.get("type")
        if block_type == "text":
            blocks.append(parse_text_content(block))
        elif block_type == "image":
            blocks.append(parse_image_content(block))
        else:
            raise PiProtocolError(f"Unsupported user content block type: {block_type!r}")
    return tuple(blocks)


def parse_assistant_content(payload: Any) -> tuple[TextContent | ThinkingContent | ToolCall, ...]:
    if not isinstance(payload, list):
        raise PiProtocolError("Expected assistant content to be a list")
    blocks: list[TextContent | ThinkingContent | ToolCall] = []
    for block in payload:
        block = _require_mapping(block, "assistant content block")
        block_type = block.get("type")
        if block_type == "text":
            blocks.append(parse_text_content(block))
        elif block_type == "thinking":
            blocks.append(parse_thinking_content(block))
        elif block_type == "toolCall":
            blocks.append(parse_tool_call(block))
        else:
            raise PiProtocolError(f"Unsupported assistant content block type: {block_type!r}")
    return tuple(blocks)


def parse_tool_result_content(payload: Any) -> tuple[TextContent | ImageContent, ...]:
    if not isinstance(payload, list):
        raise PiProtocolError("Expected tool result content to be a list")
    blocks: list[TextContent | ImageContent] = []
    for block in payload:
        block = _require_mapping(block, "tool result content block")
        block_type = block.get("type")
        if block_type == "text":
            blocks.append(parse_text_content(block))
        elif block_type == "image":
            blocks.append(parse_image_content(block))
        else:
            raise PiProtocolError(f"Unsupported tool result content block type: {block_type!r}")
    return tuple(blocks)


def serialize_content_block(block: ContentBlock) -> dict[str, Any]:
    if isinstance(block, TextContent):
        payload: dict[str, Any] = {"type": "text", "text": block.text}
        if block.text_signature is not None:
            payload["textSignature"] = block.text_signature
        return payload
    if isinstance(block, ThinkingContent):
        thinking_payload: dict[str, Any] = {"type": "thinking", "thinking": block.thinking}
        if block.thinking_signature is not None:
            thinking_payload["thinkingSignature"] = block.thinking_signature
        if block.redacted:
            thinking_payload["redacted"] = True
        return thinking_payload
    if isinstance(block, ImageContent):
        return {"type": "image", "data": block.data, "mimeType": block.mime_type}
    if isinstance(block, ToolCall):
        tool_payload: dict[str, Any] = {"type": "toolCall", "id": block.id, "name": block.name, "arguments": dict(block.arguments)}
        if block.thought_signature is not None:
            tool_payload["thoughtSignature"] = block.thought_signature
        return tool_payload
    raise TypeError(f"Unsupported content block type: {type(block).__name__}")


def parse_agent_message(payload: Any) -> AgentMessage:
    payload = _require_mapping(payload, "agent message")
    role = payload.get("role")
    if role == "user":
        return UserMessage(role="user", content=parse_user_content(payload.get("content")), timestamp=_require_int(payload, "timestamp"))
    if role == "assistant":
        return AssistantMessage(
            role="assistant",
            content=parse_assistant_content(payload.get("content")),
            api=_require_str(payload, "api"),
            provider=_require_str(payload, "provider"),
            model=_require_str(payload, "model"),
            usage=parse_usage(payload.get("usage", {})),
            stop_reason=_expect_type(payload.get("stopReason"), str, "stopReason"),
            timestamp=_require_int(payload, "timestamp"),
            response_id=_optional_str(payload, "responseId"),
            error_message=_optional_str(payload, "errorMessage"),
        )
    if role == "toolResult":
        return ToolResultMessage(
            role="toolResult",
            tool_call_id=_require_str(payload, "toolCallId"),
            tool_name=_require_str(payload, "toolName"),
            content=parse_tool_result_content(payload.get("content")),
            details=payload.get("details"),
            is_error=_require_bool(payload, "isError"),
            timestamp=_require_int(payload, "timestamp"),
        )
    if role == "bashExecution":
        return BashExecutionMessage(
            role="bashExecution",
            command=_require_str(payload, "command"),
            output=_require_str(payload, "output"),
            exit_code=_optional_int(payload, "exitCode"),
            cancelled=_require_bool(payload, "cancelled"),
            truncated=_require_bool(payload, "truncated"),
            timestamp=_require_int(payload, "timestamp"),
            full_output_path=_optional_str(payload, "fullOutputPath"),
            exclude_from_context=bool(payload.get("excludeFromContext", False)),
        )
    if role == "custom":
        return CustomMessage(
            role="custom",
            custom_type=_require_str(payload, "customType"),
            content=parse_user_content(payload.get("content")),
            display=_require_bool(payload, "display"),
            details=payload.get("details"),
            timestamp=_require_int(payload, "timestamp"),
        )
    if role == "branchSummary":
        return BranchSummaryMessage(
            role="branchSummary",
            summary=_require_str(payload, "summary"),
            from_id=_require_str(payload, "fromId"),
            timestamp=_require_int(payload, "timestamp"),
        )
    if role == "compactionSummary":
        return CompactionSummaryMessage(
            role="compactionSummary",
            summary=_require_str(payload, "summary"),
            tokens_before=_require_int(payload, "tokensBefore"),
            timestamp=_require_int(payload, "timestamp"),
        )
    raise PiProtocolError(f"Unsupported agent message role: {role!r}")


def serialize_agent_message(message: AgentMessage) -> dict[str, Any]:
    if isinstance(message, UserMessage):
        content: Any
        if isinstance(message.content, str):
            content = message.content
        else:
            content = [serialize_content_block(block) for block in message.content]
        return {"role": "user", "content": content, "timestamp": message.timestamp}
    if isinstance(message, AssistantMessage):
        payload = {
            "role": "assistant",
            "content": [serialize_content_block(block) for block in message.content],
            "api": message.api,
            "provider": message.provider,
            "model": message.model,
            "usage": serialize_usage(message.usage),
            "stopReason": message.stop_reason,
            "timestamp": message.timestamp,
        }
        if message.response_id is not None:
            payload["responseId"] = message.response_id
        if message.error_message is not None:
            payload["errorMessage"] = message.error_message
        return payload
    if isinstance(message, ToolResultMessage):
        payload = {
            "role": "toolResult",
            "toolCallId": message.tool_call_id,
            "toolName": message.tool_name,
            "content": [serialize_content_block(block) for block in message.content],
            "isError": message.is_error,
            "timestamp": message.timestamp,
        }
        if message.details is not None:
            payload["details"] = message.details
        return payload
    if isinstance(message, BashExecutionMessage):
        payload = {
            "role": "bashExecution",
            "command": message.command,
            "output": message.output,
            "cancelled": message.cancelled,
            "truncated": message.truncated,
            "timestamp": message.timestamp,
            "excludeFromContext": message.exclude_from_context,
        }
        payload["exitCode"] = message.exit_code
        if message.full_output_path is not None:
            payload["fullOutputPath"] = message.full_output_path
        return payload
    if isinstance(message, CustomMessage):
        content = message.content if isinstance(message.content, str) else [serialize_content_block(block) for block in message.content]
        payload = {
            "role": "custom",
            "customType": message.custom_type,
            "content": content,
            "display": message.display,
            "timestamp": message.timestamp,
        }
        if message.details is not None:
            payload["details"] = message.details
        return payload
    if isinstance(message, BranchSummaryMessage):
        return {"role": "branchSummary", "summary": message.summary, "fromId": message.from_id, "timestamp": message.timestamp}
    if isinstance(message, CompactionSummaryMessage):
        return {
            "role": "compactionSummary",
            "summary": message.summary,
            "tokensBefore": message.tokens_before,
            "timestamp": message.timestamp,
        }
    raise TypeError(f"Unsupported message type: {type(message).__name__}")


def parse_rpc_slash_command(payload: Any) -> RpcSlashCommand:
    payload = _require_mapping(payload, "slash command")
    source = _require_str(payload, "source")
    location = payload.get("location")
    if location is not None and not isinstance(location, str):
        raise PiProtocolError("Expected 'location' to be a string when present")
    return RpcSlashCommand(
        name=_require_str(payload, "name"),
        description=_optional_str(payload, "description"),
        source=cast(Literal["extension", "prompt", "skill"], source),
        location=cast(Literal["user", "project", "path"] | None, location),
        path=_optional_str(payload, "path"),
    )


def serialize_rpc_slash_command(command: RpcSlashCommand) -> dict[str, Any]:
    payload: dict[str, Any] = {"name": command.name, "source": command.source}
    if command.description is not None:
        payload["description"] = command.description
    if command.location is not None:
        payload["location"] = command.location
    if command.path is not None:
        payload["path"] = command.path
    return payload


def parse_session_state(payload: Any) -> RpcSessionState:
    payload = _require_mapping(payload, "session state")
    model_payload = payload.get("model")
    model = None if model_payload is None else parse_model(model_payload)
    return RpcSessionState(
        model=model,
        thinking_level=cast(ThinkingLevel, _require_str(payload, "thinkingLevel")),
        is_streaming=_require_bool(payload, "isStreaming"),
        is_compacting=_require_bool(payload, "isCompacting"),
        steering_mode=cast(QueueMode, _require_str(payload, "steeringMode")),
        follow_up_mode=cast(QueueMode, _require_str(payload, "followUpMode")),
        session_file=_optional_str(payload, "sessionFile"),
        session_id=_require_str(payload, "sessionId"),
        session_name=_optional_str(payload, "sessionName"),
        auto_compaction_enabled=_require_bool(payload, "autoCompactionEnabled"),
        message_count=_require_int(payload, "messageCount"),
        pending_message_count=_require_int(payload, "pendingMessageCount"),
    )


def serialize_session_state(state: RpcSessionState) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": None if state.model is None else serialize_model(state.model),
        "thinkingLevel": state.thinking_level,
        "isStreaming": state.is_streaming,
        "isCompacting": state.is_compacting,
        "steeringMode": state.steering_mode,
        "followUpMode": state.follow_up_mode,
        "sessionId": state.session_id,
        "autoCompactionEnabled": state.auto_compaction_enabled,
        "messageCount": state.message_count,
        "pendingMessageCount": state.pending_message_count,
    }
    if state.session_file is not None:
        payload["sessionFile"] = state.session_file
    if state.session_name is not None:
        payload["sessionName"] = state.session_name
    return payload


def parse_assistant_message_event(payload: Any) -> AssistantMessageEvent:
    payload = _require_mapping(payload, "assistant message event")
    event_type = _require_str(payload, "type")
    partial_payload = payload.get("partial")
    partial = None if partial_payload is None else parse_agent_message(partial_payload)
    if partial is not None and not isinstance(partial, AssistantMessage):
        raise PiProtocolError("Expected assistantMessageEvent.partial to be an assistant message")
    tool_call_payload = payload.get("toolCall")
    message_payload = payload.get("message")
    error_payload = payload.get("error")
    message = None if message_payload is None else parse_agent_message(message_payload)
    error = None if error_payload is None else parse_agent_message(error_payload)
    if message is not None and not isinstance(message, AssistantMessage):
        raise PiProtocolError("Expected assistantMessageEvent.message to be an assistant message")
    if error is not None and not isinstance(error, AssistantMessage):
        raise PiProtocolError("Expected assistantMessageEvent.error to be an assistant message")
    return AssistantMessageEvent(
        type=cast(AssistantEventType, event_type),
        partial=partial,
        content_index=payload.get("contentIndex") if isinstance(payload.get("contentIndex"), int) else None,
        delta=payload.get("delta") if isinstance(payload.get("delta"), str) else None,
        content=payload.get("content") if isinstance(payload.get("content"), str) else None,
        tool_call=None if tool_call_payload is None else parse_tool_call(tool_call_payload),
        reason=payload.get("reason") if isinstance(payload.get("reason"), str) else None,
        message=message,
        error=error,
    )


def serialize_assistant_message_event(event: AssistantMessageEvent) -> dict[str, Any]:
    payload: dict[str, Any] = {"type": event.type}
    if event.partial is not None:
        payload["partial"] = serialize_agent_message(event.partial)
    if event.content_index is not None:
        payload["contentIndex"] = event.content_index
    if event.delta is not None:
        payload["delta"] = event.delta
    if event.content is not None:
        payload["content"] = event.content
    if event.tool_call is not None:
        payload["toolCall"] = serialize_content_block(event.tool_call)
    if event.reason is not None:
        payload["reason"] = event.reason
    if event.message is not None:
        payload["message"] = serialize_agent_message(event.message)
    if event.error is not None:
        payload["error"] = serialize_agent_message(event.error)
    return payload


def parse_tool_execution_result(payload: Any) -> ToolExecutionResult:
    payload = _require_mapping(payload, "tool execution result")
    return ToolExecutionResult(content=parse_tool_result_content(payload.get("content", [])), details=payload.get("details"))


def serialize_tool_execution_result(result: ToolExecutionResult) -> dict[str, Any]:
    payload: dict[str, Any] = {"content": [serialize_content_block(block) for block in result.content]}
    if result.details is not None:
        payload["details"] = result.details
    return payload
