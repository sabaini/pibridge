from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from .protocol_types import ModelInfo


@dataclass(frozen=True)
class SessionTransitionResult:
    cancelled: bool


@dataclass(frozen=True)
class CycleModelResult:
    model: ModelInfo
    thinking_level: str
    is_scoped: bool


@dataclass(frozen=True)
class CycleThinkingLevelResult:
    level: str


@dataclass(frozen=True)
class CompactionResult:
    summary: str
    first_kept_entry_id: str
    tokens_before: int
    details: dict[str, Any]


@dataclass(frozen=True)
class BashResult:
    output: str
    exit_code: int | None
    cancelled: bool
    truncated: bool
    full_output_path: str | None = None


@dataclass(frozen=True)
class ForkResult:
    text: str
    cancelled: bool


@dataclass(frozen=True)
class ForkMessage:
    entry_id: str
    text: str


@dataclass(frozen=True)
class ExportHtmlResult:
    path: str


@dataclass(frozen=True)
class SessionStatsTokens:
    input: int
    output: int
    cache_read: int
    cache_write: int
    total: int


@dataclass(frozen=True)
class SessionStats:
    session_file: str
    session_id: str
    user_messages: int
    assistant_messages: int
    tool_calls: int
    tool_results: int
    total_messages: int
    tokens: SessionStatsTokens
    cost: float


@dataclass(frozen=True)
class LastAssistantTextResult:
    text: str | None


@dataclass(frozen=True)
class PiClientOptions:
    executable: str = "pi"
    provider: str | None = None
    model: str | None = None
    no_session: bool = False
    session_dir: str | None = None
    cwd: str | None = None
    env: Mapping[str, str] | None = None
    startup_timeout: float = 10.0
    command_timeout: float = 30.0
    idle_timeout: float | None = None
    extra_args: tuple[str, ...] = ()
    process_factory: Callable[..., Any] | None = None
    auto_close_subscriptions: bool = True

    def build_env(self) -> dict[str, str] | None:
        return dict(self.env) if self.env is not None else None
