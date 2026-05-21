# Multi-Agent Team Architecture — Phased Plan

This document plans the evolution from today's single-process pipeline into an
**actor-model multi-agent system** where each agent has private memory, an
explicit mailbox, and a focused role — mirroring how real engineering teams
work. It extends the scaling roadmap in `README.md`; both should be read
together. Phases 1-4 (in `PLAN.md`) are complete. Phases 5-9 below build on
that foundation.

## North star

A user opens the app, starts a conversation with a Product Owner agent, and
**describes the application they want to build the way they would to a human
PM.** Behind the scenes a team of specialized agents — Product Owner,
Project Manager, Business Analyst, Solution Architect, Designer, Backend Dev,
Frontend Dev, QA, DevOps — collaborate over hours or days to produce a
working application. Each agent has its own memory and tools; they exchange
structured messages only when needed; the user sees a live activity stream
and is pulled in at decision points and milestone checkpoints. Generated
apps are spec-traceable, audit-trailed, and production-aware for their
target domain.

## Architecture overview

### The actor model

Each agent is an autonomous actor with:

- **Identity** — name, role, role-specific system prompt (typically 2-5K
  tokens), preferred model, and a whitelist of tools they may invoke.
- **Private memory** — accumulated decisions, owned artifacts, open
  questions, completed-task history, free-form notes. Persisted per-agent.
- **A mailbox** — a durable FIFO queue of incoming messages. Agents block
  on their mailbox; they do not poll peers.
- **An outbox** — structured messages they explicitly send to specific
  recipients (other agents, the user via the PO).
- **An owned slice of the workspace** — the shared filesystem of artifacts
  (spec, ADR, code, tests). Reads are open to anyone; writes are restricted
  by convention (Backend Dev writes `backend/app/**`, QA writes
  `backend/tests/**`, etc.).

There is **no shared mutable state** between agents. Coordination happens
exclusively through messages and through the shared workspace.

### Message types

Small, structured set. Every message is auditable.

| Type | Direction | Purpose |
|---|---|---|
| `TaskAssignment` | PM → worker | Assign a single atomic task with retry budget and deadline |
| `StatusUpdate` | worker → PM | Report task status (accepted, in_progress, blocked, completed, failed) |
| `Question` / `Answer` | peer ↔ peer | Targeted question to a specific other agent |
| `InfoRequest` / `InfoResponse` | peer ↔ peer | Request a specific artifact slice from an owner |
| `Blocker` | worker → PM | Cannot proceed without a decision; lists options |
| `DecisionRequest` | PM → PO | Surface a blocker that needs the user |
| `UserMessage` / `UserReply` | PO ↔ user | The customer-facing chat channel |
| `Heartbeat` | every agent → bus | Health check; missing heartbeats trigger reassignment |

No free-form chat between agents. Every communication has a type, a schema,
and a logged audit trail.

### The shared workspace

A versioned filesystem (think Git, internally) that holds:

```
.workspace/
├── brief.md              # PO → BA: the Requirements Brief
├── spec.json             # BA-owned: the structured Spec
├── adr/                  # SA-owned: Architecture Decision Records
├── plan/                 # PM-owned: milestone & task plans
├── designs/              # Designer-owned: component specifications
├── backend/              # Backend Dev-owned: server code
├── frontend/             # Frontend Dev-owned: UI code
├── tests/                # QA-owned: test files & results
├── infra/                # DevOps-owned: Dockerfiles, CI, deployment manifests
└── audit/                # System-owned: every decision + rationale + agent
```

Optimistic concurrency: when an agent claims a file for modification, peers
wait or work elsewhere. Writes go through a `Workspace.commit(agent, files,
message)` API that records the author and rationale into `audit/`.

### The runtime

Python asyncio. One task per agent. The Mailbox blocks on `await
queue.get()`. The MessageBus is a router that delivers messages to mailboxes,
persists them, and tracks delivery acknowledgements.

```python
async def agent_loop(agent: Agent):
    while not agent.shutdown:
        msg = await agent.mailbox.next()
        try:
            await agent.handle(msg)
            await agent.mailbox.ack(msg)
        except Exception as exc:
            await agent.escalate(msg, exc)
```

