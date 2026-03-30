# Design doc: `pi-rpc-python`

## 1. Summary

`pi-rpc-python` is a standalone Python binding for the existing Pi RPC protocol. It starts `pi --mode rpc` as a subprocess, communicates over stdin/stdout using strict JSONL, exposes a protocol-faithful Python API, and keeps the subprocess warm to amortize startup cost. Pi RPC is explicitly meant for embedding the coding agent in other applications, with commands sent on stdin, responses and events streamed on stdout, and optional command `id` values used for response correlation. ([GitHub][1])

This package is a **full protocol wrapper**, not a minimal prompt-only shim.

## 2. Goals

Primary goals:

* provide a complete Python wrapper over the documented Pi RPC command surface
* preserve protocol fidelity rather than inventing a Python-specific RPC layer
* lazily start and reuse a warm Pi subprocess
* expose typed command, response, and event objects
* support one active agent workflow per client
* support caller-selectable session persistence
* provide robust integration testing against upstream Pi RPC behavior

Secondary goals:

* provide Pythonic convenience where it does not obscure protocol semantics
* support event fan-out to multiple consumers via queue-based subscriptions
* support automatic restart when the subprocess dies while idle

## 3. Non-goals

This package will not:

* define a new protocol
* add generic host capability callbacks in v1
* emulate Pi's TUI or support TUI-only extension APIs such as `ctx.ui.custom()` in v1
* invent request-scoped event streams where the protocol provides only a global event stream
* hide protocol-specific semantics such as `bash` behavior
* replace Pi’s CLI or extension system

## 4. Upstream protocol as source of truth

The upstream Pi RPC document is authoritative. In particular:

* Pi starts in RPC mode via `pi --mode rpc [options]`
* commands are JSON objects sent to stdin, one per line
* responses are JSON objects with `type: "response"`
* events are streamed to stdout as JSON lines
* all commands support an optional `id` for correlating responses
* framing uses strict JSONL with LF as the delimiter, with optional trailing `\r` accepted on input after trimming
* generic line readers that split on Unicode separators are not compliant
* `prompt` returns immediately and agent work continues asynchronously through streamed events ([GitHub][1])

If this design conflicts with upstream Pi RPC, upstream wins.

## 5. Scope of v1

v1 is a **full protocol wrapper**.

That means the package should wrap the documented command surface, including prompting, state/session commands, model selection, thinking level, queue modes, compaction, retry controls, bash, export/session operations, and command discovery. The Pi RPC doc documents all of those as first-class commands. ([GitHub][1])

v1 includes the RPC-safe extension UI request/response sub-protocol from upstream `rpc.md`.

That means the package publishes typed `extension_ui_request` records through subscriptions and provides explicit helpers for sending matching `extension_ui_response` payloads. Supported UI methods are limited to the RPC-safe methods documented upstream:

* dialog methods: `select`, `confirm`, `input`, `editor`
* fire-and-forget methods: `notify`, `setStatus`, `setWidget`, `setTitle`, `set_editor_text`

Still deferred:

* arbitrary host-side capability callbacks
* TUI-only extension APIs such as `ctx.ui.custom()` and direct component hooks that do not cross the RPC boundary

## 6. Process model

`pi-rpc-python` will manage a local Pi subprocess started as:

```bash
pi --mode rpc [options]
```

Relevant documented startup options include `--provider`, `--model`, `--no-session`, and `--session-dir`. ([GitHub][1])

The Python wrapper may also accept host-side `cwd`/`env` options for subprocess launch, but `env` should behave as an overlay on top of the inherited environment rather than forcing callers to reconstruct `PATH`, auth variables, and other ambient process state manually.

Cold start should have its own honest deadline. In the shipped client that means `startup_timeout` bounds a lazy-start readiness probe (`get_state`) before the caller's actual first command is written; once that readiness probe succeeds, the normal per-command `command_timeout` budget still applies to the real command.

Lifecycle:

* import does nothing
* constructing `PiClient()` does not start Pi
* first real command lazily starts Pi
* Pi stays alive for reuse
* Pi is shut down on `close()`, context-manager exit, or idle timeout
* if Pi dies while idle, the next command transparently starts a fresh subprocess
* if Pi dies during an active workflow, that workflow fails

## 7. Concurrency model

One `PiClient` supports **one active agent workflow at a time**.

Rationale:

* responses can be correlated by `id`
* events do not carry request ids
* the protocol therefore exposes a global process event stream, not independent request streams ([GitHub][1])

Implications:

* one active prompting/streaming workflow per client
* multiple client instances are allowed
* each client owns its own subprocess in v1
* callers that need stricter cross-thread startup or command serialization should provide that outside the client

## 8. Session policy

Session behavior is **caller-selectable**.

The protocol is session-aware and exposes `--no-session`, `--session-dir`, `new_session`, `switch_session`, `fork`, `set_session_name`, `get_state`, and `get_session_stats`. ([GitHub][1])

So the client should allow:

* ephemeral mode
* persistent default mode
* custom session directory
* explicit session operations during runtime

The binding should not impose a single policy.

## 9. Public API shape

