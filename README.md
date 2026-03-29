# pi-rpc-python

`pi-rpc-python` is a protocol-faithful Python wrapper for `pi --mode rpc`.

It starts Pi lazily, communicates over strict JSONL on stdin/stdout, exposes typed commands/responses/events, and supports bounded, queue-like event subscriptions.

## Features

- lazy subprocess startup; `PiClient()` does not spawn Pi
- one Python method per documented v1 RPC command
- strict LF-delimited JSONL framing
- typed parsing for models, messages, responses, and events
- multiple event subscribers via bounded per-subscriber queues
- idle-only subprocess restart when Pi dies between commands
- integration tests against a real `pi --mode rpc` subprocess, with a bundled mock backend by default

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
        cwd=None,
        env=None,
        startup_timeout=10,
        command_timeout=30,
        idle_timeout=300,
        extra_args=(),
        auto_close_subscriptions=True,
    )
)

# equivalent shorthand:
client = PiClient(provider="anthropic", model="claude-sonnet-4-20250514")
```

Important lifecycle rules:

- importing the package does nothing
- constructing `PiClient()` does not start Pi
- the first command starts `pi --mode rpc`
- `startup_timeout` bounds the lazy cold-start readiness probe; on a cold process the client first waits for an internal `get_state` response before sending your real command
- `PiClientOptions.env` overlays the current process environment instead of replacing it wholesale
- `PiClientOptions.extra_args` is appended to the spawned `pi --mode rpc` argv
- after a cold start is ready, the user command still gets its normal `command_timeout` budget
- `close()` or context-manager exit shuts the subprocess down
- if `idle_timeout` is set and expires, the idle subprocess is stopped; the next command starts a fresh subprocess
- if Pi exits while idle, the next command starts a fresh subprocess
- if Pi exits during an active workflow, subscribers receive an error and the active run is not replayed
- `auto_close_subscriptions=True` closes all subscriptions when the client closes

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

Notable argument details from the current client:

- `prompt()`, `steer()`, and `follow_up()` accept optional image content blocks (see `pi_rpc.protocol_types.ImageContent`)
- `prompt()` also accepts `streaming_behavior="steer" | "followUp"`
- in the current verified compatibility suite, `prompt(..., streaming_behavior="followUp")` is the reliable way to stream a follow-up turn immediately; raw `follow_up()` and `steer()` currently queue pending work in session state instead of starting a fresh streamed turn on their own
- every high-level command accepts an optional per-call `timeout=` override
- `send_command()` accepts either an explicit `pi_rpc.commands.RpcCommand` or a raw command name plus fields

### Event subscriptions

Pi RPC exposes one global process event stream. Because events are not request-scoped, a single `PiClient` supports only one active agent workflow at a time.

`subscribe_events()` returns an `EventSubscription`: a bounded, queue-like object with `get()`, `drain()`, and `close()`.

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

v1 intentionally does **not** implement extension UI request/response handling.

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

By default, the suite loads a bundled test-only extension at `tests/integration/fixtures/mock_provider.ts` and selects a canned-response mock model after startup, so external model credentials are **not** required.

Default requirements:

- `pi` on `PATH`
- the bundled mock extension fixture present in `tests/integration/fixtures/`

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

If `pi` is not installed or the bundled mock fixture is missing, the integration suite skips clearly.

## Examples

- `examples/basic_prompt.py`
- `examples/session_flow.py`
- `examples/bash_then_prompt.py`
- `examples/dataset_triage/` - Streamlit CSV/CSV.gz triage assistant with deterministic pandas profiling, sensitive-value redaction, and Pi follow-ups via `prompt(..., streaming_behavior="followUp")` (`just dataset-triage` bootstraps `.venv` and installs `.[examples]`)

## Current limits

- one active workflow per `PiClient`
- synchronous/threaded API only in v1
- no extension UI support in v1
- compatibility is enforced by tests, not by a protocol handshake
- some upstream commands still have behavior quirks; the public docs describe the runtime behavior exercised by the deterministic integration suite rather than assuming every documented RPC command streams identically
