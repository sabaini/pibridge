from __future__ import annotations

import pytest

from pi_rpc import PiClient
from pi_rpc.commands import make_command

pytestmark = pytest.mark.integration


def test_client_starts_lazily_and_gets_state(pi_client: PiClient) -> None:
    state = pi_client.get_state()
    assert state.session_id


def test_send_command_supports_string_and_rpc_command_inputs(pi_client: PiClient) -> None:
    string_response = pi_client.send_command("get_state")
    rpc_response = pi_client.send_command(make_command("get_state"))

    assert string_response.command == "get_state"
    assert rpc_response.command == "get_state"
    assert string_response.data.session_id == rpc_response.data.session_id


def test_get_commands_returns_list(pi_client: PiClient) -> None:
    commands = pi_client.get_commands()
    assert isinstance(commands, list)


def test_get_commands_includes_loaded_extension_commands(mock_extension_ui_client: PiClient) -> None:
    commands = {command.name for command in mock_extension_ui_client.get_commands()}

    assert {"rpc-select", "rpc-input", "rpc-editor", "rpc-fire-and-forget"}.issubset(commands)
