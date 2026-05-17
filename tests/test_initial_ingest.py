"""Test 1: initial ingest."""

from __future__ import annotations

import json

from tests.conftest import read_jsonl


def test_initial_ingest(fresh_db, client, workspace):
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
