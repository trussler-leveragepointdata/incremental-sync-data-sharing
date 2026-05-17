# Incremental Sync + Data Sharing Prototype

## Overview

This repository is a **local prototype** of an incremental data-sharing service. It reads changed `customers` and `cases` rows from Postgres, appends them to date-partitioned lake JSONL files, produces consumer-facing share artifacts, writes durable per-run event files, and maintains a composite ingestion checkpoint so rows are not skipped or duplicated when timestamps tie or a run fails partway through.

The service exposes a single HTTP endpoint:

`POST /ingest?dry_run=true|false`

**Stack:** Python 3.11+, FastAPI, psycopg3, Postgres 16 (Docker), pytest.

## Project Deliverables

| Deliverable | Location |
|-------------|----------|
| Database schema + deterministic seed | `db/init.sql` |
| Deterministic change script (2nd ingest) | `db/changes.sql` |
| Docker Compose (Postgres 16) | `docker-compose.yml` |
| Ingest service | `src/` |
| Tests (9 required scenarios) | `tests/` |
| Runtime outputs (created on ingest) | `state/`, `lake/`, `share/`, `events/`, `tmp/` |

## Database Contract

Docker Compose starts Postgres with:

| Setting | Value |
|---------|--------|
| Image | `postgres:16` |
| Port | `5432` |
| Database | `interop` |
| User / password | `interop` / `interop` |

Connection URL:

```text
postgresql://interop:interop@localhost:5432/interop
```

Override with `DATABASE_URL` if needed.

**Tables:** `customers` (`customer_id`, `name`, `email`, `country`, `updated_at`) and `cases` (`case_id`, `customer_id`, `title`, `description`, `status`, `updated_at`), with indexes on `updated_at` and `cases.customer_id`.

**Seed data (`db/init.sql`):** 32 customers and 210 cases, deterministic `updated_at` values from a fixed anchor over a 30-day window (no randomness).

**Changes (`db/changes.sql`):** 5 case updates, 2 new customers, 10 new cases at `2026-04-01T12:00:00Z` — expected second-ingest deltas: **customers = 2**, **cases = 15**.

## Running Locally

### Prerequisites

- Docker and Docker Compose
- Python 3.11+
- `pip install -r requirements.txt`

### Start Postgres

```bash
docker compose up -d
```

Wait until the database accepts connections. On first start, `db/init.sql` runs automatically.

### Start the service

From the repository root:

```bash
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

Health check:

```bash
curl http://localhost:8000/health
```

### Typical workflow

```bash
# 1. Initial ingest (full seed load)
curl -s -X POST "http://localhost:8000/ingest?dry_run=false" | jq .

# 2. Apply incremental changes
docker exec -i $(docker compose ps -q postgres) psql -U interop -d interop < db/changes.sql

# 3. Incremental ingest
curl -s -X POST "http://localhost:8000/ingest?dry_run=false" | jq .

# 4. No-op ingest (no DB changes)
curl -s -X POST "http://localhost:8000/ingest?dry_run=false" | jq .

# 5. Dry run (manifest only, no writes)
curl -s -X POST "http://localhost:8000/ingest?dry_run=true" | jq .
```

### Run tests

Requires Postgres on `localhost:5432` (tests reset the DB via `docker compose down -v` / `up`):

```bash
pytest -v
```

## Ingest Endpoint

**`POST /ingest?dry_run=false`** (default)

- Reads incremental deltas for `customers` and `cases`
- Writes lake, share, and event artifacts (staged, then promoted)
- Advances `./state/checkpoint.json` **last**, only after durable outputs succeed

**`POST /ingest?dry_run=true`**

- Computes the same manifest (including predicted `checkpoint_after` and output paths)
- Writes **nothing** to disk (no lake, share, events, or checkpoint update)

Response body: JSON **manifest** (see below).

## Incremental Ingestion and Checkpointing

Checkpoint file: `./state/checkpoint.json`

Per-table composite watermark:

```json
{
  "customers": { "updated_at": "2026-03-31T12:00:00Z", "last_pk": 32 },
  "cases": { "updated_at": "2026-03-31T12:00:00Z", "last_pk": 210 }
}
```

- `last_pk` is `customer_id` or `case_id` respectively.
- Missing file ⇒ initial ingest (all rows).

**Incremental query** (per table):

```sql
WHERE updated_at > :checkpoint.updated_at
   OR (updated_at = :checkpoint.updated_at AND primary_key > :checkpoint.last_pk)
