.PHONY: venv fmt lint type test unit deadcode

VENV=.venv
PY=$(VENV)/bin/python

venv:
	python3.14 -m venv $(VENV)
	$(PY) -m pip install -U pip
	$(PY) -m pip install ruff mypy pytest vulture
	$(PY) -m pip install -e .

fmt:
	$(PY) -m ruff format

lint:
	$(PY) -m ruff check .

type:
	$(PY) -m mypy .

# Code nothing calls. Paths and threshold live in pyproject under
# [tool.vulture]; tests/ is deliberately not among them. To look below the
# threshold while hunting, say so: `$(PY) -m vulture --min-confidence 0`.
deadcode:
	$(PY) -m vulture

unit:
	$(PY) -m pytest -q

test: unit
