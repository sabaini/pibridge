from __future__ import annotations

import time
from typing import Any

import pytest

from pi_rpc.commands import make_command
from pi_rpc.exceptions import PiProcessExitedError, PiProtocolError
from pi_rpc.models import PiClientOptions
from pi_rpc.process import PiProcess
from tests.unit.test_process import FakeChildProcess


@pytest.fixture
def child_factory() -> tuple[list[FakeChildProcess], PiProcess]:
    children: list[FakeChildProcess] = []

    def factory(*args: Any, **kwargs: Any) -> FakeChildProcess:
        child = FakeChildProcess()
        children.append(child)
        return child

    process = PiProcess(PiClientOptions(process_factory=factory, command_timeout=0.2))
    return children, process


def test_malformed_stdout_raises_protocol_error(child_factory: tuple[list[FakeChildProcess], PiProcess]) -> None:
    children, process = child_factory
    process._ensure_started_locked()  # type: ignore[attr-defined]
    children[0].stdout.push(b"not-json\n")
    time.sleep(0.05)
    with pytest.raises(PiProtocolError):
        process.send_command(make_command("get_state"))


def test_unknown_record_type_raises_protocol_error(child_factory: tuple[list[FakeChildProcess], PiProcess]) -> None:
    children, process = child_factory
    process._ensure_started_locked()  # type: ignore[attr-defined]
    children[0].stdout.push(b'{"type":"mystery"}\n')
    time.sleep(0.05)
    with pytest.raises(PiProtocolError):
        process.send_command(make_command("get_state"))


def test_malformed_extension_ui_request_surfaces_protocol_error(child_factory: tuple[list[FakeChildProcess], PiProcess]) -> None:
    children, process = child_factory
    process._ensure_started_locked()  # type: ignore[attr-defined]
    children[0].stdout.push(b'{"type":"extension_ui_request","id":"1","method":"select","title":"Choose","options":["Allow",1]}\n')
    time.sleep(0.05)
    with pytest.raises(PiProtocolError, match="options"):
        process.send_command(make_command("get_state"))


def test_extension_ui_response_helper_rejects_closed_process() -> None:
    child = FakeChildProcess()

    def factory(*args: Any, **kwargs: Any) -> FakeChildProcess:
        return child

    process = PiProcess(PiClientOptions(process_factory=factory, command_timeout=0.2))
    process.close()

    with pytest.raises(PiProcessExitedError, match="closed"):
        process.respond_extension_ui_cancelled("ui-1")


def test_extension_ui_response_helper_rejects_missing_process(child_factory: tuple[list[FakeChildProcess], PiProcess]) -> None:
    _children, process = child_factory
    with pytest.raises(PiProcessExitedError, match="not running"):
        process.respond_extension_ui_value("ui-2", "Allow")


def test_broken_stdin_write_maps_to_process_exit() -> None:
    child = FakeChildProcess()
    child.stdin.close()

    def factory(*args: Any, **kwargs: Any) -> FakeChildProcess:
        return child

    process = PiProcess(PiClientOptions(process_factory=factory, command_timeout=0.2))
    with pytest.raises(PiProcessExitedError):
        process.send_command(make_command("get_state"))
