"""Test 9: failure safety — checkpoint not advanced on write failure (spec required test).

Verifies checkpoint-last commit: if durable outputs are written but checkpoint
save fails, the on-disk checkpoint must remain at its previous value.
"""

from __future__ import annotations

import json

import pytest

from src.ingest import CheckpointWriteBlocked, run_ingest


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
    - Prior checkpoint JSON remains valid.
    """
    from tests.conftest import apply_changes_sql

    run_ingest(dry_run=False, paths=workspace, database_url=database_url)
    apply_changes_sql(database_url)
    cp_before = workspace.checkpoint.read_text(encoding="utf-8")

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
