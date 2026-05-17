"""Stable schema fingerprint per table."""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from typing import Any

from src.database import TABLE_COLUMNS


@lru_cache(maxsize=8)
def schema_fingerprint(table: str, database_url: str) -> str:
    columns = TABLE_COLUMNS[table]
    types_map = {
        "customers": {
            "customer_id": "bigint",
            "name": "text",
            "email": "text",
            "country": "text",
            "updated_at": "timestamp with time zone",
        },
        "cases": {
            "case_id": "bigint",
            "customer_id": "bigint",
            "title": "text",
            "description": "text",
            "status": "text",
            "updated_at": "timestamp with time zone",
        },
    }
    schema = [
        {"column_name": col, "data_type": types_map[table][col]}
        for col in columns
    ]
    canonical = json.dumps(schema, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def fingerprints_for_tables(
    tables: tuple[str, ...],
    database_url: str,
) -> dict[str, str]:
    return {table: schema_fingerprint(table, database_url) for table in tables}
