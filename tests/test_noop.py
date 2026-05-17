"""Test 3: no-op ingest."""

from __future__ import annotations

from pathlib import Path

from tests.conftest import apply_changes_sql, file_checksum


def _all_output_files(workspace) -> list[Path]:
    files = []
    for base in (workspace.lake, workspace.share, workspace.events):
        if base.exists():
            files.extend(p for p in base.rglob("*.jsonl") if p.is_file())
    return files


def test_noop_ingest(fresh_db, client, database_url, workspace):
    client.post("/ingest", params={"dry_run": False})
    apply_changes_sql(database_url)
    client.post("/ingest", params={"dry_run": False})

    checksums_before = {p: file_checksum(p) for p in _all_output_files(workspace)}

    resp = client.post("/ingest", params={"dry_run": False})
    assert resp.status_code == 200
    manifest = resp.json()

    assert manifest["tables"]["customers"]["delta_row_count"] == 0
    assert manifest["tables"]["cases"]["delta_row_count"] == 0
    assert manifest["tables"]["customers"]["lake_paths"] == []
    assert manifest["tables"]["cases"]["lake_paths"] == []
    assert manifest["tables"]["customers"]["share_path"] is None
    assert manifest["tables"]["cases"]["share_path"] is None

    checksums_after = {p: file_checksum(p) for p in _all_output_files(workspace)}
    assert checksums_before == checksums_after
