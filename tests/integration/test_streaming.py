from __future__ import annotations

import queue
import time

import pytest

from pi_rpc import PiClient

pytestmark = pytest.mark.integration


def test_prompt_streams_events(pi_client: PiClient) -> None:
    subscription = pi_client.subscribe_events(maxsize=200)
    pi_client.prompt("Reply with exactly: OK")

    seen_end = False
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        try:
            event = subscription.get(timeout=1)
        except queue.Empty:
            continue
        if event.type == "agent_end":
            seen_end = True
            break
    assert seen_end
