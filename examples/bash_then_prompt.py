from __future__ import annotations

import queue

from pi_rpc import PiClient

try:
    from examples.runtime_config import DEFAULT_MODEL, DEFAULT_PROVIDER, build_example_client_options
except ImportError:  # pragma: no cover - supports `python examples/bash_then_prompt.py`
    from runtime_config import DEFAULT_MODEL, DEFAULT_PROVIDER, build_example_client_options


def main() -> None:
    options = build_example_client_options(provider=DEFAULT_PROVIDER, model=DEFAULT_MODEL)
    with PiClient(options) as client:
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
        print(f"[done/bash_then_prompt] {client.get_last_assistant_text()}")


if __name__ == "__main__":
    main()
