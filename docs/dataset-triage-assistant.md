# Design doc: Dataset Triage Assistant

## 1. Summary

Dataset Triage Assistant is a small local Python application that helps a user inspect a CSV dataset, identify obvious quality issues, and ask follow-up questions in natural language.

The app uses:

- `pandas` for deterministic dataset inspection and profiling
- `pi-rpc-python` ("pibridge" in this document) for conversational analysis and streamed explanations
- `streamlit` for a lightweight local UI

The core design principle is:

- Python computes facts
- Pi explains, prioritizes, and suggests next steps

This makes the example meaningfully more capable than a hello world app while remaining small, readable, and aligned with Python’s strengths.

---

## 2. Goals

Primary goals:

- demonstrate a realistic pibridge application pattern
- showcase Python library integration, especially `pandas`
- keep the codebase small enough to serve as reference/example code
- support interactive follow-up questions in a persistent Pi session
- stream Pi output back to the UI for responsiveness

Secondary goals:

- produce actionable suggestions such as cleaning recommendations and example pandas code
- make the app easy to run locally with minimal setup
- leave room for future enhancements like charts and export

---

## 3. Non-goals

The MVP will not:

- mutate the uploaded dataset automatically
- support multi-file joins or relational modeling
- support Excel, Parquet, or database ingestion
- run heavy ML pipelines or advanced anomaly detection
- provide user accounts, auth, or collaborative features
- handle very large datasets beyond what comfortably fits in local memory

---

## 4. User problem

Users often receive a CSV and need fast answers to questions such as:

- What is in this dataset?
- Which columns look problematic?
- Are there missing values, duplicates, or suspicious categories?
- What should be cleaned first?
- What pandas code would fix the biggest issues?

Today, that usually requires writing ad hoc exploratory code or manually inspecting the file. The app shortens that loop by combining deterministic profiling with conversational interpretation.

---

## 5. Target user

Primary target user:

- a Python-friendly analyst, engineer, or student who wants fast first-pass insight into a CSV

Likely users:

- data analysts doing initial dataset triage
- engineers validating exports or operational reports
- students learning exploratory data analysis
- technically assisted business users

---

## 6. User experience

### Happy path

1. User opens the Streamlit app.
2. User uploads a CSV file.
3. The app parses the file into a pandas DataFrame.
4. The app shows a preview and a compact profile.
5. User clicks **Analyze with Pi**.
6. The app starts a fresh Pi session for this dataset and sends a structured prompt containing the computed profile.
7. Pi streams back:
   - a concise summary of the dataset
   - likely data quality issues
   - recommended cleanup priorities
   - optional suggested pandas code
8. User asks follow-up questions in the same session.
9. The app renders the conversation history and latest streamed response.

### Example follow-up questions

- Which three columns should I clean first?
- What is suspicious about the date fields?
- Write pandas code to normalize the country column.
- Summarize these findings for a non-technical stakeholder.

---

## 7. Product requirements

### 7.1 Functional requirements

The system shall:

- accept a local CSV upload
- parse it with pandas and surface parse failures clearly
- display a DataFrame preview
- compute a compact deterministic profile
- create a Pi session and stream an initial analysis response
- preserve conversation context for follow-up prompts
- display the latest Pi response and basic conversation history

### 7.2 Non-functional requirements

The system should:

- run locally with minimal setup
- remain small and readable as example code
- avoid sending raw full datasets when a summary is sufficient
- be responsive via streamed output
- fail clearly when CSV parsing or Pi communication fails

---

## 8. High-level architecture

The app is split into five layers:

1. **UI layer**
   - Streamlit components for file upload, preview, analysis trigger, and follow-up input
2. **Data loading layer**
   - CSV parsing and input validation
3. **Profiling layer**
   - deterministic dataset summary and heuristics with pandas
4. **Prompting/session layer**
   - prompt construction, Pi client lifecycle, event subscription, and session handling
5. **Presentation layer**
   - formatting profile output and streamed Pi responses for the UI

### Component diagram

