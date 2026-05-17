"""Test 1: initial ingest (spec required test).

Verifies the first ingest against a seeded database with no checkpoint file:
all seed rows are selected, artifacts are written, and a composite checkpoint is created.
"""

from __future__ import annotations

import json

from tests.conftest import read_jsonl


def test_initial_ingest(fresh_db, client, workspace):
    """First POST /ingest with dry_run=false on a fresh DB and empty state/.

    Setup:
    - fresh_db reloads Postgres so db/init.sql seeds >=30 customers and >=200 cases.
    - workspace has no checkpoint.json yet (treated as empty watermark).

    Action:
    - Call /ingest once.

    Assertions:
    - Manifest reports full seed counts (>= spec minimums).
    - checkpoint.json exists with both tables set.
    - Per-run event file and both share artifacts exist.
    - Share file for customers contains at least 30 upsert lines.
    """
    resp = client.post("/ingest", params={"dry_run": False})
    assert resp.status_code == 200
    manifest = resp.json()

    assert manifest["tables"]["customers"]["delta_row_count"] >= 30
    assert manifest["tables"]["cases"]["delta_row_count"] >= 200
    assert workspace.checkpoint.exists()

    run_id = manifest["run_id"]
    assert (workspace.events / f"{run_id}.jsonl").exists()
    assert (workspace.share / "customers" / "changes.jsonl").exists()
    assert (workspace.share / "cases" / "changes.jsonl").exists()

    cp = json.loads(workspace.checkpoint.read_text(encoding="utf-8"))
    assert cp["customers"] is not None
    assert cp["cases"] is not None

    share_customers = read_jsonl(workspace.share / "customers" / "changes.jsonl")
    assert len(share_customers) >= 30
