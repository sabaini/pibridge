from __future__ import annotations

import pytest

from pi_rpc import PiClient

pytestmark = pytest.mark.integration


def test_model_and_queue_commands(pi_client: PiClient) -> None:
    models = pi_client.get_available_models()
    assert isinstance(models, list)
    pi_client.set_steering_mode("one-at-a-time")
    pi_client.set_follow_up_mode("one-at-a-time")
