from __future__ import annotations

from pathlib import Path

import pytest

from pi_rpc import PiClient

pytestmark = pytest.mark.integration


def test_bash_and_session_commands(pi_client: PiClient, tmp_path: Path) -> None:
    result = pi_client.bash("printf 'hello from pi-rpc-python'")
    assert "hello from pi-rpc-python" in result.output
    stats = pi_client.get_session_stats()
    assert stats.session_id
    exported = pi_client.export_html(output_path=str(tmp_path / "session.html"))
    assert Path(exported.path).exists()
