# AI Usage

How AI was used to design, build, and verify the incremental sync prototype.

## Tools / agents used

| Agent / tool | Purpose |
|--------------|---------|
| **ChatGPT 5.5** | Walk through the take-home spec section by section; produce [`planning/development-plan.md`](planning/development-plan.md); draft the Cursor execution prompt in [`spec/planning-implementation-prompt.txt`](spec/planning-implementation-prompt.txt) |
| **Cursor** (Composer / agent mode) | End-to-end implementation, tests, README, optional docs, smoke script, gap analysis, and spec-alignment review |
| **Human review** | Final judgment on safety-critical behavior (checkpoint-last, SQL counts, test meaning vs spec) |

**Reference materials:** [`spec/incremental-sync-data-sharing.pdf`](spec/incremental-sync-data-sharing.pdf) (original take-home); [`spec/planning-implementation-prompt.txt`](spec/planning-implementation-prompt.txt) (behavioral source of truth in this repo).

---

## Key prompts or transcript excerpts

### ChatGPT 5.5 — understand the spec before coding

I pasted each major section of the PDF and asked for expansion: implied contracts, failure modes, and what “correct” looks like. Representative questions:

> For the failure-safety requirement: walk through what must happen if the process crashes after lake/share/events are written but before `checkpoint.json` is updated. Should we stage under `tmp/runs/<run_id>/` and only update the checkpoint last?

> Explain timestamp ties: why is `updated_at` alone insufficient, and how does `last_pk` prevent skipped rows?

> What is the difference between the lake (append-only history), the share artifact (latest batch), and the durable event file?

I used these sessions to nail the **pillars** (incremental ingestion, deterministic ordering, replay safety, crash-consistent storage) before writing code.

### ChatGPT 5.5 — plan and execution prompt

> Based on our discussion of the full spec, produce a development and implementation plan with modules, data flow, checkpoint logic, test scenarios, and acceptance criteria.

→ Output captured in [`planning/development-plan.md`](planning/development-plan.md).

> Turn the spec and plan into one prompt I can give Cursor: design first, then implement; do not weaken composite checkpointing, dry-run, or checkpoint-last semantics.

→ Output captured in [`spec/planning-implementation-prompt.txt`](spec/planning-implementation-prompt.txt).

### Cursor — implementation

> Implement the plan as specified. Do not edit the plan file. Use Python/FastAPI, composite checkpointing, deterministic `run_id`, staged writes with checkpoint last.

Follow-up prompts in the same project included: gap analysis vs spec, optional docs (`ARCHITECTURE_AWS.md`, `EXECUTION_PLAN.md`), share byte-identical tests, `scripts/smoke_verify.sh`, `information_schema` schema fingerprint, deeper failure-safety tests, and section-by-section spec evaluation for documentation.

**Guardrails I stated explicitly to agents:**

- Specification is the source of truth (PDF + planning prompt).
- No timestamp-only checkpoints; no random or wall-clock `run_id`s.
- Dry run must not write lake, share, events, or checkpoint.
- Durable outputs before `state/checkpoint.json`; manually review `db/init.sql` and `db/changes.sql`.

---

## What I verified manually

| Area | Verification |
|------|----------------|
| **Spec understanding** | Each contract section (DB, checkpoint, lake, share, events, dry-run) mapped to code paths before accepting implementation |
| **SQL** | `db/init.sql`: 32 customers, 210 cases, deterministic anchor, keyword variety; `db/changes.sql`: 5 updates, 2 customers, 10 cases, fixed change timestamp after seed |
| **Checkpoint semantics** | `checkpoint_after` is the last row in sort order; zero-row table leaves watermark unchanged |
| **Ingest pipeline** | Staging under `tmp/runs/<run_id>/`, promote, then checkpoint; recovery when `outputs_materialized()` is true |
| **Docker / API** | `docker compose up -d`; `POST /ingest` dry and non-dry; `changes.sql` between runs |
| **Incremental deltas** | Second ingest: customers = 2, cases = 15 |
| **Automated tests** | `.venv/bin/python -m pytest -v` (13 tests) |
| **Smoke workflow** | `./scripts/smoke_verify.sh` (16 checks, end-to-end report) |
| **Environment** | API and tests run via `.venv/bin/python -m ...` (avoid system `uvicorn` without `psycopg`) |

