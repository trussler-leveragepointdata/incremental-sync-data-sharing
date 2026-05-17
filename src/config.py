"""Runtime configuration and path layout."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DATABASE_URL = "postgresql://interop:interop@localhost:5432/interop"
PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Paths:
    root: Path
    state: Path
    lake: Path
    share: Path
    events: Path
    tmp: Path

    @property
    def checkpoint(self) -> Path:
        return self.state / "checkpoint.json"

    def run_staging(self, run_id: str) -> Path:
        return self.tmp / "runs" / run_id


def get_database_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)


def get_paths(root: Path | None = None) -> Paths:
    base = root or PROJECT_ROOT
    return Paths(
        root=base,
        state=base / "state",
        lake=base / "lake",
        share=base / "share",
        events=base / "events",
        tmp=base / "tmp",
    )
