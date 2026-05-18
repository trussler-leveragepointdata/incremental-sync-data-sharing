"""Lake, share, and event writers with staging and promotion."""

from __future__ import annotations

import json
import os
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any

from src.checkpoint import PK_FIELDS, Watermark, checkpoint_to_jsonable
from src.config import Paths
from src.manifest import lake_path_for_date, share_path_for_table


def dumps_stable(obj: dict[str, Any]) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def write_jsonl(path: Path, lines: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "".join(dumps_stable(line) + "\n" for line in lines)
    path.write_text(content, encoding="utf-8")


def validate_jsonl_file(path: Path) -> None:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            json.loads(line)


def stage_lake_files(
    staging: Path,
    paths: Paths,
    table: str,
    rows: list[dict[str, Any]],
) -> list[Path]:
    if not rows:
        return []
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_date[row["updated_at"][:10]].append(row)
    staged: list[Path] = []
    for date_str, batch in sorted(by_date.items()):
        rel = paths.lake / table / f"date={date_str}" / "data.jsonl"
        stage_path = staging / rel.relative_to(paths.root)
        write_jsonl(stage_path, batch)
        staged.append(stage_path)
    return staged


def build_share_lines(
    table: str,
    rows: list[dict[str, Any]],
    *,
    run_id: str,
    schema_fingerprint: str,
    checkpoint_after: Watermark | None,
) -> list[dict[str, Any]]:
    pk_field = PK_FIELDS[table]
    cp_after = checkpoint_after.to_dict() if checkpoint_after else None
    lines = []
    for row in rows:
        lines.append(
            {
                "table": table,
                "op": "upsert",
                pk_field: row[pk_field],
                "updated_at": row["updated_at"],
                "run_id": run_id,
                "schema_fingerprint": schema_fingerprint,
                "checkpoint_after": cp_after,
                "record": row,
            }
        )
    return lines


def stage_share_file(
    staging: Path,
    paths: Paths,
    table: str,
    lines: list[dict[str, Any]],
) -> Path | None:
    if not lines:
        return None
    rel = paths.share / table / "changes.jsonl"
    stage_path = staging / rel.relative_to(paths.root)
    write_jsonl(stage_path, lines)
    return stage_path


def build_event_line(
    table: str,
    *,
    run_id: str,
    schema_fingerprint: str,
    delta_row_count: int,
    lake_paths: list[str],
    share_path: str | None,
    checkpoint_after: Watermark | None,
) -> dict[str, Any]:
    return {
        "table": table,
        "run_id": run_id,
        "schema_fingerprint": schema_fingerprint,
        "delta_row_count": delta_row_count,
        "lake_paths": lake_paths,
        "share_path": share_path,
        "checkpoint_after": (
            checkpoint_after.to_dict() if checkpoint_after else None
        ),
    }


def stage_events_file(
    staging: Path,
    paths: Paths,
    run_id: str,
    event_lines: list[dict[str, Any]],
) -> Path:
    rel = paths.events / f"{run_id}.jsonl"
    stage_path = staging / rel.relative_to(paths.root)
    write_jsonl(stage_path, event_lines)
    return stage_path


def append_file(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    data = src.read_text(encoding="utf-8")
    if dest.exists():
        existing = dest.read_text(encoding="utf-8")
        if existing and not existing.endswith("\n"):
            existing += "\n"
        dest.write_text(existing + data, encoding="utf-8")
    else:
        dest.write_text(data, encoding="utf-8")


def replace_file_atomic(src: Path, dest: Path) -> None:
    """Write staged content to dest via a temp file and atomic rename."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = dest.with_name(dest.name + ".tmp")
    shutil.copy2(src, tmp_path)
    os.replace(tmp_path, dest)


def promote_staged_run(staging: Path, paths: Paths) -> None:
    if not staging.exists():
        return
    for src in staging.rglob("*"):
        if not src.is_file():
            continue
        rel = src.relative_to(staging)
        dest = paths.root / rel
        if "lake/" in rel.as_posix() and dest.exists():
            append_file(src, dest)
        else:
            replace_file_atomic(src, dest)


def outputs_materialized(
    paths: Paths,
    run_id: str,
    manifest_tables: dict[str, Any],
) -> bool:
    event_path = paths.events / f"{run_id}.jsonl"
    if not event_path.exists():
        return False
    for table_info in manifest_tables.values():
        for lake_path in table_info.get("lake_paths", []):
            if not (paths.root / lake_path.removeprefix("./")).exists():
                return False
        share_path = table_info.get("share_path")
        if share_path and not (paths.root / share_path.removeprefix("./")).exists():
            return False
    return True


def cleanup_staging(staging: Path) -> None:
    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