Failure isolation is structural: one agent crashing doesn't corrupt peers.

---

## Capacity ceiling at each phase

| Phase | Realistic scope | Wall-clock for the user | LLM token cost |
|---|---|---|---|
| Today | Small CRUD; placeholder UIs | 5 minutes | $0.10-$0.50 |
| Phase 5 done | Same scope, conversational onboarding | 30-60 minutes | $1-$5 |
| Phase 6 done | Medium-complexity SaaS w/ real UIs | 2-6 hours | $10-$50 |
| Phase 7 done | Complex SaaS, domain-aware (money, audit, roles) | 6-24 hours | $50-$200 |
| Phase 8 done | Niche fintech / healthcare MVP | 1-3 days | $200-$1,000 |
| Phase 9 done | Trustworthy for senior-reviewed enterprise use | days-weeks | $1K-$10K |

Production banking is **not** in the table at any phase. That requires a
human engineering team. The phased plan moves the realistic envelope from
"small CRUD" to "complex domain SaaS with human-in-the-loop review."

---

## Phase 5 — Actor runtime + minimal team

**Goal.** Move from a single-process pipeline to a four-agent team:
**Product Owner** ↔ user, **Project Manager** orchestrating,
**Engineer** doing the work (wraps the existing extract → generate →
package flow as a single agent), **QA** running tests and gating.

This is the architectural shift. Once the substrate exists, adding more
specialized roles in Phase 6 is incremental.

### Deliverables

#### New: `packages/agent_runtime/`

- `agent.py` — `Agent` base class with `run()`, `handle(msg)`, `escalate()`
- `messages.py` — typed Message dataclasses
- `mailbox.py` — durable FIFO queue backed by SQLite/Postgres
- `bus.py` — MessageBus router, delivery, ack/retry, deadletter
- `workspace.py` — versioned filesystem with ownership + commit log
- `memory.py` — `AgentMemory` dataclass + persistence
- `tools.py` — `Tool` protocol; whitelist enforcement per agent

#### New: `packages/agents/`

- `po.py` — Product Owner. Maintains the user chat. Asks clarifying
  questions. Produces the Requirements Brief and writes it to the
  workspace. Decides when the brief is "complete enough" to hand off.
- `pm.py` — Project Manager. Reads the Brief, drafts a milestone +
  task plan (LLM call), gets PO/user approval, then dispatches tasks
  to workers. Tracks status, retries on bounded failures, escalates
  blockers to PO.
