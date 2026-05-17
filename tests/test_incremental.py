"""Test 2: incremental ingest after changes.sql."""

from __future__ import annotations

from tests.conftest import apply_changes_sql


def test_incremental_after_changes(fresh_db, client, database_url):
    client.post("/ingest", params={"dry_run": False})
    apply_changes_sql(database_url)

    resp = client.post("/ingest", params={"dry_run": False})
    assert resp.status_code == 200
    manifest = resp.json()

    assert manifest["tables"]["customers"]["delta_row_count"] == 2
    assert manifest["tables"]["cases"]["delta_row_count"] == 15
