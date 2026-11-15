"""Error-body hygiene: a validation error must never carry the request values that caused it."""
from collections.abc import Iterable
from typing import Any

_KEEP = ("type", "loc", "msg")


def sanitize_errors(errors: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop `input` and `ctx` (which can hold the offending value) from pydantic error dicts."""
    return [{key: error[key] for key in _KEEP if key in error} for error in errors]
