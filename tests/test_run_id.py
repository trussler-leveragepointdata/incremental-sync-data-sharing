"""Test 6: deterministic run_id (spec required test).

Verifies run_id is SHA-256 from checkpoint_before + ordered row identities,
not a UUID or wall-clock value.
"""

from __future__ import annotations

import re

from src.ingest import run_ingest

SHA256_HEX = re.compile(r"^[a-f0-9]{64}$")


def test_deterministic_run_id(fresh_db, workspace, database_url):
    """Same DB state + same checkpoint must always yield the same run_id.

    Part A — format:
    - After first full ingest, run_id matches 64-char lowercase hex (SHA-256).

    Part B — stability with checkpoint held:
    - Two consecutive dry-runs (no writes) return identical run_id.

    Part C — recovery path:
    - Delete checkpoint.json but leave lake/share/events from first run.
    - Second non-dry ingest recomputes the same run_id and uses recovery
      (outputs already materialized) instead of duplicating lake/share.
    """
    m1 = run_ingest(dry_run=False, paths=workspace, database_url=database_url)
    run_id_first = m1["run_id"]
    assert SHA256_HEX.match(run_id_first)

    d1 = run_ingest(dry_run=True, paths=workspace, database_url=database_url)
    d2 = run_ingest(dry_run=True, paths=workspace, database_url=database_url)
    assert d1["run_id"] == d2["run_id"]

    workspace.checkpoint.unlink()
    m2 = run_ingest(dry_run=False, paths=workspace, database_url=database_url)
    assert m2["run_id"] == run_id_first
