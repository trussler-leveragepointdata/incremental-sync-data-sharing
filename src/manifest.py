"""Manifest construction for /ingest responses."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.checkpoint import Watermark, checkpoint_to_jsonable, format_ts
from src.config import Paths


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def lake_path_for_date(paths: Paths, table: str, date_str: str) -> str:
    rel = paths.lake / table / f"date={date_str}" / "data.jsonl"
    return f"./{rel.relative_to(paths.root).as_posix()}"


def share_path_for_table(paths: Paths, table: str) -> str:
    rel = paths.share / table / "changes.jsonl"
    return f"./{rel.relative_to(paths.root).as_posix()}"


def lake_paths_for_rows(paths: Paths, table: str, rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return []
    dates = sorted({row["updated_at"][:10] for row in rows})
    return [lake_path_for_date(paths, table, d) for d in dates]


def build_table_manifest(
    paths: Paths,
    table: str,
    rows: list[dict[str, Any]],
    schema_fingerprint: str,
) -> dict[str, Any]:
    count = len(rows)
    return {
        "delta_row_count": count,
        "lake_paths": lake_paths_for_rows(paths, table, rows) if count else [],
        "share_path": share_path_for_table(paths, table) if count else None,
        "schema_fingerprint": schema_fingerprint,
    }


def build_manifest(
    *,
    run_id: str,
    started_at: datetime,
    finished_at: datetime,
    dry_run: bool,
    checkpoint_before: dict[str, Watermark | None],
    checkpoint_after: dict[str, Watermark | None],
    paths: Paths,
    deltas: dict[str, list[dict[str, Any]]],
    fingerprints: dict[str, str],
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "started_at": format_ts(started_at),
        "finished_at": format_ts(finished_at),
        "dry_run": dry_run,
        "checkpoint_before": checkpoint_to_jsonable(checkpoint_before),
        "checkpoint_after": checkpoint_to_jsonable(checkpoint_after),
        "tables": {
            table: build_table_manifest(
                paths, table, deltas[table], fingerprints[table]
            )
            for table in sorted(deltas.keys())
        },
    }