```text
[Streamlit UI]
     |
     v
[CSV Loader] --> [DataFrame]
     |
     v
[Profiler] --> [Profile Summary]
     |
     v
[Prompt Builder] --> [PiClient / session / event subscription]
     |
     v
[Streamed Pi analysis + follow-ups]
     |
     v
[Rendered output in UI]
```

---

## 9. Core design decisions

### 9.1 Deterministic facts stay in Python

All measurable dataset facts come from Python, not the model. That includes:

- row/column counts
- dtypes
- missing value counts and percentages
- duplicate counts
- numeric summary statistics
- top categorical values
- simple heuristics such as high-cardinality or null-heavy columns

Pi is used to:

- summarize findings
- prioritize issues
- explain likely risks
- suggest next steps
- generate example pandas code

This keeps the app grounded and limits model variance.

### 9.2 Compact profile instead of raw dataset upload

The prompt sent to Pi should contain a compact structured summary, not the full DataFrame. This reduces prompt size, improves latency, and avoids unnecessary data exposure.

### 9.3 Fresh Pi session per uploaded dataset

A new file upload starts a fresh session. Follow-up questions for that dataset continue in the same session until the next upload or explicit reset.

Rationale:

- preserves context naturally
- avoids accidental cross-dataset contamination
- maps cleanly to the existing `new_session()` API

### 9.4 Streaming is part of the demo value

The app should use `subscribe_events()` and display response text progressively. A non-streaming implementation would work, but it would under-demonstrate one of the strongest aspects of pibridge.

---

## 10. Detailed component design

## 10.1 UI layer

Recommended framework: `streamlit`

### UI sections

- **Header**: app title and short description
- **File uploader**: upload CSV
- **Dataset preview**: first N rows and shape
- **Profile summary**: tables/cards for missingness, duplicates, numeric highlights, suspicious columns
- **Analysis panel**: streamed Pi output
- **Follow-up box**: free-text question input
- **Status/error area**: parse or Pi errors

### Streamlit session state

The app should store in `st.session_state`:

- current uploaded file metadata
- current DataFrame profile object
- current Pi client handle or session state wrapper
- conversation history
- latest streaming buffer
- boolean flags such as `analysis_running`

Note: if storing the raw client object in session state proves awkward, the app can instead store only derived state and manage the client in a narrow app-level controller.

---

## 10.2 Data loading layer

### Responsibilities

- accept uploaded file bytes
- decode and parse with `pandas.read_csv`
- catch common parsing errors
- optionally support simple parse hints later (`sep`, encoding), but not in MVP

### API sketch

```python
def load_csv(uploaded_file) -> pd.DataFrame:
    ...
```

### Failure modes

- malformed CSV
- unsupported encoding
- empty file
- file too large for practical local analysis

The MVP may simply surface the exception message with a friendly wrapper.

---

## 10.3 Profiling layer

### Responsibilities

Build a compact `DatasetProfile` object from the DataFrame.

### Proposed profile fields

```python
from dataclasses import dataclass

@dataclass
class ColumnProfile:
    name: str
    dtype: str
    non_null_count: int
    null_count: int
    null_pct: float
    unique_count: int
    sample_values: list[str]
    notes: list[str]

@dataclass
class DatasetProfile:
    rows: int
    columns: int
    duplicate_rows: int
    numeric_summary: dict[str, dict[str, float | int | None]]
    categorical_top_values: dict[str, list[tuple[str, int]]]
    columns_profile: list[ColumnProfile]
    suspicious_columns: list[str]
```
```

### MVP heuristics

The profiler should flag lightweight, explainable issues such as:

- high null percentage
- duplicate rows present
- object/string columns with inconsistent casing in top values
- high-cardinality categorical columns
- likely ID columns
- low-variance columns
- numeric columns with extreme min/max relative to median
- datetime-looking strings that remain plain object dtype

These heuristics do not need to be statistically sophisticated; they need to be understandable and useful.

### Why a separate profile object

A structured profile:

- makes prompt generation cleaner
- enables deterministic testing
- keeps UI rendering and Pi prompting decoupled
- prevents accidental over-sharing of raw dataset contents

---

## 10.4 Prompt builder

### Responsibilities

Translate `DatasetProfile` into a compact structured prompt for Pi.

### Prompt design goals

- provide enough context for Pi to reason well
- keep the prompt bounded and readable
- make the requested output shape explicit
- encourage prioritization over generic narration

### Initial analysis prompt shape

The initial prompt should include:

- dataset dimensions
- dtype overview
- duplicate row count
- highest-null columns
- top suspicious columns/heuristics
- compact numeric and categorical highlights
- explicit request for:
  - concise overview
  - top issues ranked by impact
  - recommended cleanup steps
  - optional example pandas code

### Example prompt skeleton

```text
You are helping triage a CSV dataset.

