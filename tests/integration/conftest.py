from __future__ import annotations

import json
import os
import queue
import shutil
import time
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

import pytest

from pi_rpc import PiClient, PiClientOptions
from pi_rpc.events import AgentEvent

MOCK_PROVIDER_NAME = "pi-rpc-mock"
MOCK_MODEL_ID = "canned-responses"
MOCK_API_KEY_ENV = "PI_RPC_MOCK_API_KEY"
MOCK_PROMPT_MAP_ENV = "PI_RPC_MOCK_PROMPT_MAP"
MOCK_CONTEXT_MAP_ENV = "PI_RPC_MOCK_CONTEXT_MAP"
MOCK_EXTENSION_PATH = Path(__file__).resolve().parent / "fixtures" / "mock_provider.ts"
RPC_UI_DEMO_EXTENSION_PATH = Path(__file__).resolve().parent / "fixtures" / "rpc_ui_demo.ts"
DEFAULT_MOCK_PROMPT_MAP = {
    "Reply with exactly: OK": "OK",
    "Respond with the word BRIDGE.": "BRIDGE",
    "Respond with the word TESTING.": "TESTING",
}


_REQUIRED_ENV_VALUES = {"1", "true", "yes", "on"}


def _live_override_enabled() -> bool:
    return bool(os.environ.get("PI_RPC_PROVIDER") and os.environ.get("PI_RPC_MODEL"))


def _integration_required() -> bool:
    return os.environ.get("PI_RPC_REQUIRE_INTEGRATION", "").strip().lower() in _REQUIRED_ENV_VALUES


def _integration_ready() -> tuple[bool, str]:
    if shutil.which("pi") is None:
        return False, "pi executable not found on PATH"
    if not MOCK_EXTENSION_PATH.exists():
        return False, f"mock extension fixture not found: {MOCK_EXTENSION_PATH}"
    if not RPC_UI_DEMO_EXTENSION_PATH.exists():
        return False, f"RPC UI demo extension fixture not found: {RPC_UI_DEMO_EXTENSION_PATH}"
    return True, ""


def _integration_availability_outcome(*, ready: bool, reason: str, required: bool) -> tuple[str, str]:
    if ready:
        return "ready", ""
    if required:
        return "fail", f"Integration tests are required but unavailable: {reason}"
    return "skip", reason


@pytest.fixture(scope="session")
def integration_ready() -> None:
    ready, reason = _integration_ready()
    outcome, message = _integration_availability_outcome(ready=ready, reason=reason, required=_integration_required())
    if outcome == "fail":
        pytest.fail(message)
    if outcome == "skip":
        pytest.skip(message)


@pytest.fixture(scope="session")
def mock_prompt_map() -> dict[str, str]:
    return dict(DEFAULT_MOCK_PROMPT_MAP)


@pytest.fixture(scope="session")
def command_timeout() -> float:
    return float(os.environ.get("PI_RPC_COMMAND_TIMEOUT", "120"))


@pytest.fixture(scope="session")
def mock_context_map() -> dict[str, str]:
    return {}


def _text_content(content: str | list[dict[str, str]]) -> str:
    if isinstance(content, str):
        return content
    return "".join(block["text"] for block in content if block.get("type") == "text")


def mock_user_message(content: str | list[dict[str, str]]) -> dict[str, str]:
    return {"role": "user", "content": _text_content(content)}


def mock_assistant_message(content: str) -> dict[str, str]:
    return {"role": "assistant", "content": content}


def mock_tool_result_message(tool_name: str, content: str) -> dict[str, str]:
    return {"role": "toolResult", "toolName": tool_name, "content": content}


def mock_context_key(*messages: dict[str, str]) -> str:
    return json.dumps(list(messages), sort_keys=True, separators=(",", ":"))


def bash_execution_context_text(
    command: str,
    output: str,
    *,
    exit_code: int | None = 0,
    cancelled: bool = False,
    truncated: bool = False,
    full_output_path: str | None = None,
) -> str:
    text = f"Ran `{command}`\n"
    if output:
        text += f"```\n{output}\n```"
    else:
        text += "(no output)"
    if cancelled:
        text += "\n\n(command cancelled)"
    elif exit_code not in (None, 0):
        text += f"\n\nCommand exited with code {exit_code}"
    if truncated and full_output_path:
        text += f"\n\n[Output truncated. Full output: {full_output_path}]"
    return text


@pytest.fixture
def isolated_pi_workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return workspace


def _mock_env(prompt_map: Mapping[str, Any], context_map: Mapping[str, Any]) -> dict[str, str]:
    return {
        MOCK_API_KEY_ENV: "pi-rpc-mock-test-key",
        MOCK_PROMPT_MAP_ENV: json.dumps(dict(prompt_map), sort_keys=True),
        MOCK_CONTEXT_MAP_ENV: json.dumps(dict(context_map), sort_keys=True),
    }


def _make_client(
    *,
    workspace: Path,
    command_timeout: float,
    provider: str | None = None,
    model: str | None = None,
    extra_args: tuple[str, ...] = (),
    env: Mapping[str, str] | None = None,
) -> PiClient:
    session_dir = workspace / "sessions"
    session_dir.mkdir()
    options = PiClientOptions(
        provider=provider,
        model=model,
        cwd=str(workspace),
        session_dir=str(session_dir),
        command_timeout=command_timeout,
        extra_args=extra_args,
        env=env,
    )
    return PiClient(options)


