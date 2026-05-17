# Incremental Sync + Data Sharing — Development Plan

**Source of truth:** [`spec/planning-implementation-prompt.txt`](../spec/planning-implementation-prompt.txt)  
**Reference:** [`spec/incremental-sync-data-sharing.pdf`](../spec/incremental-sync-data-sharing.pdf) (requirements align with the TXT prompt; PDF is not machine-readable here, so TXT governs implementation)

**Status:** Plan only — no implementation until explicitly approved.

---

## Implementation todos

- [ ] **foundation** — Add `docker-compose.yml`, `db/init.sql` (schema + deterministic seed), `db/changes.sql`, project skeleton and `.gitignore`
- [ ] **core-modules** — Implement `checkpoint.py`, `database.py`, `run_id.py`, `schema.py` with composite watermark queries
- [ ] **writers-ingest** — Implement `writers.py`, `manifest.py`, `ingest.py` with staged `tmp/runs` commit and checkpoint-last atomic write
- [ ] **api** — Implement FastAPI `POST /ingest?dry_run` in `src/main.py` with recovery path for existing `run_id` outputs
- [ ] **tests** — Implement all 9 pytest scenarios (initial, incremental, noop, dry-run, ties, run_id, share/event structure, failure safety)
- [ ] **docs** — Write `README.md` and optional `AI_USAGE.md`, `ARCHITECTURE_AWS.md`, `EXECUTION_PLAN.md`
- [ ] **smoke-verify** — Manual smoke: compose up, initial ingest, apply `changes.sql`, incremental + noop ingest

---

## 1. What we are building

A local prototype service that:

1. Incrementally reads changed rows from Postgres (`customers`, `cases`)
2. Appends CDC-style rows to date-partitioned lake JSONL files
3. Produces per-table consumer share artifacts (`./share/{table}/changes.jsonl`)
4. Writes durable per-run event files (`./events/<run_id>.jsonl`)
5. Maintains a composite per-table checkpoint at `./state/checkpoint.json` (`updated_at` + `last_pk`)
6. Exposes `POST /ingest?dry_run=true|false` with full manifest and staged, checkpoint-last crash safety

```mermaid
flowchart LR
  subgraph source [Source]
    PG[(Postgres 16)]
  end
  subgraph service [Ingest Service]
    API["POST /ingest"]
    CP[checkpoint.json]
    RID[run_id SHA-256]
    STG["tmp/runs/run_id"]
  end
  subgraph outputs [Durable Outputs]
    LAKE["lake/table/date=.../data.jsonl"]
    SHARE["share/table/changes.jsonl"]
    EVT["events/run_id.jsonl"]
  end
  PG --> API
  CP --> API
  API --> RID
  API --> STG
  STG --> LAKE
  STG --> SHARE
  STG --> EVT
  STG --> CP
```

---

## 2. Technology choices

| Area | Choice | Rationale |
|------|--------|-----------|
| Language | Python 3.11+ | Spec preference |
| HTTP | FastAPI + uvicorn | Spec preference |
| DB driver | `psycopg` (v3) or `asyncpg` with sync wrapper | Simple incremental queries |
| Tests | pytest + httpx TestClient | Integration-style against real Postgres in Docker |
| Config | Env var `DATABASE_URL` defaulting to `postgresql://interop:interop@localhost:5432/interop` | Spec contract |

No AWS, Kafka, Airflow, or Debezium in the implementation (optional docs only).

---

## 3. Repository layout

```
docker-compose.yml
db/init.sql
db/changes.sql
README.md
requirements.txt          # or pyproject.toml
src/
  main.py                 # FastAPI app, /ingest route
  ingest.py               # orchestration pipeline
  database.py             # connection + incremental queries
  checkpoint.py           # load/save/atomic replace + watermark math
  run_id.py               # canonical JSON + SHA-256
  schema.py               # schema fingerprint per table
  writers.py              # lake, share, event staging + promotion
  manifest.py             # manifest assembly
tests/
  conftest.py             # docker DB fixtures, temp dirs
  test_initial_ingest.py
  test_incremental.py
  test_noop.py
  test_dry_run.py
  test_watermark_ties.py
  test_run_id.py
  test_artifacts.py
  test_failure_safety.py
state/   lake/   share/   events/   tmp/   # runtime; .gitignore
```

Optional (if time permits): `AI_USAGE.md`, `ARCHITECTURE_AWS.md`, `EXECUTION_PLAN.md`.

---

## 4. Database layer

### 4.1 Docker Compose (`docker-compose.yml`)

Exact contract:

- Image: `postgres:16`
- Port: `5432`
- `POSTGRES_DB=interop`, `POSTGRES_USER=interop`, `POSTGRES_PASSWORD=interop`
- Mount `db/init.sql` into `/docker-entrypoint-initdb.d/`

