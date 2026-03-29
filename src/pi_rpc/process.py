from __future__ import annotations

import io
import json
import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .commands import RpcCommand, ensure_command_id, make_command, serialize_command
from .events import AgentEndEvent, AgentEvent, AgentStartEvent, parse_event
from .exceptions import (
    PiProcessExitedError,
    PiProtocolError,
    PiStartupError,
    PiTimeoutError,
    PiUnsupportedFeatureError,
)
from .jsonl import JsonlReader, serialize_json_line
from .models import PiClientOptions
from .responses import RpcResponse, parse_response
from .subscriptions import EventSubscription, SubscriptionHub


@dataclass
class _PendingRequest:
    command: RpcCommand
    ready: threading.Event = field(default_factory=threading.Event)
    response: RpcResponse[Any] | None = None
    error: BaseException | None = None


class PendingRequestRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pending: dict[str, _PendingRequest] = {}
        self._abandoned: set[str] = set()

    def add(self, command: RpcCommand) -> _PendingRequest:
        if command.id is None:
            raise ValueError("command.id must be set before registration")
        pending = _PendingRequest(command=command)
        with self._lock:
            self._pending[command.id] = pending
        return pending

    def fulfill(self, request_id: str, response: RpcResponse[Any]) -> str:
        with self._lock:
            if request_id in self._abandoned:
                self._abandoned.remove(request_id)
                return "abandoned"
            pending = self._pending.pop(request_id, None)
        if pending is None:
            return "missing"
        pending.response = response
        pending.ready.set()
        return "fulfilled"

    def fail(self, request_id: str, error: BaseException) -> bool:
        with self._lock:
            pending = self._pending.pop(request_id, None)
        if pending is None:
            return False
        pending.error = error
        pending.ready.set()
        return True

    def cancel(self, request_id: str) -> None:
        with self._lock:
            self._pending.pop(request_id, None)

    def abandon(self, request_id: str) -> None:
        with self._lock:
            pending = self._pending.pop(request_id, None)
            if pending is not None:
                self._abandoned.add(request_id)

    def fail_all(self, error: BaseException) -> None:
        with self._lock:
            items = list(self._pending.values())
            self._pending.clear()
        for pending in items:
            pending.error = error
            pending.ready.set()

    def clear_abandoned(self) -> None:
        with self._lock:
            self._abandoned.clear()


