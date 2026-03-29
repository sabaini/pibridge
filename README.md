# pi-rpc-python

`pi-rpc-python` is a protocol-faithful Python wrapper for `pi --mode rpc`.

It starts Pi lazily, communicates over strict JSONL on stdin/stdout, exposes typed commands/responses/events, and supports queue-based event subscriptions.

## Features

- lazy subprocess startup; `PiClient()` does not spawn Pi
- one Python method per documented v1 RPC command
- strict LF-delimited JSONL framing
- typed parsing for models, messages, responses, and events
- multiple event subscribers via bounded per-subscriber queues
- idle-only subprocess restart when Pi dies between commands
- opt-in integration tests against a real `pi --mode rpc`

## Installation

```bash
python -m venv .venv
. .venv/bin/activate
uv pip install -e .[dev]
```

Or, with pip available:

```bash
pip install -e .[dev]
```

Example-only dependencies such as `pandas` and `streamlit` live in the `examples` extra, so core development does not require them. Install `.[dev,examples]` if you want to run the bundled examples.

## Quick start

```python
from pi_rpc import PiClient, PiClientOptions

options = PiClientOptions(provider="anthropic", model="claude-sonnet-4-20250514")

with PiClient(options) as client:
    events = client.subscribe_events(maxsize=500)
    client.prompt("Reply with exactly: hello")
    while True:
        event = events.get(timeout=30)
        print(event)
        if event.type == "agent_end":
            break
```

See `examples/` for more runnable samples, including the Streamlit dataset triage assistant in `examples/dataset_triage/`.

## API overview

### Construction and lifecycle

```python
from pi_rpc import PiClient, PiClientOptions

client = PiClient(
    PiClientOptions(
        executable="pi",
        provider="anthropic",
        model="claude-sonnet-4-20250514",
        no_session=False,
        session_dir=None,
        command_timeout=30,
        idle_timeout=300,
    )
)
```

Important lifecycle rules:

- importing the package does nothing
- constructing `PiClient()` does not start Pi
- the first command starts `pi --mode rpc`
- `PiClientOptions.env` overlays the current process environment instead of replacing it wholesale
- `close()` or context-manager exit shuts the subprocess down
- if Pi exits while idle, the next command starts a fresh subprocess
- if Pi exits during an active workflow, subscribers receive an error and the active run is not replayed

### Commands

The public client mirrors the documented RPC surface:

- `prompt()`, `steer()`, `follow_up()`, `abort()`
- `new_session()`, `switch_session()`, `fork()`
- `get_state()`, `get_messages()`, `get_session_stats()`
- `set_model()`, `cycle_model()`, `get_available_models()`
- `set_thinking_level()`, `cycle_thinking_level()`
- `set_steering_mode()`, `set_follow_up_mode()`
- `compact()`, `set_auto_compaction()`
- `set_auto_retry()`, `abort_retry()`
- `bash()`, `abort_bash()`
- `export_html()`, `get_fork_messages()`, `get_last_assistant_text()`, `set_session_name()`, `get_commands()`
- low-level `send_command()` when you need direct protocol access

### Event subscriptions

Pi RPC exposes one global process event stream. Because events are not request-scoped, a single `PiClient` supports only one active agent workflow at a time.

Subscribe with a bounded queue:

```python
subscription = client.subscribe_events(maxsize=1000)
event = subscription.get(timeout=5)
```

`subscription.get()` also wakes correctly in the default blocking mode: if the client closes, the stream fails, or the subscriber overflows, the blocked caller is released and sees the corresponding exception instead of hanging forever.

Overflow behavior is explicit:

- each subscriber has its own bounded queue
- if one subscriber falls behind, that subscription fails with `PiSubscriptionOverflowError`
- other subscribers continue unaffected

## Strict JSONL framing

RPC mode uses strict JSONL semantics:

- each record is one JSON object
- records are delimited by LF (`\n`) only
- an optional trailing `\r` is accepted on input
- embedded `U+2028` and `U+2029` inside JSON strings are valid and must not split records

`pi-rpc-python` uses a byte-oriented reader/writer instead of generic text line readers.

## Bash semantics

`bash()` executes immediately and returns a typed `BashResult`, but the output reaches the LLM only on the next `prompt()`.

```python
client.bash("ceph status")
client.bash("journalctl -u ceph-mon --no-pager | tail -100")
client.prompt("Analyze the failure using the collected command output")
```

The stored bash execution message does not emit its own event.

## Unsupported/deferred v1 features

v1 intentionally does **not** implement:

- extension UI request/response handling
- generic host capability callbacks

If Pi emits an `extension_ui_request`, the client raises `PiUnsupportedFeatureError` rather than silently dropping it.

## Running tests

### Unit tests

```bash
. .venv/bin/activate
pytest -m 'not integration'
ruff check .
mypy src
python -m build
```

Example tests that need `pandas` are skipped unless you also install `.[examples]`.

### Integration tests

Integration tests run a real `pi --mode rpc` subprocess.

By default, the suite loads a bundled test-only extension at `tests/integration/fixtures/mock_provider.ts` and switches to a canned-response mock model after startup, so external model credentials are **not** required.

Default requirements:

- `pi` on `PATH`

Run them with:

```bash
. .venv/bin/activate
pytest -m integration
```

Optional live-backend override:

- `PI_RPC_PROVIDER=<provider>`
- `PI_RPC_MODEL=<model>`

When those two variables are set, the generic `pi_client` fixture starts Pi against that real backend instead of the bundled mock path. The dedicated mock-backed assertions still use the canned-response fixture.

The mock provider can match either an exact last-user prompt or an exact trailing context sequence, which lets the suite assert multi-turn history and “bash output reaches the next prompt” behavior deterministically. If a test sends an unmapped prompt/context, the provider returns a clear `[pi-rpc-mock missing canned response] ...` sentinel so failures are obvious.

If the environment is not configured, the integration suite skips clearly.

## Examples

- `examples/basic_prompt.py`
- `examples/session_flow.py`
- `examples/bash_then_prompt.py`
- `examples/dataset_triage/` - Streamlit CSV/CSV.gz triage assistant with deterministic pandas profiling and Pi follow-ups (`just dataset-triage` bootstraps `.venv` and installs `.[examples]`)

## Current limits

- one active workflow per `PiClient`
- synchronous/threaded API only in v1
- no extension UI support in v1
- compatibility is enforced by tests, not by a protocol handshake
