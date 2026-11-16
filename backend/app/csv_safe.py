"""One place for CSV safety: text that starts with = + - @ (or a tab or carriage return) runs as a formula when a spreadsheet opens the file, so every
export neutralises it; every import limits the rows and refuses binary content."""
from __future__ import annotations

import csv
import io

FORMULA_START = ("=", "+", "-", "@", "\t", "\r")
MAX_IMPORT_ROWS = 10_000


class CsvTooLarge(ValueError):
    """The file is not something Synex will read; the message is shown to the person."""


def cell(value):
    """Text starting a formula gets a leading apostrophe. Numbers and empty values pass through."""
    if value is None:
        return ""
    if isinstance(value, str) and value[:1] in FORMULA_START:
        return "'" + value
    return value


def row(values) -> list:
    return [cell(v) for v in values]


def parse(text: str, max_rows: int = MAX_IMPORT_ROWS, dialect=None) -> tuple[list[str], list[dict]]:
    """Header names and at most `max_rows` rows. Refuses binary content (a NUL byte) and files with more rows than the limit."""
    if "\x00" in text:
        raise CsvTooLarge("That file is not a text CSV file.")
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")), dialect=dialect or csv.excel)
    rows = []
    for item in reader:
        if len(rows) >= max_rows:
            raise CsvTooLarge(f"The file has more than {max_rows:,} rows. Split it and import the parts one at a time.")
        rows.append(dict(item))
    return [h for h in (reader.fieldnames or []) if h is not None], rows
