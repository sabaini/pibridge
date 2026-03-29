from __future__ import annotations

from tests.integration import conftest as integration_conftest


def test_integration_required_reads_truthy_env_values(monkeypatch) -> None:
    monkeypatch.setenv("PI_RPC_REQUIRE_INTEGRATION", "true")
    assert integration_conftest._integration_required() is True

    monkeypatch.setenv("PI_RPC_REQUIRE_INTEGRATION", "0")
    assert integration_conftest._integration_required() is False


def test_integration_availability_outcome_skips_when_optional() -> None:
    outcome, message = integration_conftest._integration_availability_outcome(
        ready=False,
        reason="pi executable not found on PATH",
        required=False,
    )

    assert outcome == "skip"
    assert message == "pi executable not found on PATH"


def test_integration_availability_outcome_fails_when_required() -> None:
    outcome, message = integration_conftest._integration_availability_outcome(
        ready=False,
        reason="pi executable not found on PATH",
        required=True,
    )

    assert outcome == "fail"
    assert message == "Integration tests are required but unavailable: pi executable not found on PATH"
