from __future__ import annotations

import queue

from pi_rpc import PiClient, PiClientOptions


def main() -> None:
    options = PiClientOptions(provider="anthropic", model="claude-sonnet-4-20250514")
    with PiClient(options) as client:
        events = client.subscribe_events(maxsize=200)
        client.prompt("Reply with exactly: hello")
        while True:
            try:
                event = events.get(timeout=60)
            except queue.Empty:
                raise TimeoutError("Timed out waiting for Pi events") from None
            print(event)
            if event.type == "agent_end":
                break


if __name__ == "__main__":
    main()
