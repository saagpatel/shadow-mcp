.PHONY: setup check build

setup:
	uv sync --locked

check:
	@if ! command -v uv >/dev/null 2>&1 || [ ! -d .venv ]; then \
		echo "Run 'make setup' first (uv and the project venv are required)." >&2; \
		exit 1; \
	fi
	uv lock --check
	uv run --no-sync ruff check .
	uv run --no-sync ruff format --check .
	uv run --no-sync mypy src
	uv run --no-sync pytest

build:
	uv build --out-dir dist/
