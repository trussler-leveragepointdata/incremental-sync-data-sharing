"""Deterministic run_id from checkpoint and ordered row identities."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from src.checkpoint import PK_FIELDS, Watermark, checkpoint_to_jsonable


def row_identity(table: str, row: dict[str, Any]) -> dict[str, Any]:
    pk_field = PK_FIELDS[table]
    return {
        "table": table,
        "primary_key": int(row[pk_field]),
        "updated_at": row["updated_at"],
    }


def compute_run_id(
    checkpoint_before: dict[str, Watermark | None],
    deltas: dict[str, list[dict[str, Any]]],
) -> str:
    payload = {
        "checkpoint_before": checkpoint_to_jsonable(checkpoint_before),
        "tables": {
            table: [row_identity(table, row) for row in deltas[table]]
            for table in sorted(deltas.keys())
        },
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
