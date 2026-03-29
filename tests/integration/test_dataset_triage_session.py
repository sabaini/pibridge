from __future__ import annotations

import pytest

from pi_rpc import PiClient
from tests.example_support import load_dataset_triage_module
from tests.integration.conftest import mock_assistant_message, mock_context_key, mock_user_message

session_module = load_dataset_triage_module("pi_session")

pytestmark = pytest.mark.integration


@pytest.fixture
def mock_prompt_map() -> dict[str, str]:
    return {"Dataset summary": "Initial analysis"}


@pytest.fixture
def mock_context_map() -> dict[str, str]:
    return {
        mock_context_key(
            mock_user_message("Dataset summary"),
            mock_assistant_message("Initial analysis"),
            mock_user_message("Which column should I clean first?"),
        ): "Clean the email column first."
    }


def test_dataset_triage_session_reuses_context_and_resets_between_datasets(mock_pi_client: PiClient) -> None:
    session = session_module.DatasetTriageSession(client_factory=lambda _options: mock_pi_client)

    session.reset_for_dataset("customers.csv")
    initial = session.analyze_profile("Dataset summary")
    follow_up = session.ask_follow_up("Which column should I clean first?")
    first_state = mock_pi_client.get_state()

    session.reset_for_dataset("orders.csv")
    second_state = mock_pi_client.get_state()

    assert initial == "Initial analysis"
    assert follow_up == "Clean the email column first."
    assert first_state.session_name == "dataset-triage:customers.csv"
    assert second_state.session_name == "dataset-triage:orders.csv"
    assert first_state.session_id != second_state.session_id
