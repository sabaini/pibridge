from __future__ import annotations

import pytest

from pi_rpc import PiClient

pytestmark = pytest.mark.integration


def test_client_starts_lazily_and_gets_state(pi_client: PiClient) -> None:
    state = pi_client.get_state()
    assert state.session_id


def test_get_commands_returns_list(pi_client: PiClient) -> None:
    commands = pi_client.get_commands()
    assert isinstance(commands, list)
