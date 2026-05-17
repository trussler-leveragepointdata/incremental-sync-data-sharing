"""Ingest orchestration pipeline."""

from __future__ import annotations

import json
import sys
from typing import Any, Callable

from src.checkpoint import (
    TABLES,
    Watermark,
    checkpoint_after_for_rows,
    format_ts,
    load_checkpoint,
    save_checkpoint,
)
from src.config import Paths, get_database_url, get_paths
from src.database import connect, fetch_delta
from src.manifest import build_manifest, utc_now
from src.run_id import compute_run_id
from src.schema import fingerprints_for_tables
from src.writers import (
    build_event_line,
    build_share_lines,
    cleanup_staging,
    outputs_materialized,
    promote_staged_run,
    stage_events_file,
    stage_lake_files,
    stage_share_file,
    validate_jsonl_file,
)


class IngestError(Exception):
    pass


class CheckpointWriteBlocked(IngestError):
    """Raised when a test hook blocks checkpoint write."""


def run_ingest(
    *,
    dry_run: bool,
    paths: Paths | None = None,
    database_url: str | None = None,
    before_checkpoint_write: Callable[[], None] | None = None,
) -> dict[str, Any]:
    paths = paths or get_paths()
    database_url = database_url or get_database_url()
    started_at = utc_now()

    checkpoint_before = load_checkpoint(paths.checkpoint)
    deltas: dict[str, list[dict[str, Any]]] = {}

    with connect(database_url) as conn:
        for table in TABLES:
            deltas[table] = fetch_delta(conn, table, checkpoint_before[table])

    checkpoint_after: dict[str, Watermark | None] = {
        table: checkpoint_after_for_rows(
            deltas[table], table, checkpoint_before[table]
        )
        for table in TABLES
    }

    run_id = compute_run_id(checkpoint_before, deltas)
    fingerprints = fingerprints_for_tables(TABLES, database_url)

    if dry_run:
        return build_manifest(
            run_id=run_id,
            started_at=started_at,
            finished_at=utc_now(),
            dry_run=True,
            checkpoint_before=checkpoint_before,
            checkpoint_after=checkpoint_after,
            paths=paths,
            deltas=deltas,
            fingerprints=fingerprints,
        )

    manifest = build_manifest(
        run_id=run_id,
        started_at=started_at,
        finished_at=utc_now(),
        dry_run=False,
        checkpoint_before=checkpoint_before,
        checkpoint_after=checkpoint_after,
        paths=paths,
        deltas=deltas,
        fingerprints=fingerprints,
    )

    staging = paths.run_staging(run_id)
    cleanup_staging(staging)
    staging.mkdir(parents=True, exist_ok=True)

    try:
        if outputs_materialized(paths, run_id, manifest["tables"]):
            if before_checkpoint_write:
                before_checkpoint_write()
            save_checkpoint(paths.checkpoint, checkpoint_after)
            manifest["finished_at"] = format_ts(utc_now())
            return manifest

        for table in TABLES:
            rows = deltas[table]
            stage_lake_files(staging, paths, table, rows)
            share_lines = build_share_lines(
                table,
                rows,
                run_id=run_id,
                schema_fingerprint=fingerprints[table],
                checkpoint_after=checkpoint_after[table],
            )
            stage_share_file(staging, paths, table, share_lines)

        event_lines = []
        for table in TABLES:
            table_manifest = manifest["tables"][table]
            event_lines.append(
                build_event_line(
                    table,
                    run_id=run_id,
                    schema_fingerprint=fingerprints[table],
                    delta_row_count=table_manifest["delta_row_count"],
                    lake_paths=table_manifest["lake_paths"],
                    share_path=table_manifest["share_path"],
                    checkpoint_after=checkpoint_after[table],
                )
            )

        stage_events_file(staging, paths, run_id, event_lines)
        for staged in staging.rglob("*.jsonl"):
            validate_jsonl_file(staged)

        promote_staged_run(staging, paths)

        for line in event_lines:
            print(json.dumps(line, sort_keys=True), file=sys.stdout)

        if before_checkpoint_write:
            before_checkpoint_write()

        save_checkpoint(paths.checkpoint, checkpoint_after)
        cleanup_staging(staging)
    except Exception:
        cleanup_staging(staging)
        raise

    manifest["finished_at"] = format_ts(utc_now())
    return manifest
