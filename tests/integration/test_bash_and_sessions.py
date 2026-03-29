from __future__ import annotations

from pathlib import Path

import pytest

from pi_rpc import PiClient
from tests.integration.conftest import _prompt_and_get_text

pytestmark = pytest.mark.integration


def test_bash_and_session_commands(mock_pi_client: PiClient, tmp_path: Path) -> None:
    result = mock_pi_client.bash("printf 'hello from pi-rpc-python'")
    assert "hello from pi-rpc-python" in result.output
    assert _prompt_and_get_text(mock_pi_client, "Reply with exactly: OK") == "OK"
    stats = mock_pi_client.get_session_stats()
    assert stats.session_id
    exported = mock_pi_client.export_html(output_path=str(tmp_path / "session.html"))
    assert Path(exported.path).exists()
