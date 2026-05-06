from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from .protocol_types import ImageContent, serialize_content_block


@dataclass(frozen=True)
class RpcCommand:
    type: str
    id: str | None = None
    fields: Mapping[str, Any] = field(default_factory=dict)


SUPPORTED_COMMANDS = {
    "prompt",
    "steer",
    "follow_up",
    "abort",
    "new_session",
    "get_state",
    "get_messages",
    "set_model",
    "cycle_model",
    "get_available_models",
    "set_thinking_level",
    "cycle_thinking_level",
    "set_steering_mode",
    "set_follow_up_mode",
    "compact",
    "set_auto_compaction",
    "set_auto_retry",
    "abort_retry",
    "bash",
    "abort_bash",
    "get_session_stats",
    "export_html",
    "switch_session",
    "fork",
    "get_fork_messages",
    "get_last_assistant_text",
    "set_session_name",
    "get_commands",
}


def make_command(command_type: str, *, request_id: str | None = None, **fields: Any) -> RpcCommand:
    return RpcCommand(type=command_type, id=request_id, fields=fields)


def ensure_command_id(command: RpcCommand) -> RpcCommand:
    if command.id is not None:
        return command
    return RpcCommand(type=command.type, id=str(uuid4()), fields=dict(command.fields))


def serialize_command(command: RpcCommand | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(command, Mapping):
        payload = dict(command)
    else:
        payload = {"type": command.type, **dict(command.fields)}
        if command.id is not None:
            payload["id"] = command.id
    if payload.get("type") not in SUPPORTED_COMMANDS:
        raise ValueError(f"Unsupported command type: {payload.get('type')!r}")
    if "images" in payload and payload["images"] is not None:
        payload["images"] = [serialize_content_block(image) if isinstance(image, ImageContent) else image for image in payload["images"]]
    return payload
