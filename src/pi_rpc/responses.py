from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from .exceptions import PiCommandError, PiProtocolError
from .models import (
    BashResult,
    CompactionResult,
    CycleModelResult,
    CycleThinkingLevelResult,
    ExportHtmlResult,
    ForkMessage,
    ForkResult,
    LastAssistantTextResult,
    SessionStats,
    SessionStatsTokens,
    SessionTransitionResult,
)
from .protocol_types import (
    parse_agent_message,
    parse_model,
    parse_rpc_slash_command,
    parse_session_state,
)

T = TypeVar("T")


@dataclass(frozen=True)
class RpcResponse(Generic[T]):
    command: str
    success: bool
    request_id: str | None = None
    data: T | None = None
    error: str | None = None

    def raise_for_error(self) -> None:
        if not self.success:
            raise PiCommandError(self.command, self.error or "Command failed", self.request_id)


def _require_response(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise PiProtocolError(f"Expected response object, got {type(payload).__name__}")
    if payload.get("type") != "response":
        raise PiProtocolError(f"Expected response record, got {payload.get('type')!r}")
    command = payload.get("command")
    if not isinstance(command, str):
        raise PiProtocolError("Expected response.command to be a string")
    success = payload.get("success")
    if not isinstance(success, bool):
        raise PiProtocolError("Expected response.success to be a boolean")
    request_id = payload.get("id")
    if request_id is not None and not isinstance(request_id, str):
        raise PiProtocolError("Expected response.id to be a string when present")
    return payload


NO_DATA_COMMANDS = {
    "prompt",
    "steer",
    "follow_up",
    "abort",
    "set_thinking_level",
    "set_steering_mode",
    "set_follow_up_mode",
    "set_auto_compaction",
    "set_auto_retry",
    "abort_retry",
    "abort_bash",
    "set_session_name",
}


def parse_response(payload: Any) -> RpcResponse[Any]:
    payload = _require_response(payload)
    command = payload["command"]
    request_id = payload.get("id")
    if not payload["success"]:
        error = payload.get("error")
        if not isinstance(error, str):
            raise PiProtocolError("Expected response.error to be a string for unsuccessful responses")
        return RpcResponse(command=command, success=False, request_id=request_id, error=error)

    data = payload.get("data")
    parsed: Any = None

    if command in NO_DATA_COMMANDS:
        parsed = None
    elif command in {"new_session", "switch_session"}:
        if not isinstance(data, dict):
            raise PiProtocolError(f"Expected data object for '{command}'")
        cancelled = data.get("cancelled")
        if not isinstance(cancelled, bool):
            raise PiProtocolError(f"Expected '{command}.data.cancelled' to be a boolean")
        parsed = SessionTransitionResult(cancelled=cancelled)
    elif command == "get_state":
        parsed = parse_session_state(data)
    elif command == "get_messages":
        if not isinstance(data, dict) or not isinstance(data.get("messages"), list):
            raise PiProtocolError("Expected get_messages data.messages to be a list")
        parsed = [parse_agent_message(item) for item in data["messages"]]
    elif command == "set_model":
        parsed = parse_model(data)
    elif command == "cycle_model":
        if data is None:
            parsed = None
        else:
            if not isinstance(data, dict):
                raise PiProtocolError("Expected cycle_model data to be null or an object")
            model = parse_model(data.get("model"))
            thinking_level = data.get("thinkingLevel")
            is_scoped = data.get("isScoped")
            if not isinstance(thinking_level, str) or not isinstance(is_scoped, bool):
                raise PiProtocolError("Invalid cycle_model payload")
            parsed = CycleModelResult(model=model, thinking_level=thinking_level, is_scoped=is_scoped)
    elif command == "get_available_models":
        if not isinstance(data, dict) or not isinstance(data.get("models"), list):
            raise PiProtocolError("Expected get_available_models data.models to be a list")
        parsed = [parse_model(item) for item in data["models"]]
    elif command == "cycle_thinking_level":
        if data is None:
            parsed = None
        else:
            if not isinstance(data, dict) or not isinstance(data.get("level"), str):
                raise PiProtocolError("Expected cycle_thinking_level data.level to be a string")
            parsed = CycleThinkingLevelResult(level=data["level"])
    elif command == "compact":
        if not isinstance(data, dict):
            raise PiProtocolError("Expected compact data to be an object")
        details = data.get("details", {})
        if not isinstance(details, dict):
            raise PiProtocolError("Expected compact details to be an object")
        parsed = CompactionResult(
            summary=str(data.get("summary", "")),
            first_kept_entry_id=str(data.get("firstKeptEntryId", "")),
            tokens_before=int(data.get("tokensBefore", 0)),
            details=dict(details),
        )
    elif command == "bash":
        if not isinstance(data, dict):
            raise PiProtocolError("Expected bash data to be an object")
        exit_code = data.get("exitCode")
        if exit_code is not None and not isinstance(exit_code, int):
            raise PiProtocolError("Expected bash exitCode to be an integer when present")
        cancelled = data.get("cancelled")
        truncated = data.get("truncated")
        if not isinstance(cancelled, bool) or not isinstance(truncated, bool):
            raise PiProtocolError("Expected bash cancelled/truncated fields to be booleans")
        parsed = BashResult(
            output=str(data.get("output", "")),
            exit_code=exit_code,
            cancelled=cancelled,
            truncated=truncated,
            full_output_path=data.get("fullOutputPath") if isinstance(data.get("fullOutputPath"), str) else None,
        )
    elif command == "get_session_stats":
        if not isinstance(data, dict):
            raise PiProtocolError("Expected get_session_stats data to be an object")
        tokens = data.get("tokens")
        if not isinstance(tokens, dict):
            raise PiProtocolError("Expected session stats tokens to be an object")
        parsed = SessionStats(
            session_file=str(data.get("sessionFile", "")),
            session_id=str(data.get("sessionId", "")),
            user_messages=int(data.get("userMessages", 0)),
            assistant_messages=int(data.get("assistantMessages", 0)),
            tool_calls=int(data.get("toolCalls", 0)),
            tool_results=int(data.get("toolResults", 0)),
            total_messages=int(data.get("totalMessages", 0)),
            tokens=SessionStatsTokens(
                input=int(tokens.get("input", 0)),
                output=int(tokens.get("output", 0)),
                cache_read=int(tokens.get("cacheRead", 0)),
                cache_write=int(tokens.get("cacheWrite", 0)),
                total=int(tokens.get("total", 0)),
            ),
            cost=float(data.get("cost", 0.0)),
        )
    elif command == "export_html":
        if not isinstance(data, dict) or not isinstance(data.get("path"), str):
            raise PiProtocolError("Expected export_html data.path to be a string")
        parsed = ExportHtmlResult(path=data["path"])
    elif command == "fork":
        if not isinstance(data, dict):
            raise PiProtocolError("Expected fork data to be an object")
        cancelled = data.get("cancelled")
        if not isinstance(cancelled, bool):
            raise PiProtocolError("Expected fork data.cancelled to be a boolean")
        parsed = ForkResult(text=str(data.get("text", "")), cancelled=cancelled)
    elif command == "get_fork_messages":
        if not isinstance(data, dict) or not isinstance(data.get("messages"), list):
            raise PiProtocolError("Expected get_fork_messages data.messages to be a list")
        parsed = [ForkMessage(entry_id=str(item.get("entryId", "")), text=str(item.get("text", ""))) for item in data["messages"] if isinstance(item, dict)]
    elif command == "get_last_assistant_text":
        if not isinstance(data, dict):
            raise PiProtocolError("Expected get_last_assistant_text data to be an object")
        text = data.get("text")
        if text is not None and not isinstance(text, str):
            raise PiProtocolError("Expected get_last_assistant_text data.text to be a string or null")
        parsed = LastAssistantTextResult(text=text)
    elif command == "get_commands":
        if not isinstance(data, dict) or not isinstance(data.get("commands"), list):
            raise PiProtocolError("Expected get_commands data.commands to be a list")
        parsed = [parse_rpc_slash_command(item) for item in data["commands"]]
    else:
        parsed = data

    return RpcResponse(command=command, success=True, request_id=request_id, data=parsed)


def unwrap_response(response: RpcResponse[T]) -> T | None:
    response.raise_for_error()
    return response.data
