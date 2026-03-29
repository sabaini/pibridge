from __future__ import annotations

import queue
import threading
import time
from collections import deque
from typing import Generic, TypeVar

from .exceptions import PiProtocolError, PiSubscriptionOverflowError

T = TypeVar("T")


class EventSubscription(Generic[T]):
    def __init__(self, maxsize: int = 1000) -> None:
        if maxsize <= 0:
            raise ValueError("maxsize must be positive")
        self._maxsize = maxsize
        self._items: deque[T] = deque()
        self._condition = threading.Condition()
        self._closed = False
        self._error: BaseException | None = None

    @property
    def closed(self) -> bool:
        with self._condition:
            return self._closed

    def publish(self, item: T) -> None:
        with self._condition:
            if self._closed or self._error is not None:
                return
            if len(self._items) >= self._maxsize:
                self._error = PiSubscriptionOverflowError("event subscription queue overflowed")
                self._closed = True
                self._condition.notify_all()
                return
            self._items.append(item)
            self._condition.notify()

    def fail(self, error: BaseException) -> None:
        with self._condition:
            if self._error is None:
                self._error = error
            self._closed = True
            self._condition.notify_all()

    def close(self) -> None:
        with self._condition:
            self._closed = True
            self._condition.notify_all()

    def get(self, timeout: float | None = None) -> T:
        if timeout is not None and timeout < 0:
            raise ValueError("'timeout' must be a non-negative number")
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._condition:
            while not self._items:
                if self._error is not None:
                    raise self._error
                if self._closed:
                    raise PiProtocolError("subscription is closed")
                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    raise queue.Empty
                self._condition.wait(timeout=remaining)
            return self._items.popleft()

    def drain(self) -> list[T]:
        with self._condition:
            items = list(self._items)
            self._items.clear()
            return items


class SubscriptionHub(Generic[T]):
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscriptions: list[EventSubscription[T]] = []

    def subscribe(self, maxsize: int = 1000) -> EventSubscription[T]:
        subscription = EventSubscription[T](maxsize=maxsize)
        with self._lock:
            self._subscriptions.append(subscription)
        return subscription

    def publish(self, item: T) -> None:
        with self._lock:
            subscriptions = list(self._subscriptions)
        survivors: list[EventSubscription[T]] = []
        for subscription in subscriptions:
            subscription.publish(item)
            if not subscription.closed:
                survivors.append(subscription)
        with self._lock:
            self._subscriptions = survivors

    def fail_all(self, error: BaseException) -> None:
        with self._lock:
            subscriptions = list(self._subscriptions)
            self._subscriptions.clear()
        for subscription in subscriptions:
            subscription.fail(error)

    def close_all(self) -> None:
        with self._lock:
            subscriptions = list(self._subscriptions)
            self._subscriptions.clear()
        for subscription in subscriptions:
            subscription.close()
