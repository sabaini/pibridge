set shell := ["bash", "-eu", "-o", "pipefail", "-c"]

python_cmd := "if [[ -x .venv/bin/python ]]; then echo .venv/bin/python; elif command -v python3 >/dev/null 2>&1; then echo python3; else echo python; fi"

bootstrap_python_cmd := "if command -v python3 >/dev/null 2>&1; then echo python3; else echo python; fi"

ruff_cmd := "if [[ -x .venv/bin/ruff ]]; then echo .venv/bin/ruff; else echo ruff; fi"

default:
    @just --list

build:
    "$({{python_cmd}})" -m build

test:
    "$({{python_cmd}})" -m pytest -m 'not integration'

test-all:
    "$({{python_cmd}})" -m pytest

test-integration:
    "$({{python_cmd}})" -m pytest -m integration

lint:
    "$({{ruff_cmd}})" check .

typecheck:
    "$({{python_cmd}})" -m mypy src

check: lint typecheck test build

check-all: check test-integration

clean:
    rm -rf build dist .pytest_cache .ruff_cache .mypy_cache

dataset-triage-setup:
    if [[ ! -x .venv/bin/python ]]; then "$({{bootstrap_python_cmd}})" -m venv .venv; fi
    if ! .venv/bin/python -m pip --version >/dev/null 2>&1; then .venv/bin/python -m ensurepip --upgrade; fi
    if [[ ! -f .venv/.dataset-triage-ready || pyproject.toml -nt .venv/.dataset-triage-ready ]]; then .venv/bin/python -m pip install -e '.[examples]' && touch .venv/.dataset-triage-ready; fi

dataset-triage: dataset-triage-setup
    .venv/bin/python -m streamlit run examples/dataset_triage/app.py

dataset_triage: dataset-triage
