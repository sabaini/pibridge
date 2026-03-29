from __future__ import annotations

import pytest

from pi_rpc import PiClient
from tests.integration.conftest import MOCK_MODEL_ID, MOCK_PROVIDER_NAME

pytestmark = pytest.mark.integration


def test_model_and_queue_commands(mock_pi_client: PiClient) -> None:
    models = mock_pi_client.get_available_models()
    assert isinstance(models, list)
    assert any(model.provider == MOCK_PROVIDER_NAME and model.id == MOCK_MODEL_ID for model in models)
    mock_pi_client.set_steering_mode("one-at-a-time")
    mock_pi_client.set_follow_up_mode("one-at-a-time")
