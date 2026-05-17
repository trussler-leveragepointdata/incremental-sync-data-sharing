"""Test 6: deterministic run_id."""

from __future__ import annotations

import re

from src.ingest import run_ingest


SHA256_HEX = re.compile(r"^[a-f0-9]{64}$")


def test_deterministic_run_id(fresh_db, workspace, database_url):
    m1 = run_ingest(dry_run=False, paths=workspace, database_url=database_url)
    run_id_first = m1["run_id"]
    assert SHA256_HEX.match(run_id_first)

    d1 = run_ingest(dry_run=True, paths=workspace, database_url=database_url)
    d2 = run_ingest(dry_run=True, paths=workspace, database_url=database_url)
    assert d1["run_id"] == d2["run_id"]

    workspace.checkpoint.unlink()
    m2 = run_ingest(dry_run=False, paths=workspace, database_url=database_url)
    assert m2["run_id"] == run_id_first
