from __future__ import annotations

import json
import subprocess
import threading
import time
from collections.abc import Callable
from typing import Any

import pytest

from pi_rpc.commands import make_command
from pi_rpc.events import AgentStartEvent
from pi_rpc.exceptions import PiProcessExitedError, PiTimeoutError
from pi_rpc.jsonl import JsonlReader, serialize_json_line
from pi_rpc.models import PiClientOptions
from pi_rpc.process import PiProcess


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
        self.exit(0)

    def kill(self) -> None:
        self.exit(-9)

    def wait(self, timeout: float | None = None) -> int:
        end = None if timeout is None else time.monotonic() + timeout
        while self._returncode is None:
            if end is not None and time.monotonic() > end:
                raise subprocess.TimeoutExpired("fake", timeout)
            time.sleep(0.01)
        return self._returncode


def make_process(children: list[FakeChildProcess]) -> PiProcess:
    def factory(*args: Any, **kwargs: Any) -> FakeChildProcess:
        child = FakeChildProcess()
        children.append(child)
        return child

    return PiProcess(PiClientOptions(process_factory=factory, command_timeout=0.2, idle_timeout=None))


def test_process_starts_lazily_and_routes_response() -> None:
    children: list[FakeChildProcess] = []

    def factory(*args: Any, **kwargs: Any) -> FakeChildProcess:
        child = FakeChildProcess()
        child.on_command = lambda payload: child.send_record({"id": payload["id"], "type": "response", "command": payload["type"], "success": True})
        children.append(child)
        return child

    process = PiProcess(PiClientOptions(process_factory=factory, command_timeout=0.2))
    assert children == []

    response = process.send_command(make_command("prompt", message="hello"))

    assert len(children) == 1
    assert children[0].commands[0]["type"] == "prompt"
    assert response.command == "prompt"


def test_process_fans_out_events_and_tracks_active_workflow() -> None:
    children: list[FakeChildProcess] = []
    process = make_process(children)
    subscription = process.subscribe_events(maxsize=10)

    def on_command(payload: dict[str, Any]) -> None:
        child = children[0]
        child.send_record({"id": payload["id"], "type": "response", "command": payload["type"], "success": True})
        child.send_record({"type": "agent_start"})
        child.send_record({"type": "agent_end", "messages": []})

    process._ensure_started_locked()  # type: ignore[attr-defined]
    children[0].on_command = on_command
    process.send_command(make_command("prompt", message="hi"))
    first = subscription.get(timeout=0.2)
    second = subscription.get(timeout=0.2)
    assert isinstance(first, AgentStartEvent)
    assert second.type == "agent_end"
    assert process.active_workflow is False


def test_process_times_out_and_cleans_pending_request() -> None:
    children: list[FakeChildProcess] = []
    process = make_process(children)
    process._ensure_started_locked()  # type: ignore[attr-defined]
    with pytest.raises(PiTimeoutError):
        process.send_command(make_command("get_state"), timeout=0.01)


def test_process_restarts_after_idle_exit() -> None:
    children: list[FakeChildProcess] = []

    def factory(*args: Any, **kwargs: Any) -> FakeChildProcess:
        child = FakeChildProcess()
        index = len(children)
        session_id = "a" if index == 0 else "b"

        def on_command(payload: dict[str, Any]) -> None:
            child.send_record(
                {
                    "id": payload["id"],
                    "type": "response",
                    "command": payload["type"],
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
            )
            if index == 0:
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
    assert len(children) == 2


def test_process_exit_during_active_workflow_fails_subscriptions() -> None:
    children: list[FakeChildProcess] = []
    process = make_process(children)
    subscription = process.subscribe_events(maxsize=10)

    def on_command(payload: dict[str, Any]) -> None:
        child = children[0]
        child.send_record({"id": payload["id"], "type": "response", "command": payload["type"], "success": True})
        child.send_record({"type": "agent_start"})
        child.exit(1)

    process._ensure_started_locked()  # type: ignore[attr-defined]
    children[0].on_command = on_command
    process.send_command(make_command("prompt", message="hi"))
    assert subscription.get(timeout=0.2).type == "agent_start"
    with pytest.raises(PiProcessExitedError):
        subscription.get(timeout=0.2)
