"""Stable schema fingerprint per table."""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from typing import Any

from src.database import TABLE_COLUMNS, connect


def _fetch_schema_columns(table: str, database_url: str) -> list[dict[str, str]]:
    if table not in TABLE_COLUMNS:
        raise ValueError(f"Unknown table: {table}")
    with connect(database_url) as conn:
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
    if not rows:
        raise ValueError(f"No columns found for table {table!r}")
    return [
        {"column_name": row["column_name"], "data_type": row["data_type"]}
        for row in rows
    ]


@lru_cache(maxsize=8)
def schema_fingerprint(table: str, database_url: str) -> str:
    schema = _fetch_schema_columns(table, database_url)
    canonical = json.dumps(schema, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def fingerprints_for_tables(
    tables: tuple[str, ...],
    database_url: str,
) -> dict[str, str]:
    return {table: schema_fingerprint(table, database_url) for table in tables}
