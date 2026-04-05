from __future__ import annotations

from pathlib import Path

import pytest

from tests.integration.conftest import (
    MOCK_EXTENSION_PATH,
    REPO_ROOT,
    RPC_UI_DEMO_EXTENSION_PATH,
    _example_runtime_env,
    _run_python_example,
    bash_execution_context_text,
    mock_context_key,
    mock_user_message,
)

pytestmark = pytest.mark.integration


EXAMPLES_DIR = REPO_ROOT / "examples"


def _assert_example_run(result, *expected_markers: str) -> None:
    assert result.returncode == 0, f"stdout:\n{result.stdout}\n\nstderr:\n{result.stderr}"
    for marker in expected_markers:
        assert marker in result.stdout, result.stdout



def test_basic_prompt_example_runs_against_mock_provider(isolated_pi_workspace: Path) -> None:
    env = _example_runtime_env(
        workspace=isolated_pi_workspace,
        prompt_map={"Reply with exactly: hello": "hello"},
        context_map={},
        extra_args=("-e", str(MOCK_EXTENSION_PATH)),
    )

    result = _run_python_example(EXAMPLES_DIR / "basic_prompt.py", workspace=isolated_pi_workspace, env=env)

    _assert_example_run(result, "[done/basic_prompt] hello")



def test_session_flow_example_runs_against_mock_provider(isolated_pi_workspace: Path) -> None:
    env = _example_runtime_env(
        workspace=isolated_pi_workspace,
        prompt_map={},
        context_map={},
        extra_args=("-e", str(MOCK_EXTENSION_PATH)),
    )

    result = _run_python_example(EXAMPLES_DIR / "session_flow.py", workspace=isolated_pi_workspace, env=env)

    _assert_example_run(result, "Current session:", "Updated session name:", "[done/session_flow]")



def test_bash_then_prompt_example_runs_against_mock_provider(isolated_pi_workspace: Path) -> None:
    context_map = {
        mock_context_key(
            mock_user_message(bash_execution_context_text("pwd", f"{isolated_pi_workspace}\n")),
            mock_user_message(bash_execution_context_text("ls -1", "example-sessions\n")),
            mock_user_message("Summarize what those commands showed."),
        ): f"pwd={isolated_pi_workspace}; ls=example-sessions",
    }
    env = _example_runtime_env(
        workspace=isolated_pi_workspace,
        prompt_map={},
        context_map=context_map,
        extra_args=("-e", str(MOCK_EXTENSION_PATH)),
    )

    result = _run_python_example(EXAMPLES_DIR / "bash_then_prompt.py", workspace=isolated_pi_workspace, env=env)

    _assert_example_run(result, "bash 1 exit: 0", "bash 2 exit: 0", f"[done/bash_then_prompt] pwd={isolated_pi_workspace}; ls=example-sessions")



def test_extension_ui_example_runs_against_mock_provider(isolated_pi_workspace: Path) -> None:
    env = _example_runtime_env(
        workspace=isolated_pi_workspace,
        prompt_map={},
        context_map={},
        extra_args=("-e", str(MOCK_EXTENSION_PATH), "-e", str(RPC_UI_DEMO_EXTENSION_PATH)),
    )

    result = _run_python_example(EXAMPLES_DIR / "extension_ui.py", workspace=isolated_pi_workspace, env=env)

    _assert_example_run(result, "[done/extension_ui]")



def test_review_gate_ui_example_runs_against_mock_provider(isolated_pi_workspace: Path) -> None:
    env = _example_runtime_env(
        workspace=isolated_pi_workspace,
        prompt_map={},
        context_map={},
        extra_args=("-e", str(MOCK_EXTENSION_PATH)),
    )

    result = _run_python_example(EXAMPLES_DIR / "review_gate_ui.py", workspace=isolated_pi_workspace, env=env)

    _assert_example_run(result, "[done/review_gate_ui]")