class PiProcess:
    def __init__(self, options: PiClientOptions) -> None:
        self._options = options
        self._lock = threading.RLock()
        self._process: subprocess.Popen[bytes] | Any | None = None
        self._stdout_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        self._stderr_buffer = io.StringIO()
        self._stderr_lock = threading.Lock()
        self._jsonl_reader = JsonlReader()
        self._pending = PendingRequestRegistry()
        self._subscriptions: SubscriptionHub[AgentEvent] = SubscriptionHub()
        self._closed = False
        self._active_workflow = False
        self._pending_workflow_start_id: str | None = None
        self._idle_timer: threading.Timer | None = None
        self._stream_failure: BaseException | None = None
        self._restartable_idle_failure = False
        self._process_generation = 0
        self._startup_pending: _PendingRequest | None = None
        self._startup_ready_generation = 0

    @property
    def active_workflow(self) -> bool:
        with self._lock:
            return self._has_active_workflow_locked()

    def _has_active_workflow_locked(self) -> bool:
        return self._active_workflow or self._pending_workflow_start_id is not None

    def subscribe_events(self, maxsize: int = 1000) -> EventSubscription[AgentEvent]:
        return self._subscriptions.subscribe(maxsize=maxsize)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._pending_workflow_start_id = None
            self._active_workflow = False
        self._cancel_idle_timer()
        self._stop_process(graceful=True)
        if self._options.auto_close_subscriptions:
            self._subscriptions.close_all()

    def send_command(self, command: RpcCommand, timeout: float | None = None) -> RpcResponse[Any]:
        if timeout is None:
            timeout = self._options.command_timeout
        while True:
            with self._lock:
                if self._closed:
                    raise PiProcessExitedError("Pi process client is closed")
                self._cancel_idle_timer()
                self._ensure_started_locked()
                startup_pending = self._startup_probe_for_current_process_locked()
                if startup_pending is None:
                    command = ensure_command_id(command)
                    pending_workflow_start = False
                    if command.type == "prompt" and not self._has_active_workflow_locked():
                        self._pending_workflow_start_id = command.id
                        pending_workflow_start = True
                    pending = self._pending.add(command)
                    try:
                        self._write_command_locked(command)
                    except BaseException:
                        if pending_workflow_start and self._pending_workflow_start_id == command.id:
                            self._pending_workflow_start_id = None
                        self._pending.cancel(command.id or "")
                        raise
                    break
            self._await_startup_probe(startup_pending)
        response = self._wait_for_pending_request(pending, timeout=timeout, timeout_error=PiTimeoutError(command.type, timeout, command.id))
        try:
            response.raise_for_error()
        except BaseException:
            if pending_workflow_start:
                with self._lock:
                    if self._pending_workflow_start_id == command.id:
                        self._pending_workflow_start_id = None
                        self._schedule_idle_timer_locked()
            raise
        with self._lock:
            self._schedule_idle_timer_locked()
        return response

    def _ensure_started_locked(self) -> bool:
        if self._process is not None and self._process.poll() is None:
            return False
        if self._stream_failure is not None:
            if self._restartable_idle_failure:
                self._stream_failure = None
                self._restartable_idle_failure = False
            else:
                raise self._stream_failure
        if self._process is not None and self._process.poll() is not None:
            self._process = None
        self._start_process_locked()
        return True

    def _startup_probe_for_current_process_locked(self) -> _PendingRequest | None:
        if self._process is None:
            raise PiProcessExitedError("Pi process is not running")
        if self._startup_ready_generation == self._process_generation:
            return None
        if self._startup_pending is None:
            self._startup_pending = self._send_startup_probe_locked()
        return self._startup_pending

    def _send_startup_probe_locked(self) -> _PendingRequest:
        command = ensure_command_id(make_command("get_state"))
        pending = self._pending.add(command)
        try:
            self._write_command_locked(command)
        except BaseException:
            self._pending.cancel(command.id or "")
            raise
        return pending

    def _await_startup_probe(self, pending: _PendingRequest) -> None:
        timeout = self._options.startup_timeout
        timeout_error = PiStartupError(f"Timed out waiting for Pi startup readiness after {timeout:.3f}s")
        try:
            response = self._wait_for_pending_request(pending, timeout=timeout, timeout_error=timeout_error)
            response.raise_for_error()
        except PiStartupError:
            with self._lock:
                if self._startup_pending is pending:
                    self._startup_pending = None
                    self._startup_ready_generation = 0
            self._stop_process(graceful=False)
            raise
        except BaseException as exc:
            with self._lock:
                if self._startup_pending is pending:
                    self._startup_pending = None
                    self._startup_ready_generation = 0
            self._stop_process(graceful=False)
            raise PiStartupError(f"Pi failed during startup readiness probe: {exc}") from exc
        with self._lock:
            if self._startup_pending is pending:
                self._startup_pending = None
                self._startup_ready_generation = self._process_generation

    def _wait_for_pending_request(self, pending: _PendingRequest, *, timeout: float, timeout_error: BaseException) -> RpcResponse[Any]:
        command_id = pending.command.id or ""
        if not pending.ready.wait(timeout):
            self._pending.abandon(command_id)
            raise timeout_error
        if pending.error is not None:
            raise pending.error
        assert pending.response is not None
        return pending.response

    def _build_argv(self) -> list[str]:
        argv = [self._options.executable, "--mode", "rpc"]
        if self._options.provider:
            argv.extend(["--provider", self._options.provider])
        if self._options.model:
            argv.extend(["--model", self._options.model])
        if self._options.no_session:
            argv.append("--no-session")
        if self._options.session_dir:
            argv.extend(["--session-dir", self._options.session_dir])
        argv.extend(self._options.extra_args)
        return argv

    def _start_process_locked(self) -> None:
        self._jsonl_reader = JsonlReader()
        self._stream_failure = None
        self._restartable_idle_failure = False
        self._pending_workflow_start_id = None
        self._startup_pending = None
        self._startup_ready_generation = 0
        self._pending.clear_abandoned()
        argv = self._build_argv()
        factory: Callable[..., Any] = self._options.process_factory or subprocess.Popen
        try:
            process = factory(
                argv,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self._options.cwd,
                env=self._options.build_env(),
                bufsize=0,
            )
        except FileNotFoundError as exc:
            raise PiStartupError(f"Failed to start pi executable: {self._options.executable}") from exc
        except OSError as exc:
            raise PiStartupError(f"Failed to start pi executable: {exc}") from exc
        self._process = process
        self._process_generation += 1
        generation = self._process_generation
        self._stdout_thread = threading.Thread(target=self._stdout_loop, args=(generation,), name="pi-rpc-stdout", daemon=True)
        self._stderr_thread = threading.Thread(target=self._stderr_loop, args=(generation,), name="pi-rpc-stderr", daemon=True)
        self._stdout_thread.start()
        self._stderr_thread.start()

    def _write_command_locked(self, command: RpcCommand) -> None:
        if self._process is None or self._process.stdin is None:
            raise PiProcessExitedError("Pi process stdin is unavailable")
        if self._process.poll() is not None:
            stderr = self._stderr_text()
            raise PiProcessExitedError("Pi process exited before command write", returncode=self._process.poll(), stderr=stderr)
        payload = serialize_command(command)
        try:
            self._process.stdin.write(serialize_json_line(payload))
            self._process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            error = PiProcessExitedError("Failed to write command to Pi process", returncode=self._process.poll(), stderr=self._stderr_text())
            self._handle_stream_failure(error, generation=self._process_generation)
            raise error from exc

    def _stdout_loop(self, generation: int) -> None:
        assert self._process is not None and self._process.stdout is not None
        stream = self._process.stdout
        try:
            while True:
                chunk = stream.read(4096)
                if not chunk:
                    break
                for line in self._jsonl_reader.feed(chunk):
                    self._handle_stdout_record(line, generation)
            self._jsonl_reader.finalize()
        except UnicodeDecodeError as exc:
            self._handle_stream_failure(PiProtocolError(f"Invalid UTF-8 on stdout: {exc}"), generation=generation)
            return
        except json.JSONDecodeError as exc:
            self._handle_stream_failure(PiProtocolError(f"Malformed JSON on stdout: {exc}"), generation=generation)
            return
        except (PiProtocolError, PiUnsupportedFeatureError) as exc:
            self._handle_stream_failure(exc, generation=generation)
            return
        except BaseException as exc:
            self._handle_stream_failure(PiProtocolError(f"Unexpected stdout reader failure: {exc}"), generation=generation)
            return
        error = PiProcessExitedError(
            "Pi process stdout closed",
            returncode=self._process.poll() if self._process is not None else None,
            stderr=self._stderr_text(),
        )
        self._handle_stream_failure(error, generation=generation)

    def _stderr_loop(self, generation: int) -> None:
        assert self._process is not None and self._process.stderr is not None
        stream = self._process.stderr
        while True:
            chunk = stream.read(4096)
            if not chunk:
                return
            with self._stderr_lock:
                self._stderr_buffer.write(chunk.decode("utf-8", errors="replace"))

    def _handle_stdout_record(self, line: str, generation: int) -> None:
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise PiProtocolError(f"Malformed JSON on stdout: {exc}") from exc
        if not isinstance(payload, dict):
            raise PiProtocolError("Expected JSON object records from stdout")
        record_type = payload.get("type")
        if record_type == "response":
            response = parse_response(payload)
            if response.request_id is None:
                raise PiProtocolError("Received response without an id")
            with self._lock:
                if generation == self._process_generation and response.request_id == self._pending_workflow_start_id and not response.success:
                    self._pending_workflow_start_id = None
                    self._schedule_idle_timer_locked()
            fulfillment = self._pending.fulfill(response.request_id, response)
            if fulfillment == "abandoned":
                return
            if fulfillment == "missing":
                raise PiProtocolError(f"Received response for unknown request id: {response.request_id}")
            return
        if record_type == "extension_ui_request":
            raise PiUnsupportedFeatureError("extension_ui_request is not supported by pi-rpc-python v1")
        event = parse_event(payload)
        with self._lock:
            if generation != self._process_generation:
                return
            if isinstance(event, AgentStartEvent):
                self._pending_workflow_start_id = None
                self._active_workflow = True
            elif isinstance(event, AgentEndEvent):
                self._pending_workflow_start_id = None
                self._active_workflow = False
                self._schedule_idle_timer_locked()
        self._subscriptions.publish(event)

    def _handle_stream_failure(self, error: BaseException, generation: int) -> None:
        with self._lock:
            if generation != self._process_generation:
                return
            if self._stream_failure is not None:
                return
            self._stream_failure = error
            active = self._has_active_workflow_locked()
            self._restartable_idle_failure = not active and isinstance(error, PiProcessExitedError)
            self._pending_workflow_start_id = None
            self._active_workflow = False
        self._pending.fail_all(error)
        if active:
            self._subscriptions.fail_all(error)
        self._stop_process(graceful=False)

    def _stop_process(self, graceful: bool) -> None:
        with self._lock:
            process = self._process
            self._process = None
            self._startup_pending = None
            self._startup_ready_generation = 0
        if process is None:
            return
        try:
            if process.stdin is not None:
                process.stdin.close()
        except OSError:
            pass
        try:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=1 if graceful else 0.2)
        except Exception:
            try:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=1)
            except Exception:
                pass
        finally:
            try:
                if process.stdout is not None:
                    process.stdout.close()
            except OSError:
                pass
            try:
                if process.stderr is not None:
                    process.stderr.close()
            except OSError:
                pass

    def _schedule_idle_timer_locked(self) -> None:
        self._cancel_idle_timer()
        timeout = self._options.idle_timeout
        if timeout is None or timeout <= 0 or self._has_active_workflow_locked() or self._closed or self._process is None:
            return
        self._idle_timer = threading.Timer(timeout, self._handle_idle_timeout)
        self._idle_timer.daemon = True
        self._idle_timer.start()

    def _cancel_idle_timer(self) -> None:
        timer = self._idle_timer
        self._idle_timer = None
        if timer is not None:
            timer.cancel()

    def _handle_idle_timeout(self) -> None:
        with self._lock:
            if self._closed or self._has_active_workflow_locked():
                return
        self._stop_process(graceful=True)

    def _stderr_text(self) -> str:
        with self._stderr_lock:
            return self._stderr_buffer.getvalue()
