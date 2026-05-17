"""Tests 7 and 8: share and event artifact structure (spec required tests).

Validates JSONL shape for consumer share files and durable per-run event files.
"""

from __future__ import annotations

from tests.conftest import read_jsonl

SHARE_FIELDS = {
    "customers": {
        "table",
        "op",
        "customer_id",
        "updated_at",
        "run_id",
        "schema_fingerprint",
        "checkpoint_after",
        "record",
    },
    "cases": {
        "table",
        "op",
        "case_id",
        "updated_at",
        "run_id",
        "schema_fingerprint",
        "checkpoint_after",
        "record",
    },
}

EVENT_FIELDS = {
    "table",
    "run_id",
    "schema_fingerprint",
    "delta_row_count",
    "lake_paths",
    "share_path",
    "checkpoint_after",
}


def test_share_artifact_structure(fresh_db, client, workspace):
    """Each share JSONL line includes required upsert envelope fields.

    Setup: fresh_db + one successful ingest (non-empty share files).

    Action: Read share/customers/changes.jsonl and share/cases/changes.jsonl.

    Assertions:
    - At least one line per table.
    - Every line contains the table-specific required keys and op == upsert.
    """
    manifest = client.post("/ingest", params={"dry_run": False}).json()
    for table in ("customers", "cases"):
        path = workspace.share / table / "changes.jsonl"
        lines = read_jsonl(path)
        assert lines
        for line in lines:
            assert SHARE_FIELDS[table].issubset(line.keys())
            assert line["op"] == "upsert"


def test_event_artifact_structure(fresh_db, client, workspace):
    """events/<run_id>.jsonl has exactly one line per table with required metadata.

    Setup: fresh_db + one successful ingest.

    Action: Open the event file named in the manifest.

    Assertions:
    - Exactly 2 lines (customers + cases).
    - Each line includes all EVENT_FIELDS.
    """
    manifest = client.post("/ingest", params={"dry_run": False}).json()
    run_id = manifest["run_id"]
    events = read_jsonl(workspace.events / f"{run_id}.jsonl")
    assert len(events) == 2
    tables = {e["table"] for e in events}
    assert tables == {"customers", "cases"}
    for event in events:
        assert EVENT_FIELDS.issubset(event.keys())


def test_zero_delta_event_on_noop(fresh_db, client, database_url, workspace):
    """No-op run still emits events with delta_row_count=0 and share_path=null.

    Setup:
    - Ingest seed, then ingest again with no DB changes (checkpoint already current).

    Action: Read event file from the second (no-op) manifest.

    Assertions:
    - Both table event lines report zero delta and null share_path (spec zero-delta rule).
    """
    client.post("/ingest", params={"dry_run": False})
    manifest = client.post("/ingest", params={"dry_run": False}).json()
    run_id = manifest["run_id"]
    events = read_jsonl(workspace.events / f"{run_id}.jsonl")
    for event in events:
        assert event["delta_row_count"] == 0
        assert event["share_path"] is None