The public API should be **generic and protocol-faithful**.

Examples of first-class methods:

* `prompt(...)`
* `steer(...)`
* `follow_up(...)`
* `abort()`
* `new_session(...)`
* `get_state()`
* `get_messages()`
* `set_model(...)`
* `cycle_model()`
* `get_available_models()`
* `set_thinking_level(...)`
* `cycle_thinking_level()`
* `set_steering_mode(...)`
* `set_follow_up_mode(...)`
* `compact(...)`
* `set_auto_compaction(...)`
* `set_auto_retry(...)`
* `abort_retry()`
* `bash(...)`
* `abort_bash()`
* `get_session_stats()`
* `export_html(...)`
* `switch_session(...)`
* `fork(...)`
* `get_fork_messages()`
* `get_last_assistant_text()`
* `set_session_name(...)`
* `get_commands()`
* `respond_extension_ui_value(...)`
* `respond_extension_ui_confirmed(...)`
* `respond_extension_ui_cancelled(...)` ([GitHub][1])

A generic low-level `send_command()` may exist, but the primary API should mirror protocol commands directly.

Higher-level convenience workflows may be added later in a separate layer, but they are not the primary surface.

One important compatibility note from the current integration suite: `PiClient.continue_prompt()` should be the recommended ergonomic helper for immediate streamed follow-ups. It is additive, maps directly to `prompt(..., streaming_behavior="followUp")`, and leaves the protocol-faithful `follow_up()` and `steer()` methods intact for callers that intentionally want the lower-level RPC behavior. On the tested upstream build, raw `follow_up()` and `steer()` requests are accepted but remain queued in session state instead of reliably starting an immediate streamed turn on their own.

## 10. Transport and framing

Transport is a managed subprocess with stdin/stdout pipes.

Framing is strict JSONL:

* one JSON object per line
* split on `\n` only
* strip trailing `\r` if present
* do not use generic Unicode-aware line readers ([GitHub][1])

The package should implement its own small JSONL reader/writer to guarantee compliance.

## 11. Response and event routing

The reader thread owns stdout.

It parses each JSON line and classifies it into:

* response
* event
* protocol error

Responses are matched by command `id`.

Normal agent events are routed separately and are not request-scoped. In addition, `extension_ui_request` records are surfaced to subscribers as typed `ExtensionUiRequestEvent` values. Matching `extension_ui_response` records are written directly to stdin and intentionally bypass normal RPC command/response bookkeeping because they are part of a side protocol, not first-class RPC commands. ([GitHub][1])

## 12. Stream consumption model

Streaming uses **queue-based subscription**.

Design:

* one background reader thread owns stdout
* responses are handled separately by id
* events are fanned out into per-subscriber bounded queues
* queued items are typed event objects, not raw dicts
* overflow policy is explicit

The protocol defines a global ordered event stream including `agent_start`, `agent_end`, `turn_start`, `turn_end`, `message_start`, `message_update`, `message_end`, `tool_execution_*`, `auto_compaction_*`, `auto_retry_*`, and `extension_error`. `message_update` includes structured deltas such as `text_delta`, `thinking_delta`, and toolcall deltas. The wrapper also publishes typed `ExtensionUiRequestEvent` values for the RPC extension UI side protocol so hosts can answer dialogs and observe fire-and-forget UI updates from the same subscription interface. ([GitHub][1])

### Subscription API

A likely Python shape:

```python
subscription = client.subscribe_events(maxsize=1000)
event = subscription.get(timeout=5)
```

Each subscription has its own bounded queue, and `get(timeout=None)` must still wake promptly if the subscription is closed, fails, or overflows.

### Overflow policy

Overflow must be explicit.

Recommended v1 policy:

* per-subscriber bounded queues
* if a subscriber overflows, mark that subscription failed/closed with an overflow error
* other subscribers continue unaffected

That keeps slow consumers isolated.

## 13. Bash semantics

`bash()` is exposed as a **normal convenience**, but its semantics must be documented clearly.

The protocol says:

* `bash` executes immediately
* the response returns command output and status
* internally a `BashExecutionMessage` is stored
* that stored bash message does **not** emit its own event
* bash output reaches the LLM only on the **next** `prompt`
* multiple bash commands may accumulate before a prompt ([GitHub][1])

So the wrapper exposes `bash()` normally, but its docs must make the sequencing explicit.

Example:

```python
client.bash("ceph status")
client.bash("journalctl -u ceph-mon")
client.prompt("Analyze the failure based on the collected evidence")
```

## 14. Extension UI support and remaining deferrals

### Extension UI

Supported in v1 for the RPC-safe sub-protocol.

Host behavior is intentionally explicit:

* subscribe first, then wait for `ExtensionUiRequestEvent`
* reply to dialog methods with `respond_extension_ui_value(...)`, `respond_extension_ui_confirmed(...)`, or `respond_extension_ui_cancelled(...)`
* fire-and-forget methods may be rendered by the host or ignored safely
* the client does not emulate Pi's TUI; it only forwards typed requests and writes typed responses ([GitHub][1])

Out of scope even with extension UI support:

