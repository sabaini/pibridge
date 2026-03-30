from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from collections.abc import Callable
from typing import Any

import pytest

from pi_rpc.commands import make_command
from pi_rpc.events import AgentStartEvent, ExtensionUiRequestEvent
from pi_rpc.exceptions import PiCommandError, PiProcessExitedError, PiStartupError, PiTimeoutError
from pi_rpc.jsonl import JsonlReader, serialize_json_line
from pi_rpc.models import PiClientOptions
from pi_rpc.process import PiProcess
from pi_rpc.protocol_types import ConfirmExtensionUiRequest, NotifyExtensionUiRequest


class FakeReadable:
    def __init__(self) -> None:
        self._buffer = bytearray()
        self._closed = False
        self._condition = threading.Condition()

    def push(self, data: bytes) -> None:
        with self._condition:
            self._buffer.extend(data)
            self._condition.notify_all()

    def read(self, size: int = -1) -> bytes:
        with self._condition:
            while not self._buffer and not self._closed:
                self._condition.wait(timeout=0.1)
            if not self._buffer and self._closed:
                return b""
            if size < 0 or size >= len(self._buffer):
                data = bytes(self._buffer)
                self._buffer.clear()
                return data
            data = bytes(self._buffer[:size])
            del self._buffer[:size]
            return data

    def close(self) -> None:
        with self._condition:
            self._closed = True
            self._condition.notify_all()


class FakeWritable:
    def __init__(self, on_write: Callable[[bytes], None]) -> None:
        self._on_write = on_write
        self._closed = False

    def write(self, data: bytes) -> int:
        if self._closed:
            raise BrokenPipeError("stdin closed")
        self._on_write(data)
        return len(data)

    def flush(self) -> None:
        return None

    def close(self) -> None:
        self._closed = True


class FakeChildProcess:
    def __init__(self) -> None:
        self.stdout = FakeReadable()
        self.stderr = FakeReadable()
        self._stdin_reader = JsonlReader()
        self.commands: list[dict[str, Any]] = []
        self.on_command: Callable[[dict[str, Any]], None] | None = None
        self.stdin = FakeWritable(self._handle_write)
        self._returncode: int | None = None
        self.terminate_calls = 0
        self.kill_calls = 0
        self.wait_calls = 0

    def _handle_write(self, data: bytes) -> None:
        for line in self._stdin_reader.feed(data):
            payload = json.loads(line)
            self.commands.append(payload)
            if self.on_command is not None:
                self.on_command(payload)

    def send_record(self, payload: dict[str, Any]) -> None:
        self.stdout.push(serialize_json_line(payload))

    def send_stderr(self, text: str) -> None:
        self.stderr.push(text.encode("utf-8"))

    def exit(self, returncode: int = 0) -> None:
        self._returncode = returncode
        self.stdout.close()
        self.stderr.close()

    def poll(self) -> int | None:
        return self._returncode

    def terminate(self) -> None:
        self.terminate_calls += 1
        self.exit(0)

    def kill(self) -> None:
        self.kill_calls += 1
        self.exit(-9)

    def wait(self, timeout: float | None = None) -> int:
        self.wait_calls += 1
        end = None if timeout is None else time.monotonic() + timeout
        while self._returncode is None:
            if end is not None and time.monotonic() > end:
                raise subprocess.TimeoutExpired("fake", timeout)
            time.sleep(0.01)
        return self._returncode


def state_response(request_id: str, session_id: str = "session") -> dict[str, Any]:
    return {
        "id": request_id,
        "type": "response",
        "command": "get_state",
        "success": True,
        "data": {
            "model": None,
            "thinkingLevel": "medium",
            "isStreaming": False,
            "isCompacting": False,
            "steeringMode": "all",
            "followUpMode": "one-at-a-time",
            "sessionId": session_id,
            "autoCompactionEnabled": True,
            "messageCount": 0,
            "pendingMessageCount": 0,
        },
    }


def success_response(request_id: str, command: str) -> dict[str, Any]:
    return {"id": request_id, "type": "response", "command": command, "success": True}


def make_process(children: list[FakeChildProcess]) -> PiProcess:
    def factory(*args: Any, **kwargs: Any) -> FakeChildProcess:
        child = FakeChildProcess()
        children.append(child)
        return child

    return PiProcess(PiClientOptions(process_factory=factory, command_timeout=0.2, idle_timeout=None))


def start_process_for_test(process: PiProcess) -> None:
    process._ensure_started_locked()  # type: ignore[attr-defined]
    process._startup_ready_generation = process._process_generation  # type: ignore[attr-defined]


