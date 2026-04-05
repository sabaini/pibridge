from __future__ import annotations

import json
import os
import subprocess
import tempfile
import textwrap
import venv
from collections.abc import Iterable
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DIST_DIR = REPO_ROOT / "dist"
MOCK_EXTENSION_PATH = REPO_ROOT / "tests" / "integration" / "fixtures" / "mock_provider.ts"


RUNNER = """
from __future__ import annotations

import json
import queue
import tempfile
from pathlib import Path

from pi_rpc import PiClient, PiClientOptions

MOCK_PROVIDER_NAME = "pi-rpc-mock"
MOCK_MODEL_ID = "canned-responses"
MOCK_API_KEY_ENV = "PI_RPC_MOCK_API_KEY"
MOCK_PROMPT_MAP_ENV = "PI_RPC_MOCK_PROMPT_MAP"
MOCK_CONTEXT_MAP_ENV = "PI_RPC_MOCK_CONTEXT_MAP"


def mock_user_message(content: str) -> dict[str, str]:
    return {"role": "user", "content": content}


def mock_assistant_message(content: str) -> dict[str, str]:
    return {"role": "assistant", "content": content}


def mock_context_key(*messages: dict[str, str]) -> str:
    return json.dumps(list(messages), sort_keys=True, separators=(",", ":"))


prompt_map = {"Respond with the word BRIDGE.": "BRIDGE"}
context_map = {
    mock_context_key(
        mock_user_message("Respond with the word BRIDGE."),
        mock_assistant_message("BRIDGE"),
        mock_user_message("Use the verified follow-up path."),
    ): "FOLLOW-UP"
}

with tempfile.TemporaryDirectory() as workspace_root:
    workspace = Path(workspace_root)
    session_dir = workspace / "sessions"
    session_dir.mkdir()
    options = PiClientOptions(
        provider=MOCK_PROVIDER_NAME,
        model=MOCK_MODEL_ID,
        cwd=str(workspace),
        session_dir=str(session_dir),
        extra_args=("-e", "__MOCK_EXTENSION_PATH__"),
        env={
            MOCK_API_KEY_ENV: "pi-rpc-mock-test-key",
            MOCK_PROMPT_MAP_ENV: json.dumps(prompt_map, sort_keys=True),
            MOCK_CONTEXT_MAP_ENV: json.dumps(context_map, sort_keys=True),
        },
    )
    with PiClient(options) as client:
        subscription = client.subscribe_events(maxsize=200)
        state = client.get_state()
        client.prompt("Respond with the word BRIDGE.")
        while True:
            event = subscription.get(timeout=60)
            if event.type == "agent_end":
                break
        client.continue_prompt("Use the verified follow-up path.")
        while True:
            event = subscription.get(timeout=60)
            if event.type == "agent_end":
                break
        print(json.dumps({"session_id": state.session_id, "final_text": client.get_last_assistant_text()}, sort_keys=True))
"""


def _python_in_venv(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"



def select_built_wheel(wheels: Iterable[Path]) -> Path:
    candidates = list(wheels)
    if not candidates:
        raise SystemExit(f"No wheel found in {DIST_DIR}; run `python -m build` first.")
    return max(candidates, key=lambda wheel: (wheel.stat().st_mtime_ns, wheel.name))



def main() -> None:
    if not MOCK_EXTENSION_PATH.exists():
        raise SystemExit(f"Mock provider fixture not found: {MOCK_EXTENSION_PATH}")

    wheel = select_built_wheel(DIST_DIR.glob("*.whl"))
    with tempfile.TemporaryDirectory(prefix="pi-rpc-install-smoke-") as temp_root:
        temp_path = Path(temp_root)
        venv_dir = temp_path / "venv"
        venv.EnvBuilder(with_pip=True).create(venv_dir)
        python = _python_in_venv(venv_dir)
        runner_path = temp_path / "smoke_runner.py"
        runner_source = textwrap.dedent(RUNNER).replace("__MOCK_EXTENSION_PATH__", str(MOCK_EXTENSION_PATH))
        runner_path.write_text(runner_source, encoding="utf-8")

        env = dict(os.environ)
        env.pop("PYTHONPATH", None)

        subprocess.run([str(python), "-m", "pip", "install", "--upgrade", "pip"], check=True, cwd=temp_path, env=env)
        subprocess.run([str(python), "-m", "pip", "install", str(wheel)], check=True, cwd=temp_path, env=env)
        completed = subprocess.run([str(python), str(runner_path)], check=True, cwd=temp_path, env=env, capture_output=True, text=True)

        payload = json.loads(completed.stdout.strip())
        if not payload.get("session_id"):
            raise SystemExit(f"Installed wheel smoke did not produce a session id: {completed.stdout}")
        if payload.get("final_text") != "FOLLOW-UP":
            raise SystemExit(f"Installed wheel smoke returned unexpected assistant text: {completed.stdout}")
        print(f"Installed wheel smoke passed for {wheel.name}: {payload['final_text']}")


if __name__ == "__main__":
    main()
