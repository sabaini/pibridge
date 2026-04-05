from __future__ import annotations

import importlib.util
import pathlib
import sys


def _load_runtime_config_module():
    path = pathlib.Path("examples/runtime_config.py")
    spec = importlib.util.spec_from_file_location("examples.runtime_config", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


runtime_config = _load_runtime_config_module()


def test_parse_example_extra_args_uses_shell_splitting() -> None:
    parsed = runtime_config.parse_example_extra_args("-e /tmp/mock.ts --log-level debug '--flag=spaced value'")

    assert parsed == ("-e", "/tmp/mock.ts", "--log-level", "debug", "--flag=spaced value")


def test_get_example_runtime_config_reads_trimmed_values() -> None:
    config = runtime_config.get_example_runtime_config(
        {
            runtime_config.EXAMPLE_PROVIDER_ENV: "  pi-rpc-mock  ",
            runtime_config.EXAMPLE_MODEL_ENV: " canned-responses ",
            runtime_config.EXAMPLE_EXTRA_ARGS_ENV: "  -e /tmp/mock.ts --debug  ",
            runtime_config.EXAMPLE_SESSION_DIR_ENV: " /tmp/pi-sessions ",
        }
    )

    assert config.provider == "pi-rpc-mock"
    assert config.model == "canned-responses"
    assert config.extra_args == ("-e", "/tmp/mock.ts", "--debug")
    assert config.session_dir == "/tmp/pi-sessions"


def test_build_example_client_options_merges_env_overrides_with_defaults() -> None:
    options = runtime_config.build_example_client_options(
        provider=runtime_config.DEFAULT_PROVIDER,
        model=runtime_config.DEFAULT_MODEL,
        session_dir="/tmp/default-sessions",
        extra_args=("-e", "/tmp/default-extension.ts"),
        env={
            runtime_config.EXAMPLE_PROVIDER_ENV: "pi-rpc-mock",
            runtime_config.EXAMPLE_MODEL_ENV: "canned-responses",
            runtime_config.EXAMPLE_EXTRA_ARGS_ENV: "-e /tmp/mock-provider.ts --log-level debug",
            runtime_config.EXAMPLE_SESSION_DIR_ENV: "/tmp/test-sessions",
        },
    )

    assert options.provider == "pi-rpc-mock"
    assert options.model == "canned-responses"
    assert options.session_dir == "/tmp/test-sessions"
    assert options.extra_args == (
        "-e",
        "/tmp/default-extension.ts",
        "-e",
        "/tmp/mock-provider.ts",
        "--log-level",
        "debug",
    )


def test_build_example_client_options_preserves_defaults_without_env() -> None:
    options = runtime_config.build_example_client_options(
        provider=runtime_config.DEFAULT_PROVIDER,
        model=runtime_config.DEFAULT_MODEL,
        session_dir="/tmp/default-sessions",
        extra_args=("-e", "/tmp/default-extension.ts"),
    )

    assert options.provider == runtime_config.DEFAULT_PROVIDER
    assert options.model == runtime_config.DEFAULT_MODEL
    assert options.session_dir == "/tmp/default-sessions"
    assert options.extra_args == ("-e", "/tmp/default-extension.ts")