ORDER BY updated_at ASC, primary_key ASC
```

This avoids missing rows that share the same `updated_at`. After a successful batch, `checkpoint_after` is the watermark of the **last processed row**; if a table has zero new rows, its checkpoint is unchanged.

## Dry Run Behavior

Dry run returns `checkpoint_before` and predicted `checkpoint_after`, `lake_paths`, `share_path`, and `schema_fingerprint` per table. Paths are **predictions only** — no files are created or modified, and the on-disk checkpoint is unchanged.

## Output Files

### Lake (append-only CDC)

```text
./lake/customers/date=YYYY-MM-DD/data.jsonl
./lake/cases/date=YYYY-MM-DD/data.jsonl
```

`YYYY-MM-DD` is the UTC date of each row's `updated_at`. One JSON object per line (row payload). Appended per successful ingest; no writes on no-op runs.

**Example lake line (`cases`):**

```json
{"case_id":1,"customer_id":1,"title":"Billing review case #1","description":"Case related to billing for customer 1. Requires audit follow-up.","status":"in_progress","updated_at":"2026-03-01T00:00:00Z"}
```

### Share artifacts (latest incremental batch per table)

```text
./share/customers/changes.jsonl
./share/cases/changes.jsonl
```

Replaced on each successful ingest that has `delta_row_count > 0`. Not updated on no-op runs.

**Example share line (`cases`):**

```json
{
  "table": "cases",
  "op": "upsert",
  "case_id": 210,
  "updated_at": "2026-04-01T12:00:00Z",
  "run_id": "<64-char-sha256-hex>",
  "schema_fingerprint": "<hex>",
  "checkpoint_after": { "updated_at": "2026-04-01T12:00:00Z", "last_pk": 220 },
  "record": { "case_id": 210, "customer_id": 32, "title": "...", "description": "...", "status": "open", "updated_at": "2026-04-01T12:00:00Z" }
}
```

Records are ordered by `updated_at ASC`, primary key ASC. Given the same source data and checkpoint, share contents are deterministic (including `run_id`).

### Durable events

```text
./events/<run_id>.jsonl
```

Exactly **two lines** per run (`customers` and `cases`). Each line includes: `table`, `run_id`, `schema_fingerprint`, `delta_row_count`, `lake_paths`, `share_path`, `checkpoint_after`. Zero-delta tables still get an event line with `delta_row_count: 0` and `share_path: null`.

Events are also printed to stdout (best-effort; not part of crash consistency).

## Manifest

Example shape after incremental ingest:

```json
{
  "run_id": "<sha256-hex>",
  "started_at": "2026-04-01T12:00:01Z",
  "finished_at": "2026-04-01T12:00:02Z",
  "dry_run": false,
  "checkpoint_before": { "customers": { "updated_at": "...", "last_pk": 32 }, "cases": { "updated_at": "...", "last_pk": 210 } },
  "checkpoint_after": { "customers": { "updated_at": "2026-04-01T12:00:00Z", "last_pk": 34 }, "cases": { "updated_at": "2026-04-01T12:00:00Z", "last_pk": 220 } },
  "tables": {
    "customers": {
      "delta_row_count": 2,
      "lake_paths": ["./lake/customers/date=2026-04-01/data.jsonl"],
      "share_path": "./share/customers/changes.jsonl",
      "schema_fingerprint": "<hex>"
    },
    "cases": {
      "delta_row_count": 15,
      "lake_paths": ["./lake/cases/date=2026-04-01/data.jsonl"],
      "share_path": "./share/cases/changes.jsonl",
      "schema_fingerprint": "<hex>"
    }
  }
}
```

**`run_id`:** SHA-256 of canonical JSON containing `checkpoint_before` and ordered row identities (`table`, `primary_key`, `updated_at`). No UUIDs or wall-clock values.

## Crash Consistency Strategy

Ingest uses **staged writes** under `./tmp/runs/<run_id>/`, validates JSONL, then promotes to final paths. The checkpoint is written **last** via `checkpoint.json.tmp` → atomic rename.

**Crash boundary includes:** lake files, share files, `./events/<run_id>.jsonl`, `./state/checkpoint.json`.

**Not in the boundary:** stdout logging, HTTP response body.

The system does **not** advance the checkpoint ahead of durable outputs. If outputs are written but checkpoint write fails, the next run may re-select the same delta; if `./events/<run_id>.jsonl` and referenced outputs already exist for the same deterministic `run_id`, recovery advances the checkpoint without rewriting lake/share.

## Replay and Idempotency

- **`./state/checkpoint.json`** is a **producer-side ingestion checkpoint** — how far extraction from Postgres has been safely published. It is **not** a per-consumer cursor.
- Consumers needing independent replay should keep **their own offsets/cursors**.
- **`./lake/`** is the durable replay substrate (append-only history).
- **`./share/`** is the latest successful incremental batch per table for downstream sync.
- Deduplicate using **table**, **primary key**, **`updated_at`**, and **`run_id`**.
- In production, **source CDC offsets**, **lake commit state**, and **consumer cursors** should be separate.

No-op ingests (`delta_row_count = 0`) do not append to lake or replace share files.

## Schema Evolution

This prototype exposes a per-table **`schema_fingerprint`**: SHA-256 of ordered `(column_name, data_type)` metadata.

In production you would typically add:

- Versioned schemas and compatibility checks
- Additive changes by default, deprecation windows for breaking changes
- Consumer contract tests
- Lakehouse formats (e.g. Iceberg) for evolved table schemas

Manifests and share/event records carry the fingerprint so consumers can detect schema changes.

## Testing

```bash
pytest -v
```

Covers: initial ingest, incremental ingest after `changes.sql`, no-op ingest, dry run, timestamp-tie watermark, deterministic `run_id`, share/event structure, and checkpoint-not-advanced-on-failure.

## Assumptions and Limitations

1. **Stable source during ingest:** Postgres data does not change while a single `/ingest` request runs. No cross-table transactional snapshot beyond that.
2. **Local filesystem only:** No multi-file atomic transactions; checkpoint-last ordering prevents the dangerous case (checkpoint ahead of missing outputs).
3. **`op` is `upsert` only:** No delete events in share artifacts.
4. **Single process:** No distributed locking; suitable for local/demo use.
5. **Postgres 16 + fixed seed:** Reproducible demos; `docker compose down -v` resets data.

Optional docs (if present): `AI_USAGE.md`, `ARCHITECTURE_AWS.md`, `EXECUTION_PLAN.md`.
