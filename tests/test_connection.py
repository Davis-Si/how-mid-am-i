"""Tests for the read-only warehouse connection (guardrail layer 1, FR-19)."""

from __future__ import annotations

import duckdb
import pytest

from howmid.data.connection import read_only_connection


def test_yields_working_read_connection():
    """The connection can read the warehouse."""
    with read_only_connection() as con:
        (n,) = con.execute("SELECT count(*) FROM fct_results").fetchone()
    assert n > 0


def test_rejects_create_table():
    """A write (CREATE TABLE) must fail — the connection is physically read-only."""
    with read_only_connection() as con:
        with pytest.raises(duckdb.Error):
            con.execute("CREATE TABLE should_not_exist (x INTEGER)")


def test_rejects_insert():
    """A write (INSERT) must fail too."""
    with read_only_connection() as con:
        with pytest.raises(duckdb.Error):
            con.execute("INSERT INTO fct_results (raceID) VALUES ('x')")


def test_connection_closed_on_exit():
    """The connection is closed when the context manager exits."""
    with read_only_connection() as con:
        pass
    # Using a closed connection raises.
    with pytest.raises(duckdb.Error):
        con.execute("SELECT 1")
