"""Schema fingerprint sourced from information_schema (optional hardening)."""

from __future__ import annotations

import hashlib
import json

import psycopg

from src.schema import schema_fingerprint


def _expected_fingerprint(conn: psycopg.Connection, table: str) -> str:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = %s
            ORDER BY ordinal_position
            """,
            (table,),
        )
        rows = cur.fetchall()
    schema = [
        {"column_name": name, "data_type": dtype} for name, dtype in rows
    ]
    canonical = json.dumps(schema, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def test_schema_fingerprint_from_information_schema(fresh_db, database_url):
    """Fingerprint matches a direct information_schema query and is stable."""
    with psycopg.connect(database_url) as conn:
        expected_customers = _expected_fingerprint(conn, "customers")
        expected_cases = _expected_fingerprint(conn, "cases")

    assert schema_fingerprint("customers", database_url) == expected_customers
    assert schema_fingerprint("cases", database_url) == expected_cases
    assert len(expected_customers) == 64
    assert schema_fingerprint("customers", database_url) == expected_customers