Use the structured profile below. Do not invent metrics that are not present.
Base your analysis on the provided facts.

Dataset profile:
- rows: ...
- columns: ...
- duplicates: ...
- columns with highest missing %: ...
- suspicious columns: ...
- numeric highlights: ...
- categorical highlights: ...

Please provide:
1. A short overview of what this dataset appears to contain.
2. The top 3-5 data quality concerns, ranked by importance.
3. Recommended cleanup steps.
4. If useful, example pandas code for the most important fixes.
```

### Follow-up prompt handling

For the current shipped example, follow-up questions are sent with `prompt(..., streaming_behavior="followUp")`. That is the verified path that starts a new streamed turn immediately on the tested upstream build. Raw `follow_up()` requests are still part of the public RPC surface, but in the compatibility suite they queue pending work instead of starting an immediate streamed turn on their own.

---

## 10.5 Pi integration layer

### Responsibilities

- create and close the `PiClient`
- subscribe to events
- start a new session per uploaded dataset
- send initial `prompt()`
- send user follow-ups
- assemble streamed text from event deltas
- expose a simple controller API to the UI

### Proposed wrapper

```python
class DatasetTriageSession:
    def __init__(self, options: PiClientOptions) -> None:
        ...

    def reset_for_dataset(self, dataset_name: str) -> None:
        ...

    def analyze_profile(self, prompt: str) -> None:
        ...

    def ask_follow_up(self, question: str) -> None:
        ...

    def poll_events(self) -> list[AgentEvent]:
        ...
```

### Relevant `pi-rpc-python` APIs

The implementation will primarily use:

- `PiClient(...)`
- `subscribe_events(maxsize=...)`
- `new_session()`
- `set_session_name(...)`
- `prompt(...)`
- `prompt(..., streaming_behavior="followUp")` for user follow-ups
- `follow_up(...)` only if you intentionally want to exercise the raw queued follow-up RPC behavior
- `get_last_assistant_text()`
- optionally `export_html(...)` later

### Streaming behavior

The app should subscribe once per client and consume events until `agent_end`.

At minimum, the integration layer should handle:

- `message_update` text deltas for incremental rendering
- `agent_end` to mark completion
- process/stream errors surfaced through the subscription mechanism

If event typing exposes finer-grained message metadata, the app can filter for assistant text updates only.

---

## 11. Data flow

### Initial analysis flow

```text
upload CSV
  -> parse into DataFrame
  -> compute DatasetProfile
  -> create/reset Pi session
  -> build initial prompt
  -> client.prompt(...)
  -> consume streamed events
  -> render response incrementally
  -> store completed answer in conversation history
```

### Follow-up flow

```text
user enters question
  -> client.prompt(..., streaming_behavior="followUp")
  -> consume streamed events
  -> render response incrementally
  -> append to conversation history
