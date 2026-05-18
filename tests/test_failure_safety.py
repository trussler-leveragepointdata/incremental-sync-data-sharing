"""Test 9: failure safety — checkpoint not advanced on write failure (spec required test).

Verifies checkpoint-last commit: if durable outputs are written but checkpoint
save fails, the on-disk checkpoint must remain at its previous value.
"""

from __future__ import annotations

import json

import pytest

from src.ingest import CheckpointWriteBlocked, run_ingest


def _lake_and_share_files(workspace) -> list:
    files = []
    for base in (workspace.lake, workspace.share):
        if base.exists():
            files.extend(p for p in base.rglob("*.jsonl") if p.is_file())
    return files


def test_checkpoint_not_advanced_on_failure(
    fresh_db, workspace, database_url
):
    """Simulated failure immediately before checkpoint write leaves checkpoint unchanged.

    Setup:
    - Ingest seed to establish checkpoint A.
    - apply_changes.sql so a second ingest has non-empty deltas.

    Action:
    - run_ingest with before_checkpoint_write hook that raises CheckpointWriteBlocked
      after lake/share/events are promoted but before save_checkpoint().

    Assertions:
    - Ingest raises CheckpointWriteBlocked.
    - checkpoint.json still matches checkpoint A (byte-for-byte).
    - Lake/share/event outputs from promotion exist (checkpoint-last failure mode).
    - Prior checkpoint JSON remains valid.
    """
    from tests.conftest import apply_changes_sql, file_checksum

    run_ingest(dry_run=False, paths=workspace, database_url=database_url)
    apply_changes_sql(database_url)
    cp_before = workspace.checkpoint.read_text(encoding="utf-8")
    checksums_before = {
        p: file_checksum(p) for p in _lake_and_share_files(workspace)
    }
    events_before = set(workspace.events.glob("*.jsonl"))

    with pytest.raises(CheckpointWriteBlocked):
        run_ingest(
            dry_run=False,
            paths=workspace,
            database_url=database_url,
            before_checkpoint_write=lambda: (_ for _ in ()).throw(
                CheckpointWriteBlocked("blocked for test")
            ),
        )

    assert workspace.checkpoint.read_text(encoding="utf-8") == cp_before
    json.loads(cp_before)

    checksums_after = {
        p: file_checksum(p) for p in _lake_and_share_files(workspace)
    }
    assert checksums_after != checksums_before
    assert workspace.share / "customers" / "changes.jsonl" in checksums_after
    assert workspace.share / "cases" / "changes.jsonl" in checksums_after

    events_after = set(workspace.events.glob("*.jsonl"))
    assert len(events_after) == len(events_before) + 1
    new_events = events_after - events_before
    assert len(new_events) == 1
    assert new_events.pop().stat().st_size > 0
