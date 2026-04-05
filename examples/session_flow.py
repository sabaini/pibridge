from __future__ import annotations

from pi_rpc import PiClient

try:
    from examples.runtime_config import DEFAULT_MODEL, DEFAULT_PROVIDER, build_example_client_options
except ImportError:  # pragma: no cover - supports `python examples/session_flow.py`
    from runtime_config import DEFAULT_MODEL, DEFAULT_PROVIDER, build_example_client_options


def main() -> None:
    options = build_example_client_options(provider=DEFAULT_PROVIDER, model=DEFAULT_MODEL)
    with PiClient(options) as client:
        state = client.get_state()
        print("Current session:", state.session_id)

        transition = client.new_session()
        print("New session cancelled:", transition.cancelled)

        client.set_session_name("pi-rpc-python-demo")
        updated = client.get_state()
        print("Updated session name:", updated.session_name)

        commands = client.get_commands()
        print("Available slash commands:", len(commands))
        print("[done/session_flow]")


if __name__ == "__main__":
    main()
