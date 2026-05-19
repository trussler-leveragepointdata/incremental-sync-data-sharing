# Execution Plan — Production AWS Delivery

**Documentation only** — delivery plan for [`ARCHITECTURE_AWS.md`](ARCHITECTURE_AWS.md), informed by the local prototype and **AI-assisted development** (see [`AI_USAGE.md`](AI_USAGE.md)). No AWS build in this repo.

---

## Estimation assumptions

**Fixed:** all sprints are **2 weeks** (10 working days). Sprint count **4**. Calendar to prod canary **~8 weeks** of sprint work, plus **1–2 weeks buffer** for hardening (not compressed by AI).

| Assumption | Baseline (traditional) | AI-assisted |
|------------|------------------------|-------------|
| **Sprint length** | 2 weeks | **2 weeks** (unchanged) |
| **Sprint count** | 4 | 4 |
| **Team size** | **2 FTE** + **1 tech lead** | **1 FTE** + **1 tech lead** + **0.5 SRE** (part-time) |
| **Sprint capacity** | **~4–5 person-weeks** / sprint | **~4 person-weeks** / sprint (**~5–6 effective** on AI-suitable impl) |
| **Total effort** | **~18–20 person-weeks** | **~16–18 person-weeks** (calendar); **~20–23 effective** on boilerplate-heavy work |
| **Calendar (sprints only)** | 8 weeks | 8 weeks |
| **Calendar (sprints + buffer)** | **~9–10 weeks** to canary | **~9–10 weeks** to canary |

**Lean-team assumption:** both tracks keep the same **four** 2-week milestones because the local prototype de-risks contracts (watermark, `run_id`, checkpoint-last, replay tests). Engineers are **senior generalists** (backend + data path); the tech lead carries architecture, review, and go/no-go. The AI-assisted track concentrates platform gates (IaC, load/failure, dashboards) in **part-time SRE** capacity rather than a second builder.

**Where AI saves effort (not calendar):** the AI-assisted track runs **half the builder headcount** but similar milestones by higher throughput on implementation (~1.3–1.5× on ~40–50% of sprint work): IaC scaffolding, Fargate/Iceberg boilerplate, contract/replay tests, runbooks, reconciliation SQL, API stubs.

**Where AI does not reduce time:** security review, tenant isolation, load/failure tests at 5k/s, canary sign-off, on-call validation—still scheduled inside each 2-week sprint (SRE + lead on the AI-assisted track; lead + engineers on baseline).

---

## Dependent metrics (single source of truth)

Use these numbers consistently across [`ARCHITECTURE_AWS.md`](ARCHITECTURE_AWS.md), [`README.md`](README.md), and [`planning/development-plan.md`](planning/development-plan.md).

| Metric | Baseline (2 FTE + lead) | AI-assisted (1 FTE + lead + 0.5 SRE) |
|--------|-------------------------|----------------------------------------|
| **Builders** | 2.0 | 1.0 |
| **Tech lead (project)** | 0.5 FTE | 0.5 FTE |
| **SRE** | — (engineers + lead cover IaC/obs basics) | 0.5 FTE |
| **Person-weeks / sprint** | ~4–5 | ~4 calendar (~5–6 effective on AI-suitable impl) |
| **Person-weeks (4 sprints)** | ~18–20 | ~16–18 calendar (~20–23 effective) |
| **End-to-end calendar** | ~9–10 weeks (8 sprint + 1–2 buffer) | ~9–10 weeks (same) |

---

## Team & ownership

| Role | Baseline (2 FTE + lead) | AI-assisted (1 FTE + lead + 0.5 SRE) | Tech lead owns |
|------|-------------------------|--------------------------------------|----------------|
| **Tech lead** | 0.5 | 0.5 | CDC contract, offset model, idempotency, go/no-go, replay runbooks |
| **Engineer(s)** | 2.0 (split backend vs data platform) | 1.0 (both paths; AI for scaffolding) | Contract review |
| **SRE** | — | 0.5 | IaC baseline, dashboards, load/failure tests, canary; security review with lead |

