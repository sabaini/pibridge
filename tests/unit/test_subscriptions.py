from __future__ import annotations

import pytest

from pi_rpc.exceptions import PiProtocolError, PiSubscriptionOverflowError
from pi_rpc.subscriptions import SubscriptionHub


def test_subscription_hub_fans_out_events_in_order() -> None:
    hub = SubscriptionHub[str]()
    first = hub.subscribe(maxsize=10)
    second = hub.subscribe(maxsize=10)

    hub.publish("a")
    hub.publish("b")

    assert first.get(timeout=0.1) == "a"
    assert first.get(timeout=0.1) == "b"
    assert second.get(timeout=0.1) == "a"
    assert second.get(timeout=0.1) == "b"


def test_subscription_overflow_isolated_to_slow_consumer() -> None:
    hub = SubscriptionHub[str]()
    slow = hub.subscribe(maxsize=1)
    fast = hub.subscribe(maxsize=10)

    hub.publish("first")
    hub.publish("second")

    assert fast.get(timeout=0.1) == "first"
    assert fast.get(timeout=0.1) == "second"
    assert slow.get(timeout=0.1) == "first"
    with pytest.raises(PiSubscriptionOverflowError):
        slow.get(timeout=0.01)


def test_subscription_close_reports_closed_state() -> None:
    hub = SubscriptionHub[str]()
    sub = hub.subscribe(maxsize=1)
    hub.close_all()
    with pytest.raises(PiProtocolError):
        sub.get(timeout=0.01)
