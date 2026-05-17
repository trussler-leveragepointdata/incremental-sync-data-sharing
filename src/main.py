"""FastAPI application."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query

from src.ingest import CheckpointWriteBlocked, IngestError, run_ingest

app = FastAPI(title="Incremental Sync + Data Sharing")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/ingest")
def ingest(dry_run: bool = Query(default=False)) -> dict:
    try:
        return run_ingest(dry_run=dry_run)
    except (IngestError, CheckpointWriteBlocked) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