### 4.2 Schema (`db/init.sql`)

Exact tables, columns, types, and indexes per spec (lines 75–96 of prompt).

### 4.3 Seed data (`db/init.sql`)

- Fixed anchor timestamp literal (e.g. `TIMESTAMPTZ '2026-03-01T00:00:00Z'`)
- Derive all `updated_at` via `anchor + interval` — no randomness
- ≥30 customers, ≥200 cases
- `updated_at` spans 30-day window
- Case titles/descriptions include keywords: billing, audit, compliance, payments, reconciliation, onboarding, fraud, AML

### 4.4 Change script (`db/changes.sql`)

Fixed timestamp **later than** all seed timestamps:

- Update exactly 5 existing cases (status + `updated_at`)
- Insert exactly 2 new customers
- Insert exactly 10 new cases (mix of existing + new customers)

**Post-change expected deltas:** customers `2`, cases `15` (2 new customers + 5 updates + 10 inserts).

---

## 5. Core ingestion logic

### 5.1 Composite watermark query (`src/database.py`)

Per table `T` with PK `pk`:

```sql
SELECT * FROM T
WHERE updated_at > :wm_at
   OR (updated_at = :wm_at AND pk > :wm_pk)
ORDER BY updated_at ASC, pk ASC
```

- **Initial run** (no checkpoint / null watermark): `SELECT * FROM T ORDER BY updated_at ASC, pk ASC` (all rows)
- **Assumption (document in README):** source data is stable for the duration of a single `/ingest` request

### 5.2 Checkpoint (`src/checkpoint.py`)

- Path: `./state/checkpoint.json`
- Shape: per-table `{ "updated_at": ISO-8601 Z, "last_pk": int }`
- `checkpoint_after` = watermark of **last processed row** in deterministic order; if zero rows for a table, copy `checkpoint_before` for that table
- Atomic write: `checkpoint.json.tmp` → flush → `os.replace` → `checkpoint.json`
- **Never advance checkpoint before durable outputs are committed**

### 5.3 Deterministic `run_id` (`src/run_id.py`)

1. Build canonical JSON: `{ "checkpoint_before": ..., "tables": { "customers": [...identities], "cases": [...] } }`
2. Each identity: `{ "table", "pk", "updated_at" }` in query order
3. `json.dumps(..., sort_keys=True, separators=(",", ":"))`
4. `run_id = sha256(hex digest)` — no UUIDs, no wall-clock

### 5.4 Schema fingerprint (`src/schema.py`)

Query `information_schema.columns` (or hardcode from spec) → stable hash of `(column_name, data_type)` ordered by ordinal position.

---

## 6. `/ingest` pipeline (`src/ingest.py`)

Shared steps for **both** dry-run and non-dry-run:

1. `started_at` (UTC ISO-8601; used only in manifest, not in `run_id`)
2. Load `checkpoint_before` (or `null` per table if missing)
3. Fetch deltas for `customers` and `cases`
4. Compute `checkpoint_after` per table
5. Compute `run_id`
6. Build manifest (paths predicted even for dry-run)

### 6.1 Dry run (`dry_run=true`)

- Return manifest with `checkpoint_before`, predicted `checkpoint_after`, `lake_paths`, `share_path`, `schema_fingerprint`
- **Write nothing** — no lake, share, events, checkpoint changes

### 6.2 Non-dry run (`dry_run=false`)

**Staged commit** under `./tmp/runs/<run_id>/`:

| Step | Action |
|------|--------|
| 1 | If recovery applies (see §6.3), skip rewrites and only advance checkpoint |
| 2 | Group delta rows by UTC date → stage lake JSONL per `lake/{table}/date=YYYY-MM-DD/data.jsonl` |
| 3 | If `delta_row_count > 0`, stage `share/{table}/changes.jsonl` (full batch, ordered, `op: upsert`) |
| 4 | Stage `events/{run_id}.jsonl` — **two lines** (customers + cases); zero-delta table: `delta_row_count=0`, `share_path=null` |
| 5 | Validate staged JSONL (parse each line) |
| 6 | **Promote:** append lake partitions; replace share files; move event file to `./events/<run_id>.jsonl` |
| 7 | Print events to stdout (best-effort, not crash boundary) |
| 8 | **Last:** atomic checkpoint write |

On failure before step 8: leave checkpoint unchanged; clean up `tmp/runs/<run_id>/`.

### 6.3 Checkpoint-failure recovery (recommended)

If `./events/<run_id>.jsonl` exists and referenced lake/share paths exist for the same `run_id` recomputed from current `checkpoint_before` + DB state:

- Treat outputs as already materialized
- Advance checkpoint to `checkpoint_after` without rewriting lake/share

Document behavior in README; tests must at minimum prove checkpoint never advances ahead of outputs.

### 6.4 Lake writer

