from __future__ import annotations

import pytest

from pi_rpc import PiClient
from tests.integration.conftest import MOCK_MODEL_ID, MOCK_PROVIDER_NAME, _wait_for_agent_end, _wait_for_event

pytestmark = pytest.mark.integration


@pytest.fixture
def mock_prompt_map() -> dict[str, object]:
    return {"Trigger compaction": "COMPACT"}


def test_model_and_queue_commands(mock_pi_client: PiClient) -> None:
    models = mock_pi_client.get_available_models()
    assert isinstance(models, list)
    assert any(model.provider == MOCK_PROVIDER_NAME and model.id == MOCK_MODEL_ID for model in models)
    mock_pi_client.set_steering_mode("one-at-a-time")
    mock_pi_client.set_follow_up_mode("one-at-a-time")


def test_compaction_and_auto_compaction_behaviors_are_exercised(mock_pi_client: PiClient) -> None:
    manual_result = mock_pi_client.compact()
    assert manual_result.summary
    assert manual_result.first_kept_entry_id

    mock_pi_client.set_auto_compaction(True)
    mock_pi_client.set_auto_retry(True)
    mock_pi_client.abort_retry()

    subscription = mock_pi_client.subscribe_events(maxsize=300)
    mock_pi_client.prompt("Trigger compaction")
    _wait_for_agent_end(subscription)
    compaction_start = _wait_for_event(subscription, "compaction_start")
    compaction_end = _wait_for_event(subscription, "compaction_end")

    assert compaction_start.type == "compaction_start"
    assert compaction_end.type == "compaction_end"
    assert compaction_end.result is not None
    assert compaction_end.result.summary
