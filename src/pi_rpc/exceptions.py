from __future__ import annotations

from dataclasses import dataclass


class PiError(Exception):
    """Base exception for pi-rpc-python."""


@dataclass(eq=False)
class PiCommandError(PiError):
    command: str
    message: str
    request_id: str | None = None

    def __str__(self) -> str:
        prefix = f"[{self.command}] " if self.command else ""
        request = f" (id={self.request_id})" if self.request_id else ""
        return f"{prefix}{self.message}{request}"


@dataclass(eq=False)
class PiProtocolError(PiError):
    message: str

    def __str__(self) -> str:
        return self.message


@dataclass(eq=False)
class PiProcessExitedError(PiError):
    message: str
    returncode: int | None = None
    stderr: str | None = None

    def __str__(self) -> str:
        details = self.message
        if self.returncode is not None:
            details += f" (returncode={self.returncode})"
        if self.stderr:
            details += f" stderr={self.stderr.strip()}"
        return details


@dataclass(eq=False)
class PiStartupError(PiError):
    message: str

    def __str__(self) -> str:
        return self.message


@dataclass(eq=False)
class PiTimeoutError(PiError):
    command: str
    timeout: float
    request_id: str | None = None

    def __str__(self) -> str:
        request = f" (id={self.request_id})" if self.request_id else ""
        return f"Timed out waiting for '{self.command}' after {self.timeout:.3f}s{request}"


@dataclass(eq=False)
class PiSubscriptionOverflowError(PiError):
    message: str

    def __str__(self) -> str:
        return self.message


@dataclass(eq=False)
class PiUnsupportedFeatureError(PiError):
    message: str

    def __str__(self) -> str:
        return self.message
