"""Test 2: incremental ingest after changes.sql (spec required test).

Verifies composite watermarking picks up only rows changed since the first ingest.
"""

from __future__ import annotations

from tests.conftest import apply_changes_sql


def test_incremental_after_changes(fresh_db, client, database_url):
    """Second ingest after db/changes.sql must match spec delta counts.

    Setup:
    - fresh_db + first ingest advances checkpoint to end of seed data.
    - apply_changes_sql: 2 new customers, 5 updated cases, 10 new cases (15 case deltas).

    Action:
    - Second POST /ingest with dry_run=false.

    Assertions:
    - customers delta_row_count == 2
    - cases delta_row_count == 15
    """
    client.post("/ingest", params={"dry_run": False})
    apply_changes_sql(database_url)

    resp = client.post("/ingest", params={"dry_run": False})
    assert resp.status_code == 200
    manifest = resp.json()

    assert manifest["tables"]["customers"]["delta_row_count"] == 2
    assert manifest["tables"]["cases"]["delta_row_count"] == 15
