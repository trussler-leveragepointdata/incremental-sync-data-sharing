"""Test 5: composite watermark with timestamp ties (spec required test).

Verifies rows sharing the same updated_at are not skipped: ordering is
updated_at ASC, primary_key ASC, and checkpoint uses the last processed row.
"""

from __future__ import annotations

import psycopg

from src.checkpoint import load_checkpoint
from src.ingest import run_ingest
from tests.conftest import read_jsonl


def test_timestamp_tie_watermark(fresh_db, workspace, database_url):
    """Incremental ingest with multiple rows at one timestamp advances last_pk correctly.

    Setup:
    - fresh_db + initial ingest (32 seed customers, checkpoint at end of seed batch).
    - Insert 3 new customers with identical updated_at (IDs 33, 34, 35).

    Action:
    - run_ingest(dry_run=false) to process only rows after the checkpoint.

    Assertions:
    - delta_row_count == 3 for customers.
    - checkpoint.customers.updated_at equals the tie timestamp.
    - checkpoint.customers.last_pk == 35 (highest PK at that timestamp).
    - Share batch contains 3 tie rows with customer_ids in ascending order.
    """
    run_ingest(dry_run=False, paths=workspace, database_url=database_url)

    tie_ts = "2026-04-15T12:00:00Z"
    with psycopg.connect(database_url) as conn:
        conn.execute(
            """
            INSERT INTO customers (name, email, country, updated_at) VALUES
            ('Tie A', 'tie.a@example.com', 'US', %s),
            ('Tie B', 'tie.b@example.com', 'UK', %s),
            ('Tie C', 'tie.c@example.com', 'CA', %s)
            """,
            (tie_ts, tie_ts, tie_ts),
        )
        conn.commit()

    manifest = run_ingest(dry_run=False, paths=workspace, database_url=database_url)
    assert manifest["tables"]["customers"]["delta_row_count"] == 3

    cp = load_checkpoint(workspace.checkpoint)
    assert cp["customers"] is not None
    assert cp["customers"].updated_at.strftime("%Y-%m-%dT%H:%M:%SZ") == tie_ts
    assert cp["customers"].last_pk == 35

    share_lines = read_jsonl(workspace.share / "customers" / "changes.jsonl")
    tie_rows = [line for line in share_lines if line["updated_at"] == tie_ts]
    assert len(tie_rows) == 3
    pks = [line["customer_id"] for line in tie_rows]
    assert pks == sorted(pks)
