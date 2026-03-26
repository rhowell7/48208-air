PYTHON = .venv/bin/python
PYTEST = .venv/bin/pytest
RUFF   = .venv/bin/ruff

.PHONY: test lint fmt check

test:
	$(PYTEST)

lint:
	$(RUFF) check .

fmt:
	$(RUFF) format .

check: lint fmt-check test

fmt-check:
	$(RUFF) format --check .
