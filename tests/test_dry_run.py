"""Test 4: dry-run behavior (spec required test).

Verifies dry_run=true computes a manifest (including predicted checkpoint_after)
but performs no durable writes.
"""

from __future__ import annotations

from tests.conftest import file_checksum


def test_dry_run_does_not_write(fresh_db, client, workspace):
    """POST /ingest?dry_run=true must be read-only on disk.

    Setup:
    - fresh_db + one successful ingest to populate checkpoint, lake, share, events.

    Action:
    - Record checkpoint text, lake/share checksums, and event file count.
    - Call /ingest?dry_run=true.

    Assertions:
    - Response dry_run is true and includes predicted checkpoint_after.
    - On-disk checkpoint unchanged.
    - Every lake/share file has the same checksum as before.
    - No new event files under events/.
    """
    client.post("/ingest", params={"dry_run": False})

    checkpoint_text = workspace.checkpoint.read_text(encoding="utf-8")
    checksums = {
        p: file_checksum(p) for p in workspace.lake.rglob("*.jsonl")
    }
    checksums.update(
        {p: file_checksum(p) for p in workspace.share.rglob("*.jsonl")}
    )
    event_count = len(list(workspace.events.glob("*.jsonl")))

    resp = client.post("/ingest", params={"dry_run": True})
    assert resp.status_code == 200
    manifest = resp.json()

    assert manifest["dry_run"] is True
    assert manifest["checkpoint_after"] is not None
    assert manifest["checkpoint_after"]["customers"] is not None

    assert workspace.checkpoint.read_text(encoding="utf-8") == checkpoint_text
    for path, digest in checksums.items():
        assert file_checksum(path) == digest
    assert len(list(workspace.events.glob("*.jsonl"))) == event_count
