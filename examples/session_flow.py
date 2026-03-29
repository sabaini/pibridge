from __future__ import annotations

from pi_rpc import PiClient, PiClientOptions


def main() -> None:
    with PiClient(PiClientOptions(provider="anthropic", model="claude-sonnet-4-20250514")) as client:
        state = client.get_state()
        print("Current session:", state.session_id)

        transition = client.new_session()
        print("New session cancelled:", transition.cancelled)

        client.set_session_name("pi-rpc-python-demo")
        updated = client.get_state()
        print("Updated session name:", updated.session_name)

        commands = client.get_commands()
        print("Available slash commands:", len(commands))


if __name__ == "__main__":
    main()
