from __future__ import annotations

import pytest

from pi_rpc import PiClient
from tests.integration.conftest import _prompt_and_get_text, mock_assistant_message, mock_context_key, mock_user_message

pytestmark = pytest.mark.integration


def test_prompt_streams_expected_canned_answer(mock_pi_client: PiClient) -> None:
    assert _prompt_and_get_text(mock_pi_client, "Reply with exactly: OK") == "OK"


@pytest.fixture
def mock_context_map() -> dict[str, str]:
    return {
        mock_context_key(
            mock_user_message("Respond with the word BRIDGE."),
            mock_assistant_message("BRIDGE"),
            mock_user_message("Repeat the previous assistant response exactly."),
        ): "BRIDGE"
    }


def test_multiple_prompts_return_matching_canned_answers(mock_pi_client: PiClient) -> None:
    assert _prompt_and_get_text(mock_pi_client, "Respond with the word BRIDGE.") == "BRIDGE"
    assert _prompt_and_get_text(mock_pi_client, "Repeat the previous assistant response exactly.") == "BRIDGE"
