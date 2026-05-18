#!/usr/bin/env bash
# End-to-end smoke verification for the incremental sync prototype.
# Starts Postgres, runs the API, executes the README workflow, and checks manifests.
#
# Usage (from repository root):
#   ./scripts/smoke_verify.sh
#
# Optional env:
#   SMOKE_PORT=8000          API port (default 8000)
#   SMOKE_RESET_DB=1         docker compose down -v before up (default 1)
#   SMOKE_CLEAN_OUTPUTS=1    remove state/lake/share/events/tmp first (default 1)

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PORT="${SMOKE_PORT:-8000}"
RESET_DB="${SMOKE_RESET_DB:-1}"
CLEAN_OUTPUTS="${SMOKE_CLEAN_OUTPUTS:-1}"
PYTHON="${ROOT}/.venv/bin/python"
BASE_URL="http://127.0.0.1:${PORT}"

UVICORN_PID=""
SMOKE_OK=1
CHECK_TOTAL=0
CHECK_PASSED=0
CHECK_FAILED=0

declare -a CHECK_ROWS=()

log() { printf '==> %s\n' "$*"; }

record_check() {
  local id="$1"
  local description="$2"
  local status="$3"
  local detail="${4:-}"
  detail="$(printf '%s' "${detail}" | tr '\n' ' ' | cut -c1-72)"
  CHECK_ROWS+=("${id}|${description}|${status}|${detail}")
  CHECK_TOTAL=$((CHECK_TOTAL + 1))
  if [[ "${status}" == "PASS" ]]; then
    CHECK_PASSED=$((CHECK_PASSED + 1))
    printf '  [PASS] %s — %s\n' "${id}" "${description}"
    [[ -n "${detail}" ]] && printf '         %s\n' "${detail}"
  else
    CHECK_FAILED=$((CHECK_FAILED + 1))
    SMOKE_OK=0
    printf '  [FAIL] %s — %s\n' "${id}" "${description}" >&2
    [[ -n "${detail}" ]] && printf '         %s\n' "${detail}" >&2
  fi
}

run_check() {
  local id="$1"
  local description="$2"
  shift 2
  local detail=""
  if detail="$("$@" 2>&1)"; then
    record_check "${id}" "${description}" "PASS" "${detail}"
    return 0
  else
    local code=$?
    record_check "${id}" "${description}" "FAIL" "${detail:-exit code ${code}}"
    return 1
  fi
}

print_summary() {
  local pass_pct fail_pct
  pass_pct="$("${PYTHON}" -c "t=${CHECK_TOTAL}; p=${CHECK_PASSED}; print(f'{100.0*p/t:.1f}' if t else '0.0')")"
  fail_pct="$("${PYTHON}" -c "t=${CHECK_TOTAL}; f=${CHECK_FAILED}; print(f'{100.0*f/t:.1f}' if t else '0.0')")"

  printf '\n'
  echo '================================================================================'
  echo ' SMOKE VERIFICATION REPORT'
  echo '================================================================================'
  printf ' Repository : %s\n' "${ROOT}"
  printf ' API base   : %s\n' "${BASE_URL}"
  echo '--------------------------------------------------------------------------------'
  echo ' What was tested:'
  printf '   - Local infrastructure (venv, Postgres, API health)\n'
  printf '   - Initial full ingest from seed data\n'
  printf '   - Durable outputs after initial ingest (checkpoint, share)\n'
  printf '   - Incremental ingest after db/changes.sql\n'
  printf '   - No-op ingest (zero deltas)\n'
  printf '   - Dry-run ingest (read-only; checkpoint unchanged)\n'
  echo '--------------------------------------------------------------------------------'
  echo ' Check results:'
  printf '   %-6s  %-32s  %-6s  %s\n' "ID" "Check" "Status" "Detail"
  printf '   %-6s  %-32s  %-6s  %s\n' "------" "--------------------------------" "------" "------------------------------"
  local row id desc status detail
  for row in "${CHECK_ROWS[@]}"; do
    IFS='|' read -r id desc status detail <<< "${row}"
    printf '   %-6s  %-32s  %-6s  %s\n' "${id}" "${desc}" "${status}" "${detail}"
  done
  echo '--------------------------------------------------------------------------------'
  echo ' Summary:'
  printf '   Total checks : %d\n' "${CHECK_TOTAL}"
  printf '   Passed       : %d (%.1f%%)\n' "${CHECK_PASSED}" "${pass_pct}"
  printf '   Failed       : %d (%.1f%%)\n' "${CHECK_FAILED}" "${fail_pct}"
  echo '--------------------------------------------------------------------------------'
  if [[ "${SMOKE_OK}" -eq 1 ]]; then
    echo ' FINAL RESULT: PASS — all smoke checks succeeded.'
  else
    echo ' FINAL RESULT: FAIL — one or more smoke checks failed.'
  fi
  echo '================================================================================'
}

cleanup() {
  if [[ -n "${UVICORN_PID}" ]] && kill -0 "${UVICORN_PID}" 2>/dev/null; then
    log "Stopping API (pid ${UVICORN_PID})"
    kill "${UVICORN_PID}" 2>/dev/null || true
    wait "${UVICORN_PID}" 2>/dev/null || true
    UVICORN_PID=""
  fi
}

on_exit() {
  cleanup
  print_summary
  if [[ "${SMOKE_OK}" -eq 1 ]]; then
    exit 0
  else
    exit 1
  fi
}
trap on_exit EXIT