**Baseline split:** Engineer A — CDC → MSK, Fargate processors, consumer API. Engineer B — Iceberg/Glue, events, reconciliation. **AI-assisted split:** single engineer owns vertical slices per sprint; SRE owns infra gates and failure injection; lead reviews watermark/tie/failure semantics (from prototype).

---

## Sprints (4 × 2 weeks)

Capacity = **implementation / review** person-weeks per sprint (review = lead ± SRE). Totals align with **Dependent metrics** above.

| Sprint | Baseline (2 + lead) | AI-assisted (1 + lead + 0.5 SRE) | Goal & exit |
|--------|---------------------|----------------------------------|-------------|
| **1 — Ingest** | **3 / 1** (~4–5 pw) | **3 / 1** (~4 pw; ~5 effective w/ AI) | CDC → MSK; canonical event + schema registry; Fargate skeleton + DLQ; IaC baseline. **Exit:** contract tests in CI; DLQ; dev load sample. *AI:* schemas, consumer skeleton, Terraform drafts. |
| **2 — Lake + events** | **3 / 1.5** (~4.5–5 pw) | **3 / 1** (~4 pw; ~5–6 effective w/ AI) | Iceberg MERGE; lake commit ≠ CDC offset; EventBridge/SQS; reconciliation; replay tests. **Exit:** staging p95 freshness ≤10 min; 24h reconciliation. *AI:* MERGE templates, replay tests, reconciliation queries. |
| **3 — Consumer API** | **3 / 1.5** (~4.5–5 pw) | **3 / 1** (~4 pw; ~5–6 effective w/ AI) | DynamoDB change index + cursor API; auth/rate limits; 300 QPS sustained in staging. **Exit:** contract tests for cursor monotonicity; staging load sample. *AI:* OpenAPI, index writer stubs. |
| **4 — Hardening + rollout** | **3 / 2** (~5 pw) | **2.5 / 1.5** (~4 pw; SRE-heavy gates) | 1k burst; failure injection; SLO dashboards; security sign-off; canary start. **Exit:** pen-test complete; one tenant in canary. *AI:* load scripts, runbooks; **human:** canary approval. |

**Buffer (after Sprint 4):** 1–2 weeks for production hardening, cost tuning, and rollout completion (10% → 100% tenants)—same calendar on both tracks; lean staffing uses buffer for review and rollout more than net-new build.

---

## Quality gates (each 2-week sprint)

Schema/contract tests · CDC ordering + replay · idempotent retry + duplicate delivery · cursor monotonicity · lake commit validation · reconciliation · load (sustained + burst) · failure injection · security (IAM, encryption, tenants) · observability (lag, freshness, index drift). Lead signs off; AI-generated tests need human review on watermark/tie/failure semantics (from prototype). **AI-assisted:** SRE runs load/failure and observability gates (concentrated in Sprints 3–4); **baseline:** engineers execute with lead sign-off.

---

## Rollout (Sprint 4 + buffer)

Dev/staging → **shadow** → **canary** (one tenant) → **10% → 50% → 100%** → rollback: freeze CDC, last good Iceberg snapshot + cursor snapshot.

---

## Top risks

| Risk | Mitigation |
|------|------------|
| **Capacity vs scope** with 2 (or 1) builders + lead | Prototype fixtures for Sprints 1–2; defer non-MVP (e.g. multi-region) to buffer; explicit impl/review split each sprint |
| Underestimating review load | Lead reserves review days in week 2 of each sprint; AI-assisted SRE owns failure/load gates in Sprints 3–4 |
| AI-generated IaC/Iceberg untested at scale | Load + failure gates; lead review on commit boundaries |
| CDC lag at 5k/s | MSK scale; Fargate autoscale; lag alarms |
| Consumer duplicates | `run_id` + cursor; idempotent MERGE |

---

## Prototype handoff

Local [`POST /ingest`](src/main.py) + **13 pytest** scenarios are acceptance fixtures for Sprints 1–2. AI shrinks **builder headcount and person-weeks per sprint**, not **sprint length**—each of **four** sprints remains a full 2-week delivery cadence with a lean **2 + lead** (baseline) or **1 + lead + 0.5 SRE** (AI-assisted) team.