def test_process_starts_lazily_runs_startup_probe_and_routes_response() -> None:
    children: list[FakeChildProcess] = []

    def factory(*args: Any, **kwargs: Any) -> FakeChildProcess:
        child = FakeChildProcess()

        def on_command(payload: dict[str, Any]) -> None:
            if payload["type"] == "get_state":
                child.send_record(state_response(payload["id"], "startup-ready"))
                return
            child.send_record(success_response(payload["id"], payload["type"]))

        child.on_command = on_command
        children.append(child)
        return child

    process = PiProcess(PiClientOptions(process_factory=factory, command_timeout=0.2))
    assert children == []

    response = process.send_command(make_command("prompt", message="hello"))

    assert len(children) == 1
    assert [command["type"] for command in children[0].commands] == ["get_state", "prompt"]
    assert response.command == "prompt"


def test_cold_start_times_out_when_startup_probe_never_completes() -> None:
    children: list[FakeChildProcess] = []

    def factory(*args: Any, **kwargs: Any) -> FakeChildProcess:
        child = FakeChildProcess()
        children.append(child)
        return child

    process = PiProcess(PiClientOptions(process_factory=factory, startup_timeout=0.01, command_timeout=0.2, idle_timeout=None))

    with pytest.raises(PiStartupError, match="startup readiness"):
        process.send_command(make_command("get_state"))

    assert len(children) == 1
    assert [command["type"] for command in children[0].commands] == ["get_state"]


def test_cold_start_timeout_terminates_spawned_child() -> None:
    children: list[FakeChildProcess] = []

    def factory(*args: Any, **kwargs: Any) -> FakeChildProcess:
        child = FakeChildProcess()
        children.append(child)
        return child

    process = PiProcess(PiClientOptions(process_factory=factory, startup_timeout=0.01, command_timeout=0.2, idle_timeout=None))

    with pytest.raises(PiStartupError, match="startup readiness"):
        process.send_command(make_command("get_state"))

    child = children[0]
    assert child.poll() is not None
    assert child.terminate_calls + child.kill_calls >= 1
    assert child.wait_calls >= 1


def test_cold_start_uses_command_timeout_after_startup_probe_succeeds() -> None:
    children: list[FakeChildProcess] = []

    def factory(*args: Any, **kwargs: Any) -> FakeChildProcess:
        child = FakeChildProcess()
        command_count = 0

        def on_command(payload: dict[str, Any]) -> None:
            nonlocal command_count
            command_count += 1
            if command_count == 1:
                threading.Timer(0.005, lambda: child.send_record(state_response(payload["id"], "ready"))).start()

        child.on_command = on_command
        children.append(child)
        return child

    process = PiProcess(PiClientOptions(process_factory=factory, startup_timeout=0.05, command_timeout=0.01, idle_timeout=None))

    with pytest.raises(PiTimeoutError, match="get_state"):
        process.send_command(make_command("get_state"))

    assert len(children) == 1
    assert [command["type"] for command in children[0].commands] == ["get_state", "get_state"]


def test_concurrent_cold_start_waits_for_shared_startup_probe() -> None:
    children: list[FakeChildProcess] = []
    probe_seen = threading.Event()
    responses: list[str] = []
    errors: list[BaseException] = []
    startup_probe_id: str | None = None

    def factory(*args: Any, **kwargs: Any) -> FakeChildProcess:
        child = FakeChildProcess()

        def on_command(payload: dict[str, Any]) -> None:
            nonlocal startup_probe_id
            if startup_probe_id is None:
                startup_probe_id = payload["id"]
                probe_seen.set()
                return
            child.send_record(state_response(payload["id"], payload["id"]))

        child.on_command = on_command
        children.append(child)
        return child

    process = PiProcess(PiClientOptions(process_factory=factory, startup_timeout=0.2, command_timeout=0.2, idle_timeout=None))

    def send() -> None:
        try:
            response = process.send_command(make_command("get_state"))
            responses.append(response.data.session_id)
        except BaseException as exc:  # pragma: no cover - exercised only on failure paths
            errors.append(exc)

    first = threading.Thread(target=send)
    second = threading.Thread(target=send)
    first.start()
    assert probe_seen.wait(timeout=0.2)
    second.start()

    time.sleep(0.05)
    assert len(children) == 1
    assert [command["type"] for command in children[0].commands] == ["get_state"]

    assert startup_probe_id is not None
    children[0].send_record(state_response(startup_probe_id, "ready"))

    first.join(timeout=0.2)
    second.join(timeout=0.2)

    assert errors == []
    assert len(responses) == 2
    assert [command["type"] for command in children[0].commands] == ["get_state", "get_state", "get_state"]


