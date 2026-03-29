from __future__ import annotations

import queue

from pi_rpc import PiClient, PiClientOptions


def main() -> None:
    with PiClient(PiClientOptions(provider="anthropic", model="claude-sonnet-4-20250514")) as client:
        first = client.bash("pwd")
        second = client.bash("ls -1")
        print("bash 1 exit:", first.exit_code)
        print("bash 2 exit:", second.exit_code)

        events = client.subscribe_events(maxsize=200)
        client.prompt("Summarize what those commands showed.")
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
