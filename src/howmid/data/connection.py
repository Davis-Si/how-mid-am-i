"""Read-only DuckDB connection factory — guardrail layer 1 (FR-19).

The app NEVER opens the warehouse writable. Read-only enforcement happens here
at the connection level (not just as a prompt instruction), so even a flawed or
injected query physically cannot mutate the data. The SQL-text guard
(``guardrails/sql_guard.py``) is layer 2 on top of this.
"""

from __future__ import annotations

from contextlib import contextmanager
from collections.abc import Iterator
from typing import TYPE_CHECKING

import duckdb

from howmid import config

if TYPE_CHECKING:
    pass


@contextmanager
def read_only_connection() -> Iterator["duckdb.DuckDBPyConnection"]:
    """Yield a read-only connection to the warehouse (``config.DB_PATH``).

    Opened with ``read_only=True`` so the process physically cannot mutate the
    data — any write (CREATE/INSERT/UPDATE) raises at the DuckDB layer. The
    connection is always closed on exit, even on error.
    """
    con = duckdb.connect(str(config.DB_PATH), read_only=True)
    try:
        yield con
    finally:
        con.close()
