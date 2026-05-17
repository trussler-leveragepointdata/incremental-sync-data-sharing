"""Test 9: failure safety — checkpoint not advanced on write failure."""

from __future__ import annotations

import json

import pytest

from src.ingest import CheckpointWriteBlocked, run_ingest


def test_checkpoint_not_advanced_on_failure(
    fresh_db, workspace, database_url
):
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