@pytest.fixture
def pi_client(
    integration_ready: None,
    isolated_pi_workspace: Path,
    command_timeout: float,
    mock_prompt_map: dict[str, str],
    mock_context_map: dict[str, str],
) -> Iterator[PiClient]:
    if _live_override_enabled():
        client = _make_client(
            workspace=isolated_pi_workspace,
            command_timeout=command_timeout,
            provider=os.environ["PI_RPC_PROVIDER"],
            model=os.environ["PI_RPC_MODEL"],
        )
    else:
        client = _make_client(
            workspace=isolated_pi_workspace,
            command_timeout=command_timeout,
            extra_args=("-e", str(MOCK_EXTENSION_PATH)),
            env=_mock_env(mock_prompt_map, mock_context_map),
        )
    with client:
        yield client


@pytest.fixture
def live_pi_client(
    integration_ready: None,
    isolated_pi_workspace: Path,
    command_timeout: float,
) -> Iterator[PiClient]:
    if not _live_override_enabled():
        pytest.skip("live backend requires PI_RPC_PROVIDER and PI_RPC_MODEL")
    client = _make_client(
        workspace=isolated_pi_workspace,
        command_timeout=command_timeout,
        provider=os.environ["PI_RPC_PROVIDER"],
        model=os.environ["PI_RPC_MODEL"],
    )
    with client:
        yield client


@pytest.fixture
def mock_pi_client(
    integration_ready: None,
    isolated_pi_workspace: Path,
    command_timeout: float,
    mock_prompt_map: dict[str, str],
    mock_context_map: dict[str, str],
) -> Iterator[PiClient]:
    client = _make_client(
        workspace=isolated_pi_workspace,
        command_timeout=command_timeout,
        extra_args=("-e", str(MOCK_EXTENSION_PATH)),
        env=_mock_env(mock_prompt_map, mock_context_map),
    )
    with client:
        available_models = client.get_available_models()
        assert any(model.provider == MOCK_PROVIDER_NAME and model.id == MOCK_MODEL_ID for model in available_models)
        selected_model = client.set_model(MOCK_PROVIDER_NAME, MOCK_MODEL_ID)
        assert selected_model.provider == MOCK_PROVIDER_NAME
        assert selected_model.id == MOCK_MODEL_ID
        state = client.get_state()
        assert state.model is not None
        assert state.model.provider == MOCK_PROVIDER_NAME
        assert state.model.id == MOCK_MODEL_ID
        yield client


@pytest.fixture
def mock_extension_ui_client(
    integration_ready: None,
    isolated_pi_workspace: Path,
    command_timeout: float,
    mock_prompt_map: dict[str, str],
    mock_context_map: dict[str, str],
) -> Iterator[PiClient]:
    client = _make_client(
        workspace=isolated_pi_workspace,
        command_timeout=command_timeout,
        extra_args=("-e", str(MOCK_EXTENSION_PATH), "-e", str(RPC_UI_DEMO_EXTENSION_PATH)),
        env=_mock_env(mock_prompt_map, mock_context_map),
    )
    with client:
        available_models = client.get_available_models()
        assert any(model.provider == MOCK_PROVIDER_NAME and model.id == MOCK_MODEL_ID for model in available_models)
        selected_model = client.set_model(MOCK_PROVIDER_NAME, MOCK_MODEL_ID)
        assert selected_model.provider == MOCK_PROVIDER_NAME
        assert selected_model.id == MOCK_MODEL_ID
        state = client.get_state()
        assert state.model is not None
        assert state.model.provider == MOCK_PROVIDER_NAME
        assert state.model.id == MOCK_MODEL_ID
        yield client


def _wait_for_agent_end(subscription: queue.Queue[AgentEvent], timeout: float = 120.0) -> AgentEvent:
    deadline = time.monotonic() + timeout
    last_event: AgentEvent | None = None
    while time.monotonic() < deadline:
        remaining = max(0.1, min(1.0, deadline - time.monotonic()))
        try:
            event = subscription.get(timeout=remaining)
        except queue.Empty:
            continue
        last_event = event
        if event.type == "agent_end":
            return event
    raise AssertionError(f"timed out waiting for agent_end; last event: {last_event!r}")


def _wait_for_event(subscription: queue.Queue[AgentEvent], event_type: str, timeout: float = 120.0) -> AgentEvent:
    deadline = time.monotonic() + timeout
    last_event: AgentEvent | None = None
    while time.monotonic() < deadline:
        remaining = max(0.1, min(1.0, deadline - time.monotonic()))
        try:
            event = subscription.get(timeout=remaining)
        except queue.Empty:
            continue
        last_event = event
        if event.type == event_type:
            return event
    raise AssertionError(f"timed out waiting for {event_type}; last event: {last_event!r}")


def _prompt_and_get_text(client: PiClient, prompt: str, timeout: float = 120.0) -> str:
    subscription = client.subscribe_events(maxsize=200)
    client.prompt(prompt, timeout=timeout)
    _wait_for_agent_end(subscription, timeout=timeout)
    text = client.get_last_assistant_text(timeout=timeout)
    assert text is not None
    return text
