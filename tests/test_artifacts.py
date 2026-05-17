"""Tests 7 and 8: share and event artifact structure."""

from __future__ import annotations

from tests.conftest import read_jsonl


SHARE_FIELDS = {
    "customers": {"table", "op", "customer_id", "updated_at", "run_id", "schema_fingerprint", "checkpoint_after", "record"},
    "cases": {"table", "op", "case_id", "updated_at", "run_id", "schema_fingerprint", "checkpoint_after", "record"},
}

EVENT_FIELDS = {
    "table", "run_id", "schema_fingerprint", "delta_row_count", "lake_paths", "share_path", "checkpoint_after"
}


def test_share_artifact_structure(fresh_db, client, workspace):
    manifest = client.post("/ingest", params={"dry_run": False}).json()
    for table in ("customers", "cases"):
        path = workspace.share / table / "changes.jsonl"
        lines = read_jsonl(path)
        assert lines
        for line in lines:
            assert SHARE_FIELDS[table].issubset(line.keys())
            assert line["op"] == "upsert"


def test_event_artifact_structure(fresh_db, client, workspace):
    manifest = client.post("/ingest", params={"dry_run": False}).json()
    run_id = manifest["run_id"]
    events = read_jsonl(workspace.events / f"{run_id}.jsonl")
    assert len(events) == 2
    tables = {e["table"] for e in events}
    assert tables == {"customers", "cases"}
    for event in events:
        assert EVENT_FIELDS.issubset(event.keys())


def test_zero_delta_event_on_noop(fresh_db, client, database_url, workspace):
    client.post("/ingest", params={"dry_run": False})
    manifest = client.post("/ingest", params={"dry_run": False}).json()
    run_id = manifest["run_id"]
    events = read_jsonl(workspace.events / f"{run_id}.jsonl")
    for event in events:
        assert event["delta_row_count"] == 0
        assert event["share_path"] is None
