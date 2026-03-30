from __future__ import annotations

from typing import Any, cast

from .commands import RpcCommand, make_command
from .events import AgentEvent
from .models import (
    BashResult,
    CompactionResult,
    CycleModelResult,
    CycleThinkingLevelResult,
    ExportHtmlResult,
    ForkMessage,
    ForkResult,
    LastAssistantTextResult,
    PiClientOptions,
    SessionStats,
    SessionTransitionResult,
)
from .process import PiProcess
from .protocol_types import (
    AgentMessage,
    ImageContent,
    ModelInfo,
    QueueMode,
    RpcSessionState,
    RpcSlashCommand,
    StreamingBehavior,
    ThinkingLevel,
)
from .responses import RpcResponse, unwrap_response
from .subscriptions import EventSubscription


class PiClient:
    def __init__(self, options: PiClientOptions | None = None, **kwargs: Any) -> None:
        self.options = options or PiClientOptions(**kwargs)
        self._process = PiProcess(self.options)

    def __enter__(self) -> PiClient:
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()

    def close(self) -> None:
        self._process.close()

    def subscribe_events(self, maxsize: int = 1000) -> EventSubscription[AgentEvent]:
        return self._process.subscribe_events(maxsize=maxsize)

    def send_command(self, request: RpcCommand | str, timeout: float | None = None, **fields: Any) -> RpcResponse[Any]:
        if isinstance(request, str):
            request = make_command(request, **fields)
        return self._process.send_command(request, timeout=timeout)

    def prompt(
        self,
        message: str,
        *,
        images: list[ImageContent] | None = None,
        streaming_behavior: StreamingBehavior | None = None,
        timeout: float | None = None,
    ) -> None:
        fields: dict[str, Any] = {"message": message}
        if images is not None:
            fields["images"] = images
        if streaming_behavior is not None:
            fields["streamingBehavior"] = streaming_behavior
        unwrap_response(self.send_command("prompt", timeout=timeout, **fields))

    def continue_prompt(self, message: str, *, images: list[ImageContent] | None = None, timeout: float | None = None) -> None:
        self.prompt(message, images=images, streaming_behavior="followUp", timeout=timeout)

    def steer(self, message: str, *, images: list[ImageContent] | None = None, timeout: float | None = None) -> None:
        fields: dict[str, Any] = {"message": message}
        if images is not None:
            fields["images"] = images
        unwrap_response(self.send_command("steer", timeout=timeout, **fields))

    def follow_up(self, message: str, *, images: list[ImageContent] | None = None, timeout: float | None = None) -> None:
        fields: dict[str, Any] = {"message": message}
        if images is not None:
            fields["images"] = images
        unwrap_response(self.send_command("follow_up", timeout=timeout, **fields))

    def abort(self, *, timeout: float | None = None) -> None:
        unwrap_response(self.send_command("abort", timeout=timeout))

    def new_session(self, *, parent_session: str | None = None, timeout: float | None = None) -> SessionTransitionResult:
        fields: dict[str, Any] = {}
        if parent_session is not None:
            fields["parentSession"] = parent_session
        return cast(SessionTransitionResult, unwrap_response(self.send_command("new_session", timeout=timeout, **fields)))

    def get_state(self, *, timeout: float | None = None) -> RpcSessionState:
        return cast(RpcSessionState, unwrap_response(self.send_command("get_state", timeout=timeout)))

    def get_messages(self, *, timeout: float | None = None) -> list[AgentMessage]:
        return cast(list[AgentMessage], unwrap_response(self.send_command("get_messages", timeout=timeout)))

    def set_model(self, provider: str, model_id: str, *, timeout: float | None = None) -> ModelInfo:
        return cast(ModelInfo, unwrap_response(self.send_command("set_model", timeout=timeout, provider=provider, modelId=model_id)))

    def cycle_model(self, *, timeout: float | None = None) -> CycleModelResult | None:
        return unwrap_response(self.send_command("cycle_model", timeout=timeout))

    def get_available_models(self, *, timeout: float | None = None) -> list[ModelInfo]:
        return cast(list[ModelInfo], unwrap_response(self.send_command("get_available_models", timeout=timeout)))

    def set_thinking_level(self, level: ThinkingLevel, *, timeout: float | None = None) -> None:
        unwrap_response(self.send_command("set_thinking_level", timeout=timeout, level=level))

    def cycle_thinking_level(self, *, timeout: float | None = None) -> CycleThinkingLevelResult | None:
        return unwrap_response(self.send_command("cycle_thinking_level", timeout=timeout))

    def set_steering_mode(self, mode: QueueMode, *, timeout: float | None = None) -> None:
        unwrap_response(self.send_command("set_steering_mode", timeout=timeout, mode=mode))

    def set_follow_up_mode(self, mode: QueueMode, *, timeout: float | None = None) -> None:
        unwrap_response(self.send_command("set_follow_up_mode", timeout=timeout, mode=mode))

    def compact(self, *, custom_instructions: str | None = None, timeout: float | None = None) -> CompactionResult:
        fields: dict[str, Any] = {}
        if custom_instructions is not None:
            fields["customInstructions"] = custom_instructions
        return cast(CompactionResult, unwrap_response(self.send_command("compact", timeout=timeout, **fields)))

    def set_auto_compaction(self, enabled: bool, *, timeout: float | None = None) -> None:
        unwrap_response(self.send_command("set_auto_compaction", timeout=timeout, enabled=enabled))

    def set_auto_retry(self, enabled: bool, *, timeout: float | None = None) -> None:
        unwrap_response(self.send_command("set_auto_retry", timeout=timeout, enabled=enabled))

    def abort_retry(self, *, timeout: float | None = None) -> None:
        unwrap_response(self.send_command("abort_retry", timeout=timeout))

    def bash(self, command: str, *, timeout: float | None = None) -> BashResult:
        return cast(BashResult, unwrap_response(self.send_command("bash", timeout=timeout, command=command)))

    def abort_bash(self, *, timeout: float | None = None) -> None:
        unwrap_response(self.send_command("abort_bash", timeout=timeout))

    def get_session_stats(self, *, timeout: float | None = None) -> SessionStats:
        return cast(SessionStats, unwrap_response(self.send_command("get_session_stats", timeout=timeout)))

    def export_html(self, *, output_path: str | None = None, timeout: float | None = None) -> ExportHtmlResult:
        fields: dict[str, Any] = {}
        if output_path is not None:
            fields["outputPath"] = output_path
        return cast(ExportHtmlResult, unwrap_response(self.send_command("export_html", timeout=timeout, **fields)))

    def switch_session(self, session_path: str, *, timeout: float | None = None) -> SessionTransitionResult:
        return cast(SessionTransitionResult, unwrap_response(self.send_command("switch_session", timeout=timeout, sessionPath=session_path)))

    def fork(self, entry_id: str, *, timeout: float | None = None) -> ForkResult:
        return cast(ForkResult, unwrap_response(self.send_command("fork", timeout=timeout, entryId=entry_id)))

    def get_fork_messages(self, *, timeout: float | None = None) -> list[ForkMessage]:
        return cast(list[ForkMessage], unwrap_response(self.send_command("get_fork_messages", timeout=timeout)))

    def get_last_assistant_text(self, *, timeout: float | None = None) -> str | None:
        result = unwrap_response(self.send_command("get_last_assistant_text", timeout=timeout))
        assert isinstance(result, LastAssistantTextResult)
        return result.text

    def set_session_name(self, name: str, *, timeout: float | None = None) -> None:
        unwrap_response(self.send_command("set_session_name", timeout=timeout, name=name))

    def get_commands(self, *, timeout: float | None = None) -> list[RpcSlashCommand]:
        return cast(list[RpcSlashCommand], unwrap_response(self.send_command("get_commands", timeout=timeout)))
