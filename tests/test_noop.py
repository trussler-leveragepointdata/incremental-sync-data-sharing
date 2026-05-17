"""Test 3: no-op ingest (spec required test).

Verifies that when the DB has no new rows since the last checkpoint, ingest returns
zero deltas and does not rewrite lake or share artifacts.
"""

from __future__ import annotations

from pathlib import Path

from tests.conftest import apply_changes_sql, file_checksum


def _lake_and_share_files(workspace) -> list[Path]:
    """Collect durable consumer/lake JSONL paths (exclude events — new event file per run)."""
    files = []
    for base in (workspace.lake, workspace.share):
        if base.exists():
            files.extend(p for p in base.rglob("*.jsonl") if p.is_file())
    return files


def test_noop_ingest(fresh_db, client, database_url, workspace):
    """Third ingest with no further DB changes must not mutate lake or share bytes.

    Setup:
    - Ingest #1: load seed.
    - Apply changes.sql + ingest #2: advance checkpoint through incremental batch.

    Action:
    - Snapshot SHA-256 checksums of all lake/share JSONL files.
    - Ingest #3 with no SQL changes.

    Assertions:
    - Manifest shows delta_row_count 0, empty lake_paths, null share_path per table.
    - Lake and share checksum maps are unchanged.

    Note:
    - A new ./events/<run_id>.jsonl is still written on each successful run (spec).
      That is why we compare lake/share only, not events/.
    """
    client.post("/ingest", params={"dry_run": False})
    apply_changes_sql(database_url)
    client.post("/ingest", params={"dry_run": False})

    checksums_before = {p: file_checksum(p) for p in _lake_and_share_files(workspace)}

    resp = client.post("/ingest", params={"dry_run": False})
    assert resp.status_code == 200
    manifest = resp.json()

    assert manifest["tables"]["customers"]["delta_row_count"] == 0
    assert manifest["tables"]["cases"]["delta_row_count"] == 0
    assert manifest["tables"]["customers"]["lake_paths"] == []
    assert manifest["tables"]["cases"]["lake_paths"] == []
    assert manifest["tables"]["customers"]["share_path"] is None
    assert manifest["tables"]["cases"]["share_path"] is None

    checksums_after = {p: file_checksum(p) for p in _lake_and_share_files(workspace)}
    assert checksums_before == checksums_after
