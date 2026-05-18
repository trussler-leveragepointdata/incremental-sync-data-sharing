# Execution Plan — Production AWS Delivery

**Documentation only** — delivery plan for [`ARCHITECTURE_AWS.md`](ARCHITECTURE_AWS.md), informed by the local prototype and **AI-assisted development** (see [`AI_USAGE.md`](AI_USAGE.md)). No AWS build in this repo.

---

## Estimation assumptions

**Fixed:** all sprints are **2 weeks** (10 working days). Sprint count **3**. Calendar to prod canary **~6 weeks** of sprint work, plus **1–2 weeks buffer** for hardening (not compressed by AI).

| Assumption | Baseline (traditional) | AI-assisted |
|------------|------------------------|-------------|
| **Sprint length** | 2 weeks | **2 weeks** (unchanged) |
| **Sprint count** | 3 | 3 |
| **Team size** | **4–6 FTE** (2 backend, 1 data platform, 0.5–1 SRE, tech lead) | **3–4 FTE** + tech lead (0.4–0.6) + 0.5 SRE |
| **Sprint capacity** | ~8–12 person-weeks / sprint | ~6–8 person-weeks / sprint |
| **Total effort** | **~24–36 person-weeks** | **~18–24 person-weeks** |
| **Calendar (sprints only)** | 6 weeks | **6 weeks** |

**Where AI saves effort (not calendar):** smaller team still hits the same milestones in **standard 2-week boxes** by higher throughput on implementation (~1.3–1.5× on ~40–50% of sprint work): IaC scaffolding, Fargate/Iceberg boilerplate, contract/replay tests, runbooks, reconciliation SQL, API stubs.

**Where AI does not reduce time:** security review, tenant isolation, load/failure tests at 5k/s, canary sign-off, on-call validation—still scheduled inside each 2-week sprint.

---

## Team & ownership

| Role | FTE (AI-assisted) | Delegated | Tech lead owns |
|------|-------------------|-----------|----------------|
| Tech lead | 0.4–0.6 | Ceremonies, review | CDC contract, offset model, idempotency, go/no-go, replay runbooks |
| Backend ×2 | 2.0 | Processors, Iceberg writer, events, consumer API | Contract review |
| Data platform | 1.0 | Glue/Iceberg, compaction, reconciliation | Freshness / reconciliation SLO |
| SRE | 0.5 | IaC baseline, dashboards, load/failure tests, canary | Security review with lead |

*Baseline plan adds ~1–2 FTE (second data platform or full-time SRE) for the same three 2-week sprints.*

---

## Sprints (3 × 2 weeks)

| Sprint | Capacity (impl / review) | Goal & exit |
|--------|--------------------------|-------------|
| **1 — Ingest** | **5 / 2** (~7 pw) | CDC → MSK; canonical event + schema registry; Fargate skeleton + DLQ; IaC baseline. **Exit:** contract tests in CI; DLQ; dev load sample. *AI:* schemas, consumer skeleton, Terraform drafts. |
| **2 — Lake + events** | **6 / 2** (~8 pw) | Iceberg MERGE; lake commit ≠ CDC offset; EventBridge/SQS; reconciliation; replay tests. **Exit:** staging p95 freshness ≤10 min; 24h reconciliation. *AI:* MERGE templates, replay tests, reconciliation queries. |
| **3 — Consumer + rollout** | **5 / 3** (~8 pw) | DynamoDB index + cursor API; auth/rate limits; 300 QPS / 1k burst; failure injection; canary start. **Exit:** SLO dashboards; security sign-off; one tenant in canary. *AI:* OpenAPI, load scripts; **human:** pen-test, canary approval. |

**Buffer (after Sprint 3):** 1–2 weeks for production hardening, cost tuning, and rollout completion (10% → 100% tenants)—same calendar whether or not AI was used during build.

---

## Quality gates (each 2-week sprint)

Schema/contract tests · CDC ordering + replay · idempotent retry + duplicate delivery · cursor monotonicity · lake commit validation · reconciliation · load (sustained + burst) · failure injection · security (IAM, encryption, tenants) · observability (lag, freshness, index drift). Lead signs off; AI-generated tests need human review on watermark/tie/failure semantics (from prototype).

---

## Rollout (Sprint 3 + buffer)

Dev/staging → **shadow** → **canary** (one tenant) → **10% → 50% → 100%** → rollback: freeze CDC, last good Iceberg snapshot + cursor snapshot.

---

## Top risks

| Risk | Mitigation |
|------|------------|
| Underestimating review load with smaller team | Reserve explicit review capacity each sprint (see impl/review split) |
| AI-generated IaC/Iceberg untested at scale | Load + failure gates; lead review on commit boundaries |
| CDC lag at 5k/s | MSK scale; Fargate autoscale; lag alarms |
| Consumer duplicates | `run_id` + cursor; idempotent MERGE |

---

## Prototype handoff

Local [`POST /ingest`](src/main.py) + **13 pytest** scenarios are acceptance fixtures for Sprints 1–2. AI shrinks **team size and person-weeks**, not **sprint length**—each sprint remains a full 2-week delivery cadence.
