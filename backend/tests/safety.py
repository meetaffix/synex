"""Test safety: tests must never run against the real database file.

`backend/synex.db` holds real data. Every test module calls `assert_isolated_database` before it
imports the app and again on the settings the app actually loaded, so a test run that would touch
`synex.db` (for example because the app was imported before the test's own database was set) stops
at import time instead of writing to it.
"""
import os
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
FORBIDDEN_NAME = "synex.db"


def _database_path(url: str) -> str:
    return url.split("///", 1)[1] if "///" in url else url


def assert_isolated_database(url: str) -> None:
    path = _database_path(url).replace("\\", "/")
    resolved = Path(path).resolve() if os.path.isabs(path) else (BACKEND / path).resolve()
    if os.path.basename(path).lower() == FORBIDDEN_NAME or resolved == (BACKEND / FORBIDDEN_NAME).resolve():
        raise RuntimeError(
            f"Refusing to run tests: DATABASE_URL points at {FORBIDDEN_NAME}. "
            "Tests must use a temporary database; they set DATABASE_URL before importing the app."
        )
