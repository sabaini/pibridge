from __future__ import annotations

import gzip
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest

from tests.example_support import load_dataset_triage_module
from tests.integration.conftest import (
    MOCK_EXTENSION_PATH,
    REPO_ROOT,
    _example_runtime_env,
    mock_assistant_message,
    mock_context_key,
    mock_user_message,
)

streamlit_testing = pytest.importorskip("streamlit.testing.v1")
AppTest = streamlit_testing.AppTest

app_module = load_dataset_triage_module("app")
loader = load_dataset_triage_module("loader")
models = load_dataset_triage_module("models")
profiler = load_dataset_triage_module("profiler")
prompts = load_dataset_triage_module("prompts")
session_module = load_dataset_triage_module("pi_session")

pytestmark = pytest.mark.integration


class FakeUpload(BytesIO):
    def __init__(self, content: bytes, *, name: str = "customers.csv", content_type: str = "text/csv") -> None:
        super().__init__(content)
        self.name = name
        self.type = content_type
        self.size = len(content)

    def getvalue(self) -> bytes:
        return super().getvalue()


class ExportFailingController:
    def __init__(self, delegate: Any) -> None:
        self._delegate = delegate

    def __getattr__(self, name: str) -> Any:
        return getattr(self._delegate, name)

    def export_session_html(self, output_path: str | None = None) -> str:
        raise OSError("mock export failure")



def _button_by_label(app_test: Any, label: str) -> Any:
    for button in app_test.button:
        if getattr(button, "label", None) == label:
            return button
    raise AssertionError(f"button with label {label!r} not found")



def _dataset_upload() -> FakeUpload:
    payload = b"customer_id,email\n1,a@example.com\n2,b@example.com\n"
    return FakeUpload(gzip.compress(payload), name="customers.csv.gz", content_type="application/gzip")



def _analysis_prompt(upload: FakeUpload) -> str:
    loaded = loader.load_csv(upload, options=models.CsvLoadOptions())
    profile = profiler.build_dataset_profile(loaded.dataframe)
    return prompts.build_initial_analysis_prompt(profile, dataset_name=loaded.upload.name, load_metadata=loaded.load)



def _configure_mock_backend(monkeypatch: pytest.MonkeyPatch, workspace: Path, upload: FakeUpload) -> str:
    analysis_prompt = _analysis_prompt(upload)
    follow_up = "Which column should I clean first?"
    env = _example_runtime_env(
        workspace=workspace,
        prompt_map={analysis_prompt: "Initial analysis"},
        context_map={
            mock_context_key(
                mock_user_message(analysis_prompt),
                mock_assistant_message("Initial analysis"),
                mock_user_message(follow_up),
            ): "Clean the email column first.",
        },
        extra_args=("-e", str(MOCK_EXTENSION_PATH)),
    )
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    return follow_up



def test_dataset_triage_app_happy_path_follow_up_reset_and_export(
    monkeypatch: pytest.MonkeyPatch,
    isolated_pi_workspace: Path,
) -> None:
    upload = _dataset_upload()
    follow_up = _configure_mock_backend(monkeypatch, isolated_pi_workspace, upload)

    app = AppTest.from_file(str(REPO_ROOT / "examples/dataset_triage/app.py"), default_timeout=60)
    app.session_state["test_uploaded_file"] = upload
    app.run(timeout=60)

    assert app.session_state["loaded_dataset"].upload.name == "customers.csv.gz"
    assert app.session_state["has_completed_initial_analysis"] is False

    app.button(key="analyze_button").click().run(timeout=60)

    assert app.session_state["has_completed_initial_analysis"] is True
    assert app.session_state["analysis_running"] is False
    assert app.session_state["conversation_history"][-1]["text"] == "Initial analysis"
    assert app.session_state["session_export_bytes"] is None

    app.text_input(key="follow_up_question").set_value(follow_up).run(timeout=60)
    _button_by_label(app, "Send").click().run(timeout=60)

    assert app.session_state["conversation_history"][-1]["text"] == "Clean the email column first."
    assert app.session_state["analysis_error"] is None

    app.button(key="prepare_session_html_export_button").click().run(timeout=60)

    assert app.session_state["session_export_bytes"] is not None
    assert app.session_state["session_export_name"].endswith("-session.html")
    assert app.session_state["export_error"] is None

    app.button(key="reset_conversation_button").click().run(timeout=60)

    assert app.session_state["conversation_history"] == []
    assert app.session_state["has_completed_initial_analysis"] is False
    assert app.session_state["session_needs_reset"] is True



def test_dataset_triage_app_surfaces_export_failures(
    monkeypatch: pytest.MonkeyPatch,
    isolated_pi_workspace: Path,
) -> None:
    upload = _dataset_upload()
    _configure_mock_backend(monkeypatch, isolated_pi_workspace, upload)

    app = AppTest.from_file(str(REPO_ROOT / "examples/dataset_triage/app.py"), default_timeout=60)
    app.session_state["test_uploaded_file"] = upload
    app.run(timeout=60)
    app.button(key="analyze_button").click().run(timeout=60)

    app.session_state["controller"] = ExportFailingController(app.session_state["controller"])
    app.button(key="prepare_session_html_export_button").click().run(timeout=60)

    assert app.session_state["session_export_bytes"] is None
    assert app.session_state["export_error"] == "Session HTML export failed: mock export failure"
