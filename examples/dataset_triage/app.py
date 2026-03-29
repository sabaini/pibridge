from __future__ import annotations

from typing import Any

import streamlit as st

try:
    from .loader import load_csv
    from .models import DatasetLoadError
    from .pi_session import DatasetTriageSession, DatasetTriageSessionError
    from .profiler import build_dataset_profile
    from .prompts import build_initial_analysis_prompt
except ImportError:  # pragma: no cover - supports `streamlit run examples/dataset_triage/app.py`
    from loader import load_csv
    from models import DatasetLoadError
    from pi_session import DatasetTriageSession, DatasetTriageSessionError
    from profiler import build_dataset_profile
    from prompts import build_initial_analysis_prompt


PREVIEW_ROWS = 20


def main() -> None:
    st.set_page_config(page_title="Dataset Triage Assistant", layout="wide")
    st.title("Dataset Triage Assistant")
    st.caption("Profile a CSV locally with pandas, then ask Pi for a streamed triage summary and follow-up guidance.")

    state = _state()
    uploaded_file = st.file_uploader("Upload a CSV file", type=["csv"])

    left, right = st.columns((3, 2))
    with right:
        if st.button("Reset conversation", disabled=state["loaded_dataset"] is None, use_container_width=True):
            _reset_conversation_state()
            state["session_needs_reset"] = True
            st.success("The next Pi request will start a fresh session for the current dataset.")

    with left:
        st.info("Try `examples/dataset_triage/sample_data/customers.csv` for a quick demo.")

    if uploaded_file is not None:
        _handle_upload(uploaded_file)

    loaded_dataset = state["loaded_dataset"]
    dataset_profile = state["dataset_profile"]

    if state["analysis_error"]:
        st.error(state["analysis_error"])

    if loaded_dataset is None or dataset_profile is None:
        st.warning("Upload a CSV to preview its contents, inspect a compact profile, and ask Pi for cleanup advice.")
        return

    preview_col, profile_col = st.columns((3, 2))
    with preview_col:
        st.subheader("Preview")
        st.write(f"**Dataset:** {loaded_dataset.upload.name or 'uploaded.csv'}")
        st.dataframe(loaded_dataset.dataframe.head(PREVIEW_ROWS), use_container_width=True)

    with profile_col:
        st.subheader("Profile summary")
        metrics = st.columns(3)
        metrics[0].metric("Rows", dataset_profile.rows)
        metrics[1].metric("Columns", dataset_profile.columns)
        metrics[2].metric("Duplicate rows", dataset_profile.duplicate_rows)
        if dataset_profile.suspicious_columns:
            st.markdown("**Suspicious columns**")
            for column in dataset_profile.suspicious_columns:
                st.markdown(f"- `{column.name}`: {', '.join(column.notes)}")
        else:
            st.success("No suspicious columns were flagged by the deterministic heuristics.")

    st.subheader("Conversation")
    for message in state["conversation_history"]:
        with st.chat_message(message["role"]):
            st.markdown(message["text"])

    stream_placeholder = st.empty()
    if state["latest_stream_text"]:
        with stream_placeholder.container():
            with st.chat_message("assistant"):
                st.markdown(state["latest_stream_text"])

    analyze_disabled = state["analysis_running"]
    if st.button("Analyze with Pi", disabled=analyze_disabled, type="primary", use_container_width=True):
        prompt = build_initial_analysis_prompt(dataset_profile, dataset_name=loaded_dataset.upload.name)
        state["conversation_history"].append({"role": "user", "text": "Analyze the uploaded dataset."})
        _run_streamed_request(
            lambda on_update: state["controller"].analyze_profile(prompt, on_update=on_update),
            dataset_name=loaded_dataset.upload.name or "uploaded.csv",
            placeholder=stream_placeholder,
            history=state["conversation_history"],
        )
        st.rerun()

    with st.form("follow_up_form", clear_on_submit=True):
        question = st.text_input("Ask a follow-up question", placeholder="Which three columns should I clean first?")
        submitted = st.form_submit_button("Send", disabled=analyze_disabled)
    if submitted and question.strip():
        state["conversation_history"].append({"role": "user", "text": question.strip()})
        _run_streamed_request(
            lambda on_update: state["controller"].ask_follow_up(question.strip(), on_update=on_update),
            dataset_name=loaded_dataset.upload.name or "uploaded.csv",
            placeholder=stream_placeholder,
            history=state["conversation_history"],
        )
        st.rerun()


def _handle_upload(uploaded_file: Any) -> None:
    state = _state()
    try:
        loaded_dataset = load_csv(uploaded_file)
    except DatasetLoadError as exc:
        state["analysis_error"] = str(exc)
        state["current_fingerprint"] = None
        state["loaded_dataset"] = None
        state["dataset_profile"] = None
        _reset_conversation_state()
        state["analysis_error"] = str(exc)
        return

    if state["current_fingerprint"] == loaded_dataset.upload.fingerprint:
        return

    state["current_fingerprint"] = loaded_dataset.upload.fingerprint
    state["loaded_dataset"] = loaded_dataset
    state["dataset_profile"] = build_dataset_profile(loaded_dataset.dataframe)
    state["analysis_error"] = None
    _reset_conversation_state()
    state["session_needs_reset"] = True


def _run_streamed_request(runner: Any, *, dataset_name: str, placeholder: Any, history: list[dict[str, str]]) -> None:
    state = _state()
    state["analysis_running"] = True
    state["latest_stream_text"] = ""
    state["analysis_error"] = None

    def on_update(text: str) -> None:
        state["latest_stream_text"] = text
        with placeholder.container():
            with st.chat_message("assistant"):
                st.markdown(text)

    try:
        _ensure_dataset_session(dataset_name)
        final_text = runner(on_update)
    except DatasetTriageSessionError as exc:
        state["analysis_error"] = str(exc)
    else:
        if final_text:
            history.append({"role": "assistant", "text": final_text})
            state["latest_stream_text"] = ""
    finally:
        state["analysis_running"] = False


def _ensure_dataset_session(dataset_name: str) -> None:
    state = _state()
    if not state["session_needs_reset"]:
        return
    state["controller"].reset_for_dataset(dataset_name)
    state["session_needs_reset"] = False


def _reset_conversation_state() -> None:
    state = _state()
    state["conversation_history"] = []
    state["latest_stream_text"] = ""
    state["analysis_error"] = None
    state["analysis_running"] = False


def _state() -> Any:
    if "controller" not in st.session_state:
        st.session_state.controller = DatasetTriageSession()
        st.session_state.current_fingerprint = None
        st.session_state.loaded_dataset = None
        st.session_state.dataset_profile = None
        st.session_state.conversation_history = []
        st.session_state.latest_stream_text = ""
        st.session_state.analysis_error = None
        st.session_state.analysis_running = False
        st.session_state.session_needs_reset = False
    return st.session_state


if __name__ == "__main__":
    main()
