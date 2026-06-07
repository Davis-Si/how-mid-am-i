"""SQL guard — guardrail layer 2 (FR-19).

Parses any SQL with sqlglot and asserts it is a single read-only SELECT: no
DDL/DML (INSERT/UPDATE/DELETE/CREATE/DROP/ATTACH/PRAGMA), no multiple
statements. Layered on top of the read-only connection so a generated query is
rejected before it ever reaches DuckDB.
"""

from __future__ import annotations


class UnsafeSQLError(ValueError):
    """Raised when SQL is not a single read-only SELECT."""


def assert_select_only(sql: str) -> None:
    """Raise UnsafeSQLError unless ``sql`` is exactly one read-only SELECT."""
    raise NotImplementedError
