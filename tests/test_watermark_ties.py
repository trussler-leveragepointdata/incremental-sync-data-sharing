"""Test 5: composite watermark with timestamp ties."""

from __future__ import annotations

import psycopg

from src.checkpoint import load_checkpoint
from src.ingest import run_ingest


def test_timestamp_tie_watermark(fresh_db, workspace, database_url):
    tie_ts = "2026-04-15T12:00:00Z"
    with psycopg.connect(database_url) as conn:
        conn.execute(
            """
            INSERT INTO customers (name, email, country, updated_at) VALUES
            ('Tie A', 'tie.a@example.com', 'US', %s),
            ('Tie B', 'tie.b@example.com', 'UK', %s)
            """,
            (tie_ts, tie_ts),
        )
        conn.commit()

    run_ingest(dry_run=False, paths=workspace, database_url=database_url)

    cp = load_checkpoint(workspace.checkpoint)
    assert cp["customers"] is not None
    assert cp["customers"].updated_at.strftime("%Y-%m-%dT%H:%M:%SZ") == tie_ts
    assert cp["customers"].last_pk >= 35