def test_process_fans_out_events_and_tracks_active_workflow() -> None:
    children: list[FakeChildProcess] = []
    process = make_process(children)
    subscription = process.subscribe_events(maxsize=10)

    def on_command(payload: dict[str, Any]) -> None:
        child = children[0]
        child.send_record(success_response(payload["id"], payload["type"]))
        child.send_record({"type": "agent_start"})
        child.send_record({"type": "agent_end", "messages": []})

    start_process_for_test(process)
    children[0].on_command = on_command
    process.send_command(make_command("prompt", message="hi"))
    first = subscription.get(timeout=0.2)
    second = subscription.get(timeout=0.2)
    assert isinstance(first, AgentStartEvent)
    assert second.type == "agent_end"
    assert process.active_workflow is False


def test_process_publishes_extension_ui_request_events_without_killing_stream() -> None:
    children: list[FakeChildProcess] = []
    process = make_process(children)
    subscription = process.subscribe_events(maxsize=10)

    start_process_for_test(process)
    children[0].send_record({"type": "extension_ui_request", "id": "ui-1", "method": "notify", "message": "Heads up"})

    event = subscription.get(timeout=0.2)
    assert isinstance(event, ExtensionUiRequestEvent)
    assert isinstance(event.request, NotifyExtensionUiRequest)
    assert event.request.message == "Heads up"

    children[0].on_command = lambda payload: children[0].send_record(state_response(payload["id"], "after-ui"))
    response = process.send_command(make_command("get_state"))
    assert response.data.session_id == "after-ui"


def test_process_extension_ui_response_helpers_write_raw_jsonl_records() -> None:
    children: list[FakeChildProcess] = []
    process = make_process(children)

    start_process_for_test(process)

    process.respond_extension_ui_value("ui-1", "Allow")
    process.respond_extension_ui_confirmed("ui-2")
    process.respond_extension_ui_confirmed("ui-3", confirmed=False)
    process.respond_extension_ui_cancelled("ui-4")

    assert children[0].commands == [
        {"type": "extension_ui_response", "id": "ui-1", "value": "Allow"},
        {"type": "extension_ui_response", "id": "ui-2", "confirmed": True},
        {"type": "extension_ui_response", "id": "ui-3", "confirmed": False},
        {"type": "extension_ui_response", "id": "ui-4", "cancelled": True},
    ]
    assert process.active_workflow is False


def test_process_publishes_dialog_extension_ui_requests() -> None:
    children: list[FakeChildProcess] = []
    process = make_process(children)
    subscription = process.subscribe_events(maxsize=10)

    start_process_for_test(process)
    children[0].send_record({"type": "extension_ui_request", "id": "ui-confirm", "method": "confirm", "title": "Clear session?", "message": "All messages will be lost."})

    event = subscription.get(timeout=0.2)
    assert isinstance(event, ExtensionUiRequestEvent)
    assert isinstance(event.request, ConfirmExtensionUiRequest)
    assert event.request.title == "Clear session?"
    assert event.request.message == "All messages will be lost."


def test_process_times_out_and_cleans_pending_request() -> None:
    children: list[FakeChildProcess] = []
    process = make_process(children)
    start_process_for_test(process)
    with pytest.raises(PiTimeoutError):
        process.send_command(make_command("get_state"), timeout=0.01)


def test_process_forwards_extra_args_into_spawned_argv() -> None:
    captured_argv: list[str] | None = None

    def factory(*args: Any, **kwargs: Any) -> FakeChildProcess:
        nonlocal captured_argv
        child = FakeChildProcess()
        captured_argv = args[0]
        child.on_command = lambda payload: child.send_record(state_response(payload["id"], "argv-test"))
        return child

    process = PiProcess(
        PiClientOptions(
            process_factory=factory,
            command_timeout=0.2,
            idle_timeout=None,
            extra_args=("-e", "/tmp/mock-provider.ts", "--log-level", "debug"),
        )
    )

    process.send_command(make_command("get_state"))

    assert captured_argv == ["pi", "--mode", "rpc", "-e", "/tmp/mock-provider.ts", "--log-level", "debug"]


def test_process_overlays_child_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PI_RPC_TEST_INHERITED", "base")
    captured_env: dict[str, str] = {}

    def factory(*args: Any, **kwargs: Any) -> FakeChildProcess:
        child = FakeChildProcess()
        env = kwargs["env"]
        assert isinstance(env, dict)
        captured_env.update(env)
        child.on_command = lambda payload: child.send_record(state_response(payload["id"], "env-test"))
        return child

    process = PiProcess(
        PiClientOptions(
            process_factory=factory,
            command_timeout=0.2,
            idle_timeout=None,
            env={"PI_RPC_TEST_INHERITED": "override", "PI_RPC_TEST_EXTRA": "extra"},
        )
    )

    process.send_command(make_command("get_state"))

    assert captured_env["PI_RPC_TEST_INHERITED"] == "override"
    assert captured_env["PI_RPC_TEST_EXTRA"] == "extra"
    assert captured_env["PATH"] == os.environ["PATH"]