- Append-only JSONL per partition; one JSON object per line (row payload)
- Multiple dates in one run → multiple `lake_paths`
- No-op run (`delta_row_count=0`) → no lake writes, `lake_paths=[]`

### 6.5 Share writer

Each line includes: `table`, `op`, PK field, `updated_at`, `run_id`, `schema_fingerprint`, `checkpoint_after`, `record`

- Replace `./share/{table}/changes.jsonl` per successful batch with deltas
- Zero-delta: do **not** touch existing share file; manifest `share_path=null`

### 6.6 Manifest (`src/manifest.py`)

Required fields per spec: `run_id`, `started_at`, `finished_at`, `dry_run`, `checkpoint_before`, `checkpoint_after`, per-table `delta_row_count`, `lake_paths`, `share_path`, `schema_fingerprint`.

---

## 7. HTTP service (`src/main.py`)

- `POST /ingest?dry_run: bool = False`
- Return manifest JSON; HTTP 500 on unrecoverable failure
- Optional health route for tests: `GET /health`

---

## 8. Test plan (pytest)

Use TestClient against FastAPI with:

- Ephemeral output dirs via `tmp_path` monkeypatch (override paths in config)
- Postgres from `docker compose` (session-scoped) or testcontainers

| # | Test | Key assertions |
|---|------|----------------|
| 1 | Initial ingest | ≥30 customers, ≥200 cases ingested; checkpoint created; lake/share/event exist |
| 2 | After `changes.sql` | `delta_row_count`: customers=2, cases=15 |
| 3 | No-op third ingest | Both tables `delta_row_count=0`, `lake_paths=[]`, `share_path=null`; no duplicate lake/share bytes |
| 4 | Dry run | Manifest has predicted `checkpoint_after`; checkpoint + file checksums unchanged |
| 5 | Timestamp ties | Seed or insert rows with same `updated_at`; verify order + composite checkpoint does not skip PKs |
| 6 | Deterministic `run_id` | Same DB + checkpoint → identical `run_id`; pattern matches hex SHA-256, not UUID |
| 7 | Share structure | Required fields on every JSONL line |
| 8 | Event structure | `./events/<run_id>.jsonl` has 2 lines; zero-delta fields correct |
| 9 | Failure safety | Inject exception / read-only dir before checkpoint write → ingest fails, checkpoint unchanged |

---

## 9. Documentation deliverables

### Required: `README.md`

Sections per spec: Overview, Deliverables, DB contract, Running locally, `/ingest`, checkpointing, dry-run, outputs, manifest, crash consistency, replay/idempotency, schema evolution, testing, assumptions.

Include commands:

```bash
docker compose up -d
uvicorn src.main:app --reload
curl -X POST "http://localhost:8000/ingest?dry_run=false"
curl -X POST "http://localhost:8000/ingest?dry_run=true"
docker exec -i <container> psql -U interop -d interop < db/changes.sql
pytest
```

### Optional (post-core)

- `AI_USAGE.md` — tools, prompts, manual verification, guardrails
- `ARCHITECTURE_AWS.md` — ≤1 page, production CDC → lake → consumer API (no implementation)
- `EXECUTION_PLAN.md` — ≤1 page, 2–3 sprint delivery plan

---

## 10. Implementation sequence (after approval)

```mermaid
flowchart TD
  A[docker-compose + db/init.sql + db/changes.sql] --> B[Core modules: checkpoint, database, run_id, schema]
  B --> C[Writers + ingest orchestration]
  C --> D[FastAPI /ingest endpoint]
  D --> E[pytest suite - all 9 scenarios]
  E --> F[README + optional docs]
  F --> G[Manual smoke: compose up, 3 ingest runs with changes.sql]
```

**Estimated phases:**

1. **Foundation** (~2–3h): Compose, SQL scripts, project skeleton, `.gitignore` for runtime dirs
2. **Core engine** (~4–5h): Queries, checkpoint, run_id, staged writers, manifest
3. **API + recovery** (~2h): FastAPI route, idempotent recovery path
4. **Tests** (~3–4h): All 9 required test categories
5. **Docs + polish** (~2h): README, optional AWS/execution/AI docs, manual verification

---

## 11. Acceptance checklist (from spec)

All 16 acceptance criteria in the prompt (lines 1019–1036) must pass before calling the project complete — especially:

- Composite checkpoint (`updated_at` + `last_pk`)
- Checkpoint written **last**
- Dry-run writes nothing
- Deterministic `run_id` and share artifact byte identity
- No-op runs produce no lake/share duplicates

---

## 12. Explicit non-goals

- Multi-file filesystem transactions
- Cross-table transactional consistency beyond “stable DB during ingest”
- Cloud infrastructure implementation
- DELETE operations in share artifacts (`op` is `upsert` only)

---

**Next step:** Reply with approval (or edits). Implementation will not start until you confirm.
