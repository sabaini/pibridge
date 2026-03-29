from __future__ import annotations

import pytest

from pi_rpc import PiClient
from tests.integration.conftest import _prompt_and_get_text

pytestmark = pytest.mark.integration


def test_prompt_streams_expected_canned_answer(mock_pi_client: PiClient) -> None:
    assert _prompt_and_get_text(mock_pi_client, "Reply with exactly: OK") == "OK"


def test_multiple_prompts_return_matching_canned_answers(mock_pi_client: PiClient) -> None:
    assert _prompt_and_get_text(mock_pi_client, "Respond with the word BRIDGE.") == "BRIDGE"
    assert _prompt_and_get_text(mock_pi_client, "Respond with the word TESTING.") == "TESTING"