assert_manifest() {
  local label="$1"
  local manifest_json="$2"
  local min_c="${3:-}"
  local min_cases="${4:-}"
  local exact_c="${5:-}"
  local exact_cases="${6:-}"
  MANIFEST_JSON="${manifest_json}" \
  LABEL="${label}" \
  MIN_C="${min_c}" \
  MIN_CASES="${min_cases}" \
  EXACT_C="${exact_c}" \
  EXACT_CASES="${exact_cases}" \
  "${PYTHON}" -c "
import json, os, sys
m = json.loads(os.environ['MANIFEST_JSON'])
t = m.get('tables', {})
c = t.get('customers', {}).get('delta_row_count')
k = t.get('cases', {}).get('delta_row_count')
if c is None or k is None:
    raise SystemExit('missing delta_row_count')
min_c = os.environ.get('MIN_C', '')
min_cases = os.environ.get('MIN_CASES', '')
exact_c = os.environ.get('EXACT_C', '')
exact_cases = os.environ.get('EXACT_CASES', '')
if min_c and c < int(min_c):
    raise SystemExit(f'customers {c} < {min_c}')
if min_cases and k < int(min_cases):
    raise SystemExit(f'cases {k} < {min_cases}')
if exact_c and c != int(exact_c):
    raise SystemExit(f'customers {c} != {exact_c}')
if exact_cases and k != int(exact_cases):
    raise SystemExit(f'cases {k} != {exact_cases}')
rid = (m.get('run_id') or '?')[:16]
print(f'customers={c}, cases={k}, run_id={rid}...')
"
}

ingest() {
  local dry_run="${1:-false}"
  curl -sf -X POST "${BASE_URL}/ingest?dry_run=${dry_run}"
}

# --- Infrastructure ---

log "Smoke verification starting"

run_check "INF-01" "Python venv available" test -x "${PYTHON}"

if [[ "${RESET_DB}" == "1" ]]; then
  log "Resetting Postgres volume (docker compose down -v)"
  docker compose down -v >/dev/null 2>&1 || true
fi

log "Starting Postgres (docker compose up -d)"
docker compose up -d

run_check "INF-02" "Postgres accepts connections" bash -c "
for i in \$(seq 1 60); do
  '${PYTHON}' -c \"import psycopg; psycopg.connect('postgresql://interop:interop@localhost:5432/interop', connect_timeout=2).close()\" 2>/dev/null \\
    && echo 'connected to interop@localhost:5432' && exit 0
  sleep 1
done
exit 1
"

if [[ "${CLEAN_OUTPUTS}" == "1" ]]; then
  log "Cleaning local output directories"
  rm -rf state lake share events tmp
fi

log "Starting API on ${BASE_URL}"
"${PYTHON}" -m uvicorn src.main:app --host 127.0.0.1 --port "${PORT}" \
  >/dev/null 2>&1 &
UVICORN_PID=$!

run_check "INF-03" "API /health returns 200" bash -c "
for i in \$(seq 1 30); do
  curl -sf '${BASE_URL}/health' >/dev/null && exit 0
  sleep 1
done
exit 1
"

# --- Workflow ---

log "Step 1: Initial ingest"
M1="$(ingest false || true)"
export M1
run_check "ING-01" "Initial ingest returns manifest" test -n "${M1}"
run_check "ING-02" "Initial ingest deltas (>=30 customers, >=200 cases)" \
  assert_manifest "initial" "${M1}" 30 200
run_check "ING-03" "checkpoint.json created" test -f state/checkpoint.json
run_check "ING-04" "share artifacts created" test -f share/customers/changes.jsonl

log "Step 2: Apply db/changes.sql"
PG_CID="$(docker compose ps -q postgres)"
run_check "CHG-01" "Postgres container running" test -n "${PG_CID}"
if [[ -n "${PG_CID}" ]]; then
  docker exec -i "${PG_CID}" psql -U interop -d interop < db/changes.sql >/dev/null
  run_check "CHG-02" "changes.sql applied successfully" true
else
  record_check "CHG-02" "changes.sql applied successfully" "FAIL" "no postgres container"
fi

log "Step 3: Incremental ingest"
M2="$(ingest false || true)"
export M2
run_check "ING-05" "Incremental ingest returns manifest" test -n "${M2}"
run_check "ING-06" "Incremental deltas (customers=2, cases=15)" \
  assert_manifest "incremental" "${M2}" "" "" 2 15

log "Step 4: No-op ingest"
M3="$(ingest false || true)"
export M3
run_check "ING-07" "No-op ingest returns manifest" test -n "${M3}"
run_check "ING-08" "No-op deltas (customers=0, cases=0)" \
  assert_manifest "noop" "${M3}" "" "" 0 0

log "Step 5: Dry run (read-only)"
CP_BEFORE="$(cat state/checkpoint.json)"
M4="$(ingest true || true)"
export M4
run_check "ING-09" "Dry-run ingest returns manifest" test -n "${M4}"
run_check "ING-10" "Dry-run manifest dry_run=true" "${PYTHON}" -c "
import json, os
m = json.loads(os.environ['M4'])
assert m.get('dry_run') is True
print('dry_run=true')
"
run_check "ING-11" "Dry-run leaves checkpoint unchanged" test "${CP_BEFORE}" = "$(cat state/checkpoint.json)"

log "Smoke verification steps complete (see report below)."
