from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

import pytest

from pi_rpc.exceptions import PiProtocolError, PiSubscriptionOverflowError
from pi_rpc.subscriptions import EventSubscription, SubscriptionHub


def assert_blocking_get_raises(
    subscription: EventSubscription[Any],
    trigger: Callable[[], None],
    expected: type[BaseException],
) -> None:
    result: dict[str, BaseException] = {}

    def reader() -> None:
        try:
            subscription.get()
        except BaseException as exc:  # pragma: no branch - thread handoff
            result["error"] = exc

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    trigger()
    thread.join(timeout=0.2)

    assert not thread.is_alive(), "blocking get() did not wake up"
    assert isinstance(result.get("error"), expected)


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


def test_subscription_blocking_get_wakes_on_close() -> None:
    hub = SubscriptionHub[str]()
    sub = hub.subscribe(maxsize=1)

    assert_blocking_get_raises(sub, hub.close_all, PiProtocolError)


def test_subscription_blocking_get_wakes_on_failure() -> None:
    hub = SubscriptionHub[str]()
    sub = hub.subscribe(maxsize=1)

    assert_blocking_get_raises(sub, lambda: hub.fail_all(PiProtocolError("boom")), PiProtocolError)


def test_subscription_blocking_get_wakes_on_overflow_after_drain() -> None:
    hub = SubscriptionHub[str]()
    sub = hub.subscribe(maxsize=1)

    hub.publish("first")
    hub.publish("second")

    assert sub.get(timeout=0.1) == "first"
    assert_blocking_get_raises(sub, lambda: None, PiSubscriptionOverflowError)
