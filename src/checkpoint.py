"""Checkpoint load/save with composite watermark per table."""

from __future__ import annotations

import json
import os
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TABLES = ("customers", "cases")
PK_FIELDS = {"customers": "customer_id", "cases": "case_id"}


@dataclass(frozen=True)
class Watermark:
    updated_at: datetime
    last_pk: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "updated_at": format_ts(self.updated_at),
            "last_pk": self.last_pk,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Watermark:
        return cls(
            updated_at=parse_ts(data["updated_at"]),
            last_pk=int(data["last_pk"]),
        )


def format_ts(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_ts(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    text = value.replace("Z", "+00:00")
    return datetime.fromisoformat(text).astimezone(timezone.utc)


def empty_checkpoint_state() -> dict[str, Watermark | None]:
    return {table: None for table in TABLES}


def load_checkpoint(path: Path) -> dict[str, Watermark | None]:
    if not path.exists():
        return empty_checkpoint_state()
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {
        table: Watermark.from_dict(raw[table]) if raw.get(table) else None
        for table in TABLES
    }


def checkpoint_to_jsonable(state: dict[str, Watermark | None]) -> dict[str, Any]:
    return {
        table: (wm.to_dict() if wm else None) for table, wm in state.items()
    }


def save_checkpoint(path: Path, state: dict[str, Watermark | None]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(checkpoint_to_jsonable(state), indent=2, sort_keys=True)
    payload += "\n"
    tmp_path = path.with_suffix(".json.tmp")
    with open(tmp_path, "w", encoding="utf-8") as fh:
        fh.write(payload)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp_path, path)


def watermark_from_row(row: dict[str, Any], table: str) -> Watermark:
    pk_field = PK_FIELDS[table]
    return Watermark(
        updated_at=parse_ts(row["updated_at"]),
        last_pk=int(row[pk_field]),
    )


def checkpoint_after_for_rows(
    rows: list[dict[str, Any]],
    table: str,
    checkpoint_before: Watermark | None,
) -> Watermark | None:
    if not rows:
        return deepcopy(checkpoint_before)
    return watermark_from_row(rows[-1], table)