---

## Commands I ran

```bash
# Database
docker compose up -d
docker compose down -v   # when resetting for tests or a clean demo

# Python environment
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

# Service
.venv/bin/python -m uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

# Ingest workflow
curl -s -X POST "http://localhost:8000/ingest?dry_run=false" | jq .
docker exec -i $(docker compose ps -q postgres) psql -U interop -d interop < db/changes.sql
curl -s -X POST "http://localhost:8000/ingest?dry_run=false" | jq .
curl -s -X POST "http://localhost:8000/ingest?dry_run=true" | jq .

# Verification
.venv/bin/python -m pytest -v
./scripts/smoke_verify.sh
```

---

## Edge cases I checked

| Edge case | Expected behavior | How it was checked |
|-----------|-------------------|-------------------|
| **Timestamp ties** | Rows with same `updated_at` ordered by PK; composite watermark does not skip | `tests/test_watermark_ties.py` |
| **Initial ingest** | Full seed load; checkpoint created | `tests/test_initial_ingest.py` |
| **Incremental after `changes.sql`** | customers=2, cases=15 | `tests/test_incremental.py`, smoke `ING-06` |
| **No-op ingest** | Zero deltas; no lake/share rewrite; `share_path` null | `tests/test_noop.py` |
| **Dry run** | Manifest with predicted `checkpoint_after`; no durable writes | `tests/test_dry_run.py`, smoke `ING-10`–`11` |
| **Deterministic `run_id`** | Same DB + checkpoint → same 64-char hex hash | `tests/test_run_id.py` |
| **Share / event shape** | Required JSONL fields; two event lines per run | `tests/test_artifacts.py` |
| **Zero-delta event** | Event line with `delta_row_count=0`, `share_path=null` | `tests/test_zero_delta_event_on_noop` |
| **Checkpoint-last failure** | Promoted outputs exist; checkpoint unchanged on failure before save | `tests/test_failure_safety.py` |
| **Recovery** | Same `run_id` + existing outputs → checkpoint advances without duplicate lake/share | `tests/test_share_determinism.py` |
| **Share determinism** | Byte-identical share files for same inputs | `tests/test_share_determinism.py` |
| **Schema fingerprint** | Stable hash from `information_schema` | `tests/test_schema_fingerprint.py` |

---

## What the agent got wrong and how I corrected it

| What went wrong | Correction |
|-----------------|------------|
| **`uvicorn` on system Python 3.9** — missing `psycopg` when not using the venv | Documented and ran `.venv/bin/python -m uvicorn` and `.venv/bin/python -m pytest` in README |
| **No-op test compared `events/` checksums** — failed on every no-op because spec allows a new event file per successful run | Compare lake/share checksums only; exclude `events/` in `test_noop.py` |
| **Watermark tie test** — expected `last_pk >= 35` after two tied inserts without matching setup | Reworked test: initial ingest, then three customers at one timestamp → `last_pk == 35` |
| **`changes.sql` used psql variables** — awkward for `docker exec ... < db/changes.sql` | Replaced with plain SQL literals and fixed timestamps |
| **Smoke dry-run check** — string compare on `"true"` instead of boolean | Use Python `dry_run is True` on parsed JSON manifest |
| **Early “plan only” tracker** — `development-plan.md` left unchecked after implementation | Updated plan status, todos, and test counts to match the repo |
| **Schema fingerprint** — initially hardcoded column types | Switched to `information_schema.columns` + dedicated test (optional hardening) |
| **Failure-safety test depth** — only asserted checkpoint unchanged | Also assert lake/share/events materialized before simulated checkpoint failure |

For safety-critical items (checkpoint ordering, delta counts, tie handling), I treated agent output as a draft until the spec, SQL, and tests agreed.
