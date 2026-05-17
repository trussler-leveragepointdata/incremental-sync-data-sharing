"""Pytest fixtures."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

from src.config import DEFAULT_DATABASE_URL, get_paths
from src.main import app

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CHANGES_SQL = PROJECT_ROOT / "db" / "changes.sql"


def postgres_available(url: str = DEFAULT_DATABASE_URL) -> bool:
    try:
        with psycopg.connect(url, connect_timeout=2) as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def database_url() -> str:
    url = DEFAULT_DATABASE_URL
    if not postgres_available(url):
        pytest.skip("Postgres not available at " + url)
    return url


@pytest.fixture
def workspace(tmp_path: Path, database_url: str, monkeypatch: pytest.MonkeyPatch):
    """Isolated output dirs; DB is shared (reset checkpoint between tests)."""
    for name in ("state", "lake", "share", "events", "tmp"):
        (tmp_path / name).mkdir()
    paths = get_paths(tmp_path)
    monkeypatch.setattr("src.ingest.get_paths", lambda: paths)
    monkeypatch.setattr("src.config.PROJECT_ROOT", tmp_path)
    yield paths
    checkpoint = paths.checkpoint
    if checkpoint.exists():
        checkpoint.unlink()


@pytest.fixture
def client(workspace) -> TestClient:
    return TestClient(app)


def reset_database(database_url: str) -> None:
    """Truncate tables and re-seed from init.sql data via full reload."""
    subprocess.run(
        ["docker", "compose", "down", "-v"],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
    )
    subprocess.run(
        ["docker", "compose", "up", "-d"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
    )
    import time

    for _ in range(30):
        if postgres_available(database_url):
            with psycopg.connect(database_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT COUNT(*) FROM information_schema.tables "
                        "WHERE table_name = 'customers'"
                    )
                    if cur.fetchone()[0]:
                        conn.commit()
                        return
        time.sleep(1)
    raise RuntimeError("Postgres did not become ready")


@pytest.fixture
def fresh_db(database_url: str, workspace):
    reset_database(database_url)
    yield


def apply_changes_sql(database_url: str) -> None:
    sql = CHANGES_SQL.read_text(encoding="utf-8")
    with psycopg.connect(database_url) as conn:
        conn.execute(sql)
        conn.commit()


def file_checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            lines.append(json.loads(line))
    return lines
