from __future__ import annotations

from pathlib import Path

import pytest

from pi_rpc import PiClient
from tests.integration.conftest import _prompt_and_get_text, bash_execution_context_text, mock_context_key, mock_user_message

pytestmark = pytest.mark.integration


@pytest.fixture
def mock_context_map() -> dict[str, str]:
    return {
        mock_context_key(
            mock_user_message(
                bash_execution_context_text("printf 'hello from pi-rpc-python'", "hello from pi-rpc-python")
            ),
            mock_user_message("What output did the previous bash command produce? Reply with exactly that text."),
        ): "hello from pi-rpc-python"
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
