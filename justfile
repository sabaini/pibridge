set shell := ["bash", "-eu", "-o", "pipefail", "-c"]

python_cmd := "if [[ -x .venv/bin/python ]]; then echo .venv/bin/python; elif command -v python3 >/dev/null 2>&1; then echo python3; else echo python; fi"

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
