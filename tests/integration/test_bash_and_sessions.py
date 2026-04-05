from __future__ import annotations

import threading
from pathlib import Path

import pytest

from pi_rpc import PiClient
from tests.integration.conftest import _prompt_and_get_text, bash_execution_context_text, mock_context_key, mock_user_message

pytestmark = pytest.mark.integration


@pytest.fixture
def mock_context_map() -> dict[str, object]:
    return {
        mock_context_key(
            mock_user_message(
                bash_execution_context_text("printf 'hello from pi-rpc-python'", "hello from pi-rpc-python")
            ),
            mock_user_message("What output did the previous bash command produce? Reply with exactly that text."),
        ): "hello from pi-rpc-python",
        mock_context_key(
            mock_user_message(bash_execution_context_text("printf 'alpha'", "alpha")),
            mock_user_message(bash_execution_context_text("printf 'beta'", "beta")),
            mock_user_message("List the previous bash outputs in order, separated by commas."),
        ): "alpha,beta",
    }


@pytest.fixture
def mock_prompt_map() -> dict[str, object]:
    return {
        "Session one prompt": "ONE",
        "Session two prompt": "TWO",
    }


def test_bash_and_session_commands(mock_pi_client: PiClient, tmp_path: Path) -> None:
    result = mock_pi_client.bash("printf 'hello from pi-rpc-python'")
    assert "hello from pi-rpc-python" in result.output
    assert (
        _prompt_and_get_text(mock_pi_client, "What output did the previous bash command produce? Reply with exactly that text.")
        == "hello from pi-rpc-python"
    )
    stats = mock_pi_client.get_session_stats()
    assert stats.session_id
    exported = mock_pi_client.export_html(output_path=str(tmp_path / "session.html"))
    assert Path(exported.path).exists()


def test_abort_bash_returns_cancelled_result(mock_pi_client: PiClient) -> None:
    result_holder: dict[str, object] = {}

    def run_bash() -> None:
        result_holder["result"] = mock_pi_client.bash(
            "python -c 'import time; print(\"start\"); time.sleep(30)'",
            timeout=60,
        )

    thread = threading.Thread(target=run_bash)
    thread.start()

    mock_pi_client.abort_bash(timeout=10)
    thread.join(timeout=20)

    assert thread.is_alive() is False
    result = result_holder["result"]
    assert result.cancelled is True
    assert result.exit_code is None


def test_multiple_bash_results_accumulate_into_the_next_prompt(mock_pi_client: PiClient) -> None:
    first = mock_pi_client.bash("printf 'alpha'")
    second = mock_pi_client.bash("printf 'beta'")

    assert first.output == "alpha"
    assert second.output == "beta"
    assert _prompt_and_get_text(mock_pi_client, "List the previous bash outputs in order, separated by commas.") == "alpha,beta"



def test_switch_session_get_messages_and_fork_flows(mock_pi_client: PiClient) -> None:
    first_text = _prompt_and_get_text(mock_pi_client, "Session one prompt")
    first_session = mock_pi_client.get_session_stats().session_file
    first_session_id = mock_pi_client.get_state().session_id
    first_messages = mock_pi_client.get_messages()

    assert first_text == "ONE"
    assert [message.role for message in first_messages][-2:] == ["user", "assistant"]

    fork_messages = mock_pi_client.get_fork_messages()
    assert len(fork_messages) == 1
    assert fork_messages[0].text == "Session one prompt"

    mock_pi_client.new_session()
    second_text = _prompt_and_get_text(mock_pi_client, "Session two prompt")
    second_session_id = mock_pi_client.get_state().session_id

    assert second_text == "TWO"
    assert second_session_id != first_session_id

    switched = mock_pi_client.switch_session(first_session)
    switched_state = mock_pi_client.get_state()
    switched_messages = mock_pi_client.get_messages()

    assert switched.cancelled is False
    assert switched_state.session_id == first_session_id
    assert [message.role for message in switched_messages][-2:] == ["user", "assistant"]

    forked = mock_pi_client.fork(fork_messages[0].entry_id)
    forked_state = mock_pi_client.get_state()

    assert forked.cancelled is False
    assert forked.text == "Session one prompt"
    assert forked_state.session_id != first_session_id
    assert mock_pi_client.get_messages() == []