```

---

## 12. Session model

### Session lifecycle

- app startup: initialize Pi client lazily
- file upload: call `new_session()` and optionally `set_session_name()`
- initial analysis: `prompt()`
- subsequent user questions: `prompt(..., streaming_behavior="followUp")`
- app shutdown/reset: `close()`

### Session naming

Useful session naming pattern:

```text
dataset-triage:<filename>
```

This makes exported or persisted sessions easier to identify.

### Why not reuse one session across uploads

Reusing one session risks:

- context bleed between datasets
- confusing follow-up behavior
- misleading summaries that reference prior files

A per-dataset session is simpler and more correct.

---

## 13. Error handling

### CSV errors

Show a user-friendly error banner for:

- parse failures
- empty file
- unsupported encoding

### Pi startup and runtime errors

Surface errors from:

- `PiStartupError`
- `PiProcessExitedError`
- `PiProtocolError`
- `PiCommandError`
- `PiTimeoutError`

The UI should display a concise message and allow the user to retry.

### Streaming/subscription errors

If the event subscription fails or overflows:

- mark the current response as failed
- show a helpful message
- allow the user to rerun analysis

Mitigation:

- use a reasonably large queue, e.g. `maxsize=500` or `1000`
- poll the stream continuously while analysis is active

---

## 14. Privacy and safety

This is a local-first example app, but prompts still leave the local process if Pi is configured to use a hosted model provider.

Design implications:

- do not send the full dataset by default
- send only compact summaries and small representative samples where useful
- avoid including obviously sensitive columns verbatim in the prompt if not needed
- explicitly mark likely sensitive columns (for example identifiers and emails) and redact their raw categorical values before sending the prompt
- let the user inspect the exact bounded prompt that will be sent to Pi

The MVP will not implement full PII detection, but the design should avoid gratuitous raw data inclusion.

---

## 15. Testing strategy

### Unit tests

Test deterministic parts without requiring a live Pi process:

- CSV loading behavior for valid/invalid inputs
- profile computation for representative DataFrames
- heuristic detection
- prompt builder output shape
- event-to-text assembly logic in the integration wrapper

### Integration tests

With a real or mock-backed Pi process, test:

- initial session setup for a dataset
- prompt submission and streaming completion
- follow-up question behavior in the same session via `prompt(..., streaming_behavior="followUp")`
- graceful handling of Pi startup/timeout failures

### Example fixtures

Use small in-memory CSVs such as:

- customer dataset with missing emails and duplicate rows
- sales dataset with date and category columns
- dirty categorical values (`US`, `us`, `United States`)

---

## 16. Observability and debugging

For a demo app, lightweight observability is enough.

Recommended debugging artifacts:

- log dataset shape and profile generation steps
- log when a new Pi session starts
- log prompt submission boundaries, not full sensitive content
- log event lifecycle markers (`agent_start`, `agent_end`)
- display a developer-friendly expandable debug panel later if needed

---

## 17. MVP file structure

Suggested example-app layout:

```text
examples/dataset_triage/
  README.md
  app.py
  loader.py
  profiler.py
  prompts.py
  pi_session.py
  models.py
  sample_data/
    customers.csv
```

### File responsibilities

- `app.py`: Streamlit UI and orchestration
- `loader.py`: CSV parsing helpers
- `profiler.py`: DataFrame -> `DatasetProfile`
- `prompts.py`: prompt generation
- `pi_session.py`: wrapper around `PiClient`
- `models.py`: dataclasses for structured profile data

---

## 18. Implementation phases

### Phase 1: deterministic local analysis

- CSV upload
- DataFrame preview
- profile computation
- suspicious-column heuristics
- local rendering without Pi

### Phase 2: Pi integration

- initialize `PiClient`
- create session per dataset
- initial prompt
- streamed response rendering

### Phase 3: follow-up chat

- question input
- follow-up submission
- conversation history display

### Phase 4: polish

- cleaner layout
- better errors
- sample CSV
- README/run instructions

---

## 19. Open questions

- Should the app offer a manual dataset summary edit box before sending to Pi?
- Should the app include a small sample-row excerpt in addition to aggregate stats?
- Should follow-up questions use `prompt()` or `follow_up()` consistently?
  - current verified recommendation: `prompt()` for the initial dataset analysis and `prompt(..., streaming_behavior="followUp")` for later turns
- Should we add optional charts in MVP or keep the first version text-first?
  - recommendation: keep MVP text-first

---

## 20. Recommendation

Build the MVP as a small Streamlit app with a strict separation between:

- deterministic profiling (`pandas`)
- prompt construction
- Pi session/streaming integration

This keeps the app easy to understand, showcases pibridge clearly, and leaves a clean path for later additions such as charts, HTML export, or richer profiling.
