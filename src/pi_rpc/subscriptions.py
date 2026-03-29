from __future__ import annotations

import queue
import threading
from typing import Generic, TypeVar

from .exceptions import PiProtocolError, PiSubscriptionOverflowError

T = TypeVar("T")


class EventSubscription(Generic[T]):
    def __init__(self, maxsize: int = 1000) -> None:
        if maxsize <= 0:
            raise ValueError("maxsize must be positive")
        self._queue: queue.Queue[T] = queue.Queue(maxsize=maxsize)
        self._lock = threading.Lock()
        self._closed = False
        self._error: BaseException | None = None

    @property
    def closed(self) -> bool:
        with self._lock:
            return self._closed

    def publish(self, item: T) -> None:
        with self._lock:
            if self._closed or self._error is not None:
                return
            try:
                self._queue.put_nowait(item)
            except queue.Full:
                self._error = PiSubscriptionOverflowError("event subscription queue overflowed")
                self._closed = True

    def fail(self, error: BaseException) -> None:
        with self._lock:
            if self._error is None:
                self._error = error
            self._closed = True

    def close(self) -> None:
        with self._lock:
            self._closed = True

    def get(self, timeout: float | None = None) -> T:
        try:
            item = self._queue.get(timeout=timeout)
        except queue.Empty as exc:
            error = self._error
            if error is not None:
                raise error from exc
            if self.closed:
                raise PiProtocolError("subscription is closed") from exc
            raise
        return item

    def drain(self) -> list[T]:
        items: list[T] = []
        while True:
            try:
                items.append(self._queue.get_nowait())
            except queue.Empty:
                break
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