def test_late_response_after_timeout_does_not_poison_client() -> None:
    children: list[FakeChildProcess] = []
    process = make_process(children)
    start_process_for_test(process)
    child = children[0]
    timed_out_request_id: str | None = None

    def on_command(payload: dict[str, Any]) -> None:
        nonlocal timed_out_request_id
        if timed_out_request_id is None:
            timed_out_request_id = payload["id"]
            return
        child.send_record(state_response(payload["id"], "second"))

    child.on_command = on_command

    with pytest.raises(PiTimeoutError):
        process.send_command(make_command("get_state"), timeout=0.01)

    assert timed_out_request_id is not None
    child.send_record(state_response(timed_out_request_id, "late"))
    time.sleep(0.05)

    response = process.send_command(make_command("get_state"))

    assert response.command == "get_state"
    assert response.data.session_id == "second"


def test_timed_out_prompt_exit_still_fails_event_subscriptions() -> None:
    children: list[FakeChildProcess] = []
    process = make_process(children)
    subscription = process.subscribe_events(maxsize=10)

    def on_command(payload: dict[str, Any]) -> None:
        child = children[0]
        child.send_record({"type": "agent_start"})

    start_process_for_test(process)
    children[0].on_command = on_command

    with pytest.raises(PiTimeoutError):
        process.send_command(make_command("prompt", message="hi"), timeout=0.01)

    assert subscription.get(timeout=0.2).type == "agent_start"
    children[0].exit(1)

    with pytest.raises(PiProcessExitedError):
        subscription.get(timeout=0.2)


def test_failed_idle_prompt_does_not_poison_idle_restart() -> None:
    children: list[FakeChildProcess] = []

    def factory(*args: Any, **kwargs: Any) -> FakeChildProcess:
        child = FakeChildProcess()
        index = len(children)

        def on_command(payload: dict[str, Any]) -> None:
            if payload["type"] == "get_state":
                session_id = f"probe-{index}" if len(child.commands) == 1 else "restarted"
                child.send_record(state_response(payload["id"], session_id))
                return
            if index == 0:
                child.send_record({"id": payload["id"], "type": "response", "command": payload["type"], "success": False, "error": "bad prompt"})
            else:
                child.send_record(success_response(payload["id"], payload["type"]))

        child.on_command = on_command
        children.append(child)
        return child

    process = PiProcess(PiClientOptions(process_factory=factory, command_timeout=0.2, idle_timeout=None))

    with pytest.raises(PiCommandError):
        process.send_command(make_command("prompt", message="hi"))

    assert process.active_workflow is False
    children[0].exit(1)
    time.sleep(0.05)

    response = process.send_command(make_command("get_state"))

    assert response.command == "get_state"
    assert response.data.session_id == "restarted"
    assert len(children) == 2


def test_process_restarts_after_idle_exit() -> None:
    children: list[FakeChildProcess] = []

    def factory(*args: Any, **kwargs: Any) -> FakeChildProcess:
        child = FakeChildProcess()
        index = len(children)
        session_id = "a" if index == 0 else "b"

        def on_command(payload: dict[str, Any]) -> None:
            child.send_record(state_response(payload["id"], session_id))
            if index == 0 and len(child.commands) >= 2:
                child.exit(0)

        child.on_command = on_command
        children.append(child)
        return child

    process = PiProcess(PiClientOptions(process_factory=factory, command_timeout=0.2, idle_timeout=None))
    first_response = process.send_command(make_command("get_state"))
    time.sleep(0.05)
    next_response = process.send_command(make_command("get_state"))

    assert first_response.command == "get_state"
    assert next_response.command == "get_state"
    assert first_response.data.session_id == "a"
    assert next_response.data.session_id == "b"
    assert len(children) == 2


def test_process_exit_during_active_workflow_fails_subscriptions() -> None:
    children: list[FakeChildProcess] = []
    process = make_process(children)
    subscription = process.subscribe_events(maxsize=10)

    def on_command(payload: dict[str, Any]) -> None:
        child = children[0]
        child.send_record(success_response(payload["id"], payload["type"]))
        child.send_record({"type": "agent_start"})
        child.exit(1)

    start_process_for_test(process)
    children[0].on_command = on_command
    process.send_command(make_command("prompt", message="hi"))
    assert subscription.get(timeout=0.2).type == "agent_start"
    with pytest.raises(PiProcessExitedError):
        subscription.get(timeout=0.2)
