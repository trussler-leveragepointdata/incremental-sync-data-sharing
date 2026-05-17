"""Postgres connection and incremental delta queries."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

import psycopg
from psycopg.rows import dict_row

from src.checkpoint import PK_FIELDS, Watermark, format_ts
from src.config import get_database_url

TABLE_COLUMNS = {
    "customers": (
        "customer_id",
        "name",
        "email",
        "country",
        "updated_at",
    ),
    "cases": (
        "case_id",
        "customer_id",
        "title",
        "description",
        "status",
        "updated_at",
    ),
}


@contextmanager
def connect(database_url: str | None = None) -> Iterator[psycopg.Connection]:
    url = database_url or get_database_url()
    conn = psycopg.connect(url, row_factory=dict_row)
    try:
        yield conn
    finally:
        conn.close()


def fetch_delta(
    conn: psycopg.Connection,
    table: str,
    watermark: Watermark | None,
) -> list[dict[str, Any]]:
    pk = PK_FIELDS[table]
    cols = ", ".join(TABLE_COLUMNS[table])
    if watermark is None:
        query = f"""
            SELECT {cols}
            FROM {table}
            ORDER BY updated_at ASC, {pk} ASC
        """
        params: tuple[Any, ...] = ()
    else:
        query = f"""
            SELECT {cols}
            FROM {table}
            WHERE updated_at > %(wm_at)s
               OR (updated_at = %(wm_at)s AND {pk} > %(wm_pk)s)
            ORDER BY updated_at ASC, {pk} ASC
        """
        params = {
            "wm_at": watermark.updated_at,
            "wm_pk": watermark.last_pk,
        }
    with conn.cursor() as cur:
        cur.execute(query, params)
        rows = cur.fetchall()
    return [serialize_row(dict(row)) for row in rows]


def serialize_row(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    if "updated_at" in out:
        out["updated_at"] = format_ts(out["updated_at"])
    return out
