"""Shared pytest fixtures and helpers for integration tests.

How tests run:
- Postgres must be reachable at DATABASE_URL (default: local Docker Compose).
- `fresh_db` recreates the database volume so each test gets seed data from db/init.sql.
- `workspace` redirects lake/share/events/state/tmp to a per-test temp directory so runs
  do not collide on disk.
- HTTP tests use FastAPI TestClient; direct pipeline tests call run_ingest().
"""

from __future__ import annotations

import hashlib
import json
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
    """Return True when Postgres accepts a connection (used to skip tests if DB is down)."""
    try:
        with psycopg.connect(url, connect_timeout=2) as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def database_url() -> str:
    """Session-scoped connection string; skips the suite if Postgres is unavailable."""
    url = DEFAULT_DATABASE_URL
    if not postgres_available(url):
        pytest.skip("Postgres not available at " + url)
    return url


@pytest.fixture
def workspace(tmp_path: Path, database_url: str, monkeypatch: pytest.MonkeyPatch):
    """Isolate filesystem outputs under pytest's tmp_path for each test.

    Patches get_paths() so ingest writes under tmp_path instead of the repo root.
    Removes checkpoint.json after the test so the next test does not inherit watermarks.
    """
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
    """HTTP client for POST /ingest against the FastAPI app."""
    return TestClient(app)


def reset_database(database_url: str) -> None:
    """Recreate Postgres from scratch so db/init.sql runs again (deterministic seed)."""
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
    """Empty checkpoint + freshly seeded tables before each test that needs a clean DB."""
    reset_database(database_url)
    yield


def apply_changes_sql(database_url: str) -> None:
    """Apply db/changes.sql (5 case updates, 2 customers, 10 cases) for incremental tests."""
    sql = CHANGES_SQL.read_text(encoding="utf-8")
    with psycopg.connect(database_url) as conn:
        conn.execute(sql)
        conn.commit()


def file_checksum(path: Path) -> str:
    """SHA-256 of file bytes — used to detect unexpected lake/share rewrites."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    """Parse a JSONL file into a list of objects (one per non-empty line)."""
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            lines.append(json.loads(line))
    return lines