* `ctx.ui.custom()`
* direct TUI component hooks and other methods that require in-process terminal rendering

### Host capability callbacks

Deferred from v1.

The current documented RPC surface does not define a general mechanism for Pi to call arbitrary host-side Python functions for data retrieval or actions. v1 assumes the host gathers evidence and feeds it to Pi, rather than the other way around. ([GitHub][1])

## 15. Error semantics

Error handling has two layers.

### Raw protocol semantics

* `success: false` response → `PiCommandError`
* malformed JSON / invalid stream / transport junk → `PiProtocolError`
* subprocess exit / broken pipe → `PiProcessExitedError`
* timeout waiting for a response → `PiTimeoutError`
* if a caller times out locally and Pi later emits that response anyway, the late response should be discarded rather than treated as a fatal protocol error

The protocol itself models failed commands as normal response objects with `success: false`, and parse failures also come back as response objects. ([GitHub][1])

### Operation-level semantics

On top of that, the binding should distinguish:

* `PiStartupError` — could not spawn `pi --mode rpc`, or the cold-start readiness probe did not complete within `startup_timeout`
* command failure — Pi returned `success: false`
* stream failure — stdout stream died or became invalid during active work
* cancellation — user issued `abort`, `abort_retry`, or `abort_bash`
* session transition cancelled — `new_session`, `switch_session`, or `fork` returned success with `data.cancelled: true` ([GitHub][1])

### Cancellation semantics

Cancellation is modeled as a **result state**, not necessarily an exception.

That means result types for relevant operations should be able to represent `cancelled=True`.

## 16. Restart semantics

Restart policy:

* **auto-restart only when idle**
* if Pi dies between requests, the next command starts a fresh subprocess
* if Pi dies during an active workflow or stream, fail that operation

No automatic replay of interrupted active workflows.

This keeps behavior honest and avoids pretending a broken stream can be resumed safely.

## 17. Compatibility policy

There is no documented version-negotiation handshake in the Pi RPC doc. ([GitHub][1])

So compatibility will be enforced by **comprehensive integration testing** against supported upstream Pi versions or release windows.

Current repository policy:

* the required CI contract is the Ubuntu GitHub Actions install path in `.github/workflows/ci.yml`, which currently installs `pi` with `npm install -g @mariozechner/pi-coding-agent`
* the mock-backed integration suite is required in CI and may be made fail-fast with `PI_RPC_REQUIRE_INTEGRATION=1`
* an opt-in live smoke workflow runs `tests/integration/test_live_smoke.py` against one maintainer-configured real provider/model pair when secrets are available
* the additive `continue_prompt()` helper is part of the compatibility story because it encodes the currently verified immediate-follow-up behavior without removing the low-level RPC methods

See also `docs/compatibility-policy.md` and `docs/release-checklist.md`.

## 18. Proposed package layout

```text
pi-rpc-python/
  pyproject.toml
  src/
    pi_rpc/
      __init__.py
      client.py
      process.py
      jsonl.py
      protocol_types.py
      commands.py
      responses.py
      events.py
      subscriptions.py
      exceptions.py
      models.py
  tests/
```

Suggested roles:

* `client.py` — public `PiClient`
* `process.py` — subprocess lifecycle and restart logic
* `jsonl.py` — strict JSONL framing
* `protocol_types.py` — typed wire-level objects
* `commands.py` — command builders / serializers
* `responses.py` — response parsing and id correlation
* `events.py` — typed event parsing
* `subscriptions.py` — queue-based fan-out
* `exceptions.py` — error taxonomy
* `models.py` — higher-level typed result wrappers where useful

## 19. Testing strategy

### Unit tests

Cover:

* strict JSONL behavior
* response matching by id
* typed event parsing
* queue subscription behavior
* overflow handling
* timeout handling
* idle restart behavior
* active-stream failure behavior

### Integration tests

Use real Pi subprocesses to verify:

* startup via `pi --mode rpc`
* full command coverage
* prompt/steer/follow_up behavior during streaming
* state/session commands
* model/thinking/queue mode commands
* compaction/retry commands
* bash semantics, especially “reaches LLM on next prompt”
* cancellation behavior
* auto-restart when idle
* failure behavior during active streams ([GitHub][1])

Given your decision, integration coverage is a core deliverable, not a later polish item.

## 20. Milestones

### Milestone 1

* subprocess startup and shutdown
* strict JSONL reader/writer
* low-level `send_command()`
* response matching by id
* reader thread
* basic event parsing
* base exception taxonomy

### Milestone 2

* full protocol command wrappers
* typed responses
* typed events
* session-selectable startup/config
* queue-based subscriptions with bounded queues

### Milestone 3

* idle restart
* robust failure handling
* cancellation/result-state support
* complete integration coverage for supported Pi versions

### Milestone 4

* polish
* docs
* examples
* optional higher-level helpers as a separate layer



[1]: https://raw.githubusercontent.com/badlogic/pi-mono/c2a42e3215fdef1ac2d8eb0f714e82aed7189ed3/packages/coding-agent/docs/rpc.md "raw.githubusercontent.com"
