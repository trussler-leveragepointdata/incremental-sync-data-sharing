"""Share artifact byte-for-byte determinism (spec ~592).

Verifies that the same source DB state and checkpoint produce identical
share JSONL bytes across repeated successful materialization.
"""

from __future__ import annotations

from src.ingest import run_ingest
from tests.conftest import file_checksum


def test_share_artifact_byte_identical_on_rewrite(fresh_db, workspace, database_url):
    """Re-materializing the same delta yields identical share file bytes.

    Setup:
    - fresh_db + full ingest (checkpoint at end of seed, share files written).

    Action:
    - Record checksums of both share files.
    - Remove checkpoint and event file so recovery cannot short-circuit.
    - Delete share artifacts.
    - Run ingest again (same DB → same delta, same run_id, full rewrite).

    Assertions:
    - Second ingest produces the same run_id as the first.
    - Share file checksums match the first run byte-for-byte.
    """
    m1 = run_ingest(dry_run=False, paths=workspace, database_url=database_url)
    run_id = m1["run_id"]

    share_paths = [
        workspace.share / "customers" / "changes.jsonl",
        workspace.share / "cases" / "changes.jsonl",
    ]
    checksums_first = {p: file_checksum(p) for p in share_paths}

    workspace.checkpoint.unlink()
    (workspace.events / f"{run_id}.jsonl").unlink()
    for path in share_paths:
        path.unlink()

    m2 = run_ingest(dry_run=False, paths=workspace, database_url=database_url)
    assert m2["run_id"] == run_id

    checksums_second = {p: file_checksum(p) for p in share_paths}
    assert checksums_first == checksums_second


def test_share_artifact_unchanged_on_recovery(fresh_db, workspace, database_url):
    """Recovery path must not rewrite share when outputs already exist.

    Setup:
    - fresh_db + full ingest.

    Action:
    - Record raw bytes of share files.
    - Delete checkpoint only (lake/share/events remain).
    - Ingest again via recovery (same run_id, no share rewrite).

    Assertions:
    - Share files are byte-for-byte identical to before recovery ingest.
    """
    run_ingest(dry_run=False, paths=workspace, database_url=database_url)

    share_paths = [
        workspace.share / "customers" / "changes.jsonl",
        workspace.share / "cases" / "changes.jsonl",
    ]
    bytes_before = {p: p.read_bytes() for p in share_paths}

    workspace.checkpoint.unlink()
    run_ingest(dry_run=False, paths=workspace, database_url=database_url)

    for path in share_paths:
        assert path.read_bytes() == bytes_before[path]
