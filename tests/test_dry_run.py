"""Test 4: dry-run behavior."""

from __future__ import annotations

import json

from tests.conftest import file_checksum


def test_dry_run_does_not_write(fresh_db, client, workspace):
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
