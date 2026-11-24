"""Carry per-entry diagnostics through an ordinary collector invocation."""

import logging
from contextvars import ContextVar

source_errors: ContextVar[list[str] | None] = ContextVar("source_errors", default=None)


def report_entry_error(message: str) -> None:
    errors = source_errors.get()
    if errors is None:
        logging.getLogger(__name__).warning("%s", message)
    else:
        errors.append(message)