- `engineer.py` — Engineer. Wraps today's `extract_spec → generate →
  package` as a single agent. Receives tasks like "implement
  milestone 2" and produces commits to the workspace.
- `qa.py` — QA. Receives a "validate milestone N" task, runs
  `validate`, `reconcile`, and `pytest` on the workspace, files bug
  reports back to Engineer (bounded retries), eventually signs off.

#### API: `apps/api/routers/projects.py`

New endpoints sitting alongside the existing `/jobs`:

- `POST /projects` — start a new project; spawns a team; returns project_id.
- `GET /projects/{id}` — full state: team, mailboxes, workspace tree,
  current milestone, open decisions.
- `POST /projects/{id}/message` — user message routed to PO.
- `GET /projects/{id}/stream` — SSE stream of activity events (status
  updates, file writes, user-facing prompts).

Legacy `/jobs` stays for one-shot generation.

#### UI: `apps/web/src/pages/Project.tsx`

- **Center: chat with PO.** Multi-turn, streaming. Familiar interface.
- **Left rail: team activity.** Live list of agents with their current
  status (PM: planning, Engineer: writing backend/app/routers/users.py,
  QA: idle).
- **Right rail: workspace snapshot.** Tree view; click any file to see
  current contents and history.
- **Top: milestone progress bar.** Current milestone + completion %.
- **Bottom: decision queue.** Cards for any `DecisionRequest` from PM →
  PO that needs user input. Approve / modify / reject.

#### Persistence schema

Postgres (or SQLite for self-host). New tables:

- `projects` (id, name, status, created_at, …)
- `agents` (id, project_id, role, identity_json, memory_json, …)
- `messages` (id, project_id, type, from_agent, to_agent, payload, sent_at, acked_at, …)
- `workspace_files` (project_id, path, owner_agent, content_blob_uri, …)
- `workspace_commits` (id, project_id, agent_id, files[], message, made_at)
- `audit_log` (id, project_id, agent_id, kind, content, created_at)

### Effort

**L (8-12 weeks)** for one engineer. Substrate-heavy; the agents themselves
are small once the substrate exists.

### Dependencies

- Roadmap Item 6 (Job + artifact persistence). Multi-agent state must
  survive restarts and span days. Build the JobStore generalization
  first; the agent_runtime sits on top of it.

### User-visible outcome

The product transforms from "upload a doc and watch a pipeline" into
"describe your app to the PO, watch the team build it." Even at the
minimum-team stage, the demo value is enormous.

---

## Phase 6 — Specialized roles

**Goal.** Split the monolithic Engineer into specialized roles, add Business
Analyst (separated from PO), Solution Architect, and Designer. After this
phase the team has the full 8-role org chart.

### Deliverables

#### Role splits in `packages/agents/`

- `ba.py` — Business Analyst. Owns the Spec. Consumes the Brief, produces
  structured Spec, asks PO/user to resolve ambiguities. Updates Spec as
  PM dispatches refinements.
- `sa.py` — Solution Architect. Produces an Architecture Decision Record
  (ADR) for each significant choice (auth strategy, persistence pattern,
  background-job approach, integration choices). The ADR lives in
  `workspace/adr/`. Other agents read it before making implementation
  choices.
- `designer.py` — Designer. Owns `workspace/designs/`. For each screen,
  emits a component specification: layout, components used, states
  (loading/error/empty), key interactions. Hands off to Frontend Dev.
- `backend_dev.py` — Backend Developer. Owns `workspace/backend/`. Uses
  mechanical codegen for CRUD plus the AI code-editor tool for targeted
  modifications. Implements the service layer where ADR requires.
- `frontend_dev.py` — Frontend Developer. Owns `workspace/frontend/`.
  Consumes Designer's component specs + the API client + ADR. Produces
  the React/TS components (AI-driven, gated by tsc — Roadmap Item 1).
- `devops.py` — DevOps. Owns `workspace/infra/`. Produces Dockerfiles,
  docker-compose, CI configuration, Caddy/Traefik reverse-proxy config,
  deployment templates.

#### Role-specific tools

Each agent's tool whitelist is constrained:

| Agent | Tools |
|---|---|
| PO | `chat_user`, `read_brief`, `write_brief`, `ask_pm` |
| PM | `read_brief`, `read_adr`, `write_plan`, `assign_task`, `escalate_to_po` |
| BA | `read_brief`, `write_spec`, `validate_spec`, `ask_po` |
| SA | `read_spec`, `write_adr`, `ask_ba` |
| Designer | `read_spec`, `read_adr`, `write_design`, `ask_sa` |
| Backend Dev | `read_spec`, `read_adr`, `read_design`, `write_backend_file`, `edit_backend_file`, `read_backend_file`, `run_validator`, `ask_sa`, `ask_qa` |
| Frontend Dev | (analogous, on frontend/) |
| QA | `read_spec`, `read_*`, `write_tests`, `run_tests`, `file_bug`, `signoff_milestone` |
| DevOps | `read_adr`, `write_infra_file`, `run_docker` |

The whitelist is enforced by the `Tool` dispatcher, not by prompting alone.

#### Updated PM behavior

PM dispatches by role and respects dependencies:

- Tasks with `kind: "design"` go to Designer.
- Tasks with `kind: "code"` and `area: "backend"` go to Backend Dev.
- Cross-role tasks (e.g., "implement signup") fan out: BA confirms spec,
  SA picks pattern, Designer specs the screen, Backend Dev + Frontend
  Dev work in parallel, QA validates.
- PM maintains a dependency graph and can release tasks for parallel
  execution as soon as upstream tasks complete.

#### UI updates

- **Team panel** shows the full 8-agent org chart with real-time status.
- **Milestone view** shows the task DAG visually — green = done, yellow =
  in progress, blue = blocked, grey = pending — with arrows for
  dependencies.
- **Per-artifact authorship**: every file in the workspace tree shows
  the owning agent's icon.

### Effort

**M-L (6-8 weeks)** on top of Phase 5. Each agent is a constrained variant
of the same Agent base class with a different prompt and tool whitelist.

### Dependencies

- Phase 5 (the substrate)
- Roadmap Item 1 (AI-driven UI codegen) — Frontend Dev becomes meaningful
  with this; otherwise it produces placeholders like today

### User-visible outcome

The activity stream now reads like a real team's standup. The user can
see SA explaining a tradeoff, Designer producing wireframes, Backend Dev
implementing while Frontend Dev works in parallel, QA flagging issues.
Specialization is visible and explainable.

---

## Phase 7 — Domain capabilities

**Goal.** Make generated apps **production-aware** by domain — proper money
handling, audit trails, idempotency, role-based access, multi-entity
transactional service layers. This is what closes the "looks like code, is
not safe to deploy" gap.

### Deliverables

#### Spec schema extensions

`packages/spec_extractor/schema.json` grows:

```json
{
  "entities": [{
    "name": "Account",
    "fields": [
      {"name": "balance", "type": "money", "currency": "USD", "precision": 4},
      {"name": "owner_id", "type": "integer", "references": "User.id"}
    ],
    "audit": true,
    "constraints": [
      {"kind": "invariant", "expression": "balance >= 0"}
    ]
  }],
  "endpoints": [{
    "method": "POST", "path": "/transfers",
    "idempotency": {"header": "Idempotency-Key", "ttl_hours": 24},
    "requires_role": ["customer"]
  }],
  "services": [{
    "name": "TransferService",
    "operations": [{
      "name": "execute",
      "steps": [
        {"kind": "validate", "rule": "source.balance >= amount"},
        {"kind": "debit", "from": "source", "amount": "amount"},
        {"kind": "credit", "to": "destination", "amount": "amount"},
        {"kind": "audit", "event": "transfer.completed"}
      ],
      "atomic": true
    }]
  }]
}
```

#### Codegen updates

- `field.type = "money"` → `Decimal` with declared precision; never `float`.
- `endpoint.idempotency` → middleware that records and replays.
- `entity.audit: true` → emit `_audit_log` table + interceptor service.
- `endpoint.requires_role` → role-check dependency on the route.
- `services[].operations[]` → emit a service class with a transactional
  method; the route handler delegates to it rather than touching the DB
  directly.

These are codegen patches in `packages/generator/backend.py` plus matching
QA tests.

#### Per-task test execution

QA agent runs `pytest` after every task, not just at the milestone end.
A test failure on a task that previously passed is treated as a regression
— surfaced to the agent that broke it (via Backend Dev's mailbox), not
silently accepted.

This requires Roadmap Item 5 (Alembic migrations) so that schema changes
between tasks don't break the test DB.

#### AI-driven UI codegen

Roadmap Item 1 lands here. Frontend Dev becomes a real coder: spec.screen
+ entity + API client + ADR → real React component, gated by tsc and
spec-conformance.

#### Reconciler extensions

Reconciler now checks:

- Every money field is `Decimal`.
- Every audited entity has a matching audit-row write in its
  create/update/delete operations.
- Every role-protected endpoint has a role-check dependency.
- Every multi-step service operation is wrapped in a DB transaction.

These are *semantic* checks, not just structural.

### Effort

**L (8-12 weeks)**.

### Dependencies

- Phase 6
- Roadmap Items 1 (AI UI codegen) and 5 (Alembic)

### User-visible outcome

Generated apps cross from "scaffold" into "starting point a senior engineer
would seriously customize." Money is handled correctly, audit trails exist,
role-based access works, idempotency middleware is in place.

---

## Phase 8 — Domain expertise (RAG)

**Goal.** Give agents access to **curated domain knowledge** so they make
informed decisions without each user re-explaining banking, healthcare, or
SaaS patterns.

### Deliverables

#### New: `packages/knowledge/`

- `embedder.py` — wraps the embedding API of each provider.
- `vector_store.py` — pluggable backend (Postgres pgvector for self-host,
  Pinecone/Weaviate for SaaS). Per-domain collections.
- `retriever.py` — query construction, top-k retrieval, reranking.
- `tool.py` — exposes retrieval as an agent tool: `search_knowledge(query,
  domain) → list[Document]`.

#### Curated knowledge bases

Initial domain packs (each ~hundreds to thousands of documents):

- **General SWE**: design patterns, anti-patterns, common pitfalls, OWASP.
- **SaaS**: authentication best practices, billing, multi-tenancy patterns,
  feature flags, observability.
- **Fintech**: double-entry accounting, money math, idempotency patterns,
  payment-processor integration recipes, KYC tiering.
- **Healthcare**: HIPAA constraints, audit retention, PHI handling,
  consent flows.

Knowledge curation is real ongoing work; cannot be auto-generated reliably.
This is where domain experts are needed.

#### Per-agent retrieval

Each agent's system prompt gains: "Before making a decision, retrieve from
your knowledge base." SA retrieves architecture patterns. Backend Dev
retrieves implementation recipes. QA retrieves test patterns. The retrieved
docs are included in the LLM call as context.

#### Team presets

A "team preset" is a bundle of:

- Domain-specialized prompts for each agent
- A knowledge base assignment (`fintech` activates the fintech knowledge
  for SA, Backend Dev, and QA)
- Default spec.stack choices (e.g., fintech defaults to Postgres + audit:
  true on every entity)
- Mandatory milestone checkpoints with human review

PO offers the user a preset choice at project start: "What kind of app
are you building?" → applies the team.

### Effort

**L-XL (12-16 weeks, plus ongoing curation)**.

### Dependencies

- Phase 7 (the domain capabilities need to exist before knowledge of them
  is useful)

### User-visible outcome

The team feels like it knows what it's doing in a given domain. SA proposes
patterns that fit; Backend Dev writes idiomatic code for the vertical; QA
checks the right things. The user no longer has to specify every pattern in
the brief — implicit-requirements coverage improves dramatically.

---

## Phase 9 — Production hardening

**Goal.** Ready for paying customers depending on the system.

### Deliverables

#### Cost & token budgeting

- Per-project budget set at start. PM has a granular accounting tool:
  `record_spend(agent, tokens, cost)`. PM enforces caps and warns when
  a milestone approaches budget.
- Per-agent budgets so a runaway agent can't drain the project.
- Hard kill switches.

#### Audit trail

Every agent decision is logged with:

- Agent identity, model used
- Full system prompt + retrieved context + user message
- LLM response
- Resulting file changes (with diff)
- Rationale (the agent's own stated reasoning)

This goes into `workspace/audit/` and can be exported as a verifiable
log. For regulated industries, this is essential.

#### Observability

- Live OpenTelemetry traces of every message and tool call.
- Dashboards: per-agent latency, retry rates, token spend, deadlock
  detection.
- Alerting on stuck mailboxes, repeated escalations, budget overruns.

#### Multi-tenant deployment

- Tenant isolation at every layer (projects, mailboxes, workspaces).
- Per-tenant rate limits and quotas.
- SSO / SCIM for enterprise customers.

#### Per-preview reverse proxy

Roadmap Item 7 lands here — wildcard subdomain routing per preview, idle
reaping, many concurrent previews.

#### SDK & extensibility

- Public Python SDK so customers can write their own role-specialized
  agents (e.g., a customer's own "Compliance Reviewer" with internal
  policies).
- Plugin system for tools (e.g., Stripe integration plugin, OpenAPI
  importer plugin).

#### Compliance posture

- SOC 2 Type I/II preparation
- Data residency options
- GDPR/CCPA tooling
- Pen-tested deployment templates

### Effort

**L (12-16 weeks)** for the engineering work; SOC 2 etc. is a parallel
multi-month process.

### Dependencies

- Phases 5-8

### User-visible outcome

The product becomes deployable for real businesses, not just demos. SaaS
offering can take real money; enterprise customers can self-host with
confidence; regulated industries can use the audit trail for compliance.

---

## Total path

| Phase | Effort (1 eng) | Cumulative | What it unlocks |
|---|---|---|---|
| 5 — Runtime + minimal team | 8-12 weeks | 3 months | Conversational UX, multi-agent substrate |
| 6 — Specialized roles | 6-8 weeks | 5 months | Real org chart, parallelism |
| 7 — Domain capabilities | 8-12 weeks | 8 months | Production-aware generated code |
| 8 — Domain expertise (RAG) | 12-16 weeks | 12 months | Knows the verticals |
| 9 — Production hardening | 12-16 weeks | 15 months | Sellable to enterprises |

For a small team (3 engineers): roughly half the wall-clock — **8-9 months
to a sellable, vertical-aware multi-agent product.**

## What this plan does *not* achieve

To stay honest about the same limits raised earlier:

- **Banking-grade systems still require human engineering teams.** Phase 9
  gets you a viable starting point for a small bank MVP that a real team
  hardens; it does not get you a system you'd deploy without senior
  review.
- **Compliance is not automated.** SOC 2 prep is checklist work; the
  actual interpretation requires humans. Same for PCI, HIPAA, banking
  regs.
- **Reliability at extreme scale (1000+ tasks) still requires human
  milestone gates.** Multi-agent + private memory + milestone resets +
  RAG together raise the achievable scope to "tens of milestones,
  hundreds of tasks, with human approval between major chunks." Beyond
  that, the math of compounding LLM errors still wins.
- **Novel domain reasoning** — implementing a new payment scheme nobody
  has shipped yet, or interpreting fresh regulation — can't be automated.
  The agents work from patterns they've been given, not from first
  principles.

## Suggested first commit toward this

To start moving in this direction without committing to the full 15-month
plan, the **highest-leverage incremental step** is **Phase 5.1: the agent
runtime** (`packages/agent_runtime/`). It is:

- A self-contained piece of infrastructure
- Useful even without the full team (you could wrap today's pipeline as a
  single "Engineer" agent on the new runtime and immediately benefit from
  the durable mailbox + workspace + audit log)
- The hardest substrate to retrofit later

Estimated effort: 3-4 weeks for one engineer. Lands the foundation that
every subsequent phase builds on.

---

## Appendix: extended team roster

The 8-role team defined in Phases 5-6 is the minimum viable team. Real
software organisations have several more roles that become important as
the generated project's domain or scale grows. This appendix lays out the
complete roster mapped to the Avengers team for memorability — each role
is described by what it owns, what tools it needs, and when in a project's
lifecycle it activates.

### Core team (Phases 5-6) — always active

| Role | Codename | Owns | Activates |
|---|---|---|---|
| Product Owner | **Pepper Potts** | User chat, Requirements Brief | Start of every project |
| Product Manager | **Iron Man (Tony Stark)** | Roadmap, milestone priorities | After PO has a usable brief |
| Scrum Master | **Hawkeye (Clint Barton)** | Task dispatching, blockers, sprint cadence | Once a plan exists |
| Tech Lead / Architect | **Captain America (Steve Rogers)** | ADRs, code-review gate | Before any code is written |
| Business Analyst | **Vision** | `spec.json` — canonical structured spec | After PO produces brief |
| UX/UI Designer | **Scarlet Witch (Wanda Maximoff)** | Component specs, design system | After SA chooses frontend stack |
| Backend Engineer | **Doctor Strange (Stephen Strange)** | `backend/app/**`, data pipelines | Per backend task |
| Frontend Engineer | **Spider-Man (Peter Parker)** | `frontend/src/**` | Per screen, after Designer hands off |
| QA / SDET | **Hulk (Bruce Banner)** | Tests, bug reports | After each task and at milestone gates |
| DevOps / SRE | **Thor** | Dockerfiles, CI, deployment, uptime | At milestone packaging |

### Specialist team (Phases 7-8) — activated by spec

| Role | Codename | Activates when | Owns |
|---|---|---|---|
| Cybersecurity Engineer | **Black Widow (Natasha Romanoff)** | Spec has auth, payments, PII, or compliance flags | Threat model, security findings, pen-test results |
| Performance Engineer | **Quicksilver (Pietro Maximoff)** | Spec.non_functional includes performance SLOs | Load tests, profiling reports |
| Junior Developer | **Ant-Man (Scott Lang)** | Backlog of small isolated tasks under a senior's supervision | Small bug fixes, refactors, legacy-code spelunking |
| Technical Writer | **Maria Hill** | Spec.deliverables includes docs / public API | `docs/**`, API reference, user manuals |
| Compliance Officer | **Daredevil (Matt Murdock)** | Domain preset is regulated (banking, healthcare) | Compliance gap analysis, audit-readiness checklist |
| Data Scientist | **Shuri** | Spec includes analytics / ML features | Analytics models, data pipelines, ML inference services |

### Gap analysis vs the original Avengers-9 proposal

The original 9-role mapping (Iron Man PM, Cap Architect, Thor DevOps,
Widow Sec, Hulk QA, Spider-Man FE, Strange BE, Hawkeye SM, Ant-Man Jr)
is a strong foundation but is missing roles that real teams need:

1. **Product Owner / Pepper Potts** — distinct from Product Manager. PO
   is *user-facing*; PM is *strategy-facing*. In Scrum these are
   different roles, often filled by different humans. In our system the
   PO is the chat front-door; the PM holds the roadmap. Without
   splitting them, the PM's prompt would have to do two unrelated jobs
   (talking to the user *and* prioritising work) and would do both
   worse.
2. **Business Analyst / Vision** — translates the Requirements Brief
   into the structured Spec. In a single-person team this can be the
   PM's side gig; in a multi-agent system, the Spec is a critical
   artifact and deserves an owner. Without this role, PM and Backend
   Dev both end up doing the work informally and silently disagree on
   what was intended.
3. **UX/UI Designer / Scarlet Witch** — Spider-Man (Frontend Dev)
   *implements* UI; the Designer decides what the UI should be. Real
   teams have both. We model them as separate agents because the design
   artifact (`workspace/designs/`) is independently useful — Backend
   Dev consults it to understand what API shape the UI needs, QA
   consults it to write meaningful UI tests.
4. **Performance Engineer / Quicksilver** — QA (Hulk) covers
   correctness; Performance Engineer covers latency, throughput,
   load patterns. Different skill set, different tooling (k6, Locust,
   pprof, flamegraphs). Important for any project that promises
   non-trivial scale.
5. **Technical Writer / Maria Hill** — documentation is an artifact,
   not a side effect. For any product with a public API or end-user
   surface, generated docs are necessary. Hill is the "information
   control" character — keeps records, communicates state.
6. **Compliance Officer / Daredevil** — for regulated industries this
   role is non-negotiable. It's the agent that reads the spec + ADR +
   code through the lens of a specific regulatory regime (PCI-DSS,
   HIPAA, SOX, banking regs) and produces a gap analysis. Daredevil
   is canonically a lawyer in the MCU — natural fit.

The first three (PO, BA, Designer) are part of the *core* team and
ship in Phases 5-6 because nearly every non-trivial project needs them.
The last three (Performance, Technical Writer, Compliance) are
*specialists* that activate based on the project's spec — they're part
of Phases 7-8.

### Roles intentionally not included

- **Engineering Manager** — people management doesn't apply to agents.
- **Mobile Engineer** — folded into Frontend Engineer until mobile is a
  first-class output target.
- **DBA** — folded into Backend Engineer (Doctor Strange already
  handles data architecture) until database complexity warrants the
  split.
- **Customer Support** — post-launch concern, out of project scope.
- **Engineering Director / VP** — agents don't need managers of managers.
- **Release Engineer** — folded into DevOps (Thor).

### Optional UI theming: Avengers mode

The Avengers codenames are user-visible if a user opts into "**Avengers
mode**" in project settings. By default the UI shows functional names
(*"Backend Engineer is implementing `/accounts` router"*), which is
clearer in a B2B context. With Avengers mode on, the activity stream
reads (*"Doctor Strange is implementing `/accounts` router"*), which is
memorable and demoable. Same agents underneath, different display layer
— this is a useful product differentiator with essentially zero
engineering cost (a single boolean in project settings + a name-mapping
table in the frontend).
