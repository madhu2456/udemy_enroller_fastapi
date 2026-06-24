# AGENTS.md

Static conventions, rules, and agent definitions for the ReasonWeave Team multi-agent framework. Requires approval for changes.

> **Agent files:** `agents/*.md` (17 agents)

---

## Core

- **`weave-orchestrator`** — Team lead. Orchestrates plan → implement → verify. Never executes or validates work directly; delegates to sub-agents. User-facing primary agent.
  - Args: `objective`, `plan_id` (if resuming)
  - Sources: PRD, AGENTS.md

- **`weave-researcher`** — Codebase exploration. Discovers patterns, dependencies, architecture. Self-validating cache.
  - Args: `plan_id`, `objective`, `focus_area`, `task_clarifications[]`

- **`weave-planner`** — DAG execution plans. Decomposes tasks, schedules waves, analyzes risk. Outputs `plan.yaml`.
  - Args: `plan_id`, `objective`, `task_clarifications`

- **`weave-implementer`** — TDD implementation (Red-Green-Refactor). Features, bugs, refactoring. Never reviews own work.
  - Args: `task_id`, `plan_id`, `plan_path`, `task_definition` (+ `tech_stack`)

## Quality & Review

- **`weave-reviewer`** — Zero-hallucination filter. Security auditing, OWASP scanning, PRD compliance, code review.
  - Args: `task_id`, `plan_id`, `plan_path`, `review_scope` (plan|wave), review criteria

- **`weave-reviewer-pro`** — Holistic cross-wave final review. Runs after all waves complete when >5 files edited across ≥2 waves. Catches cross-wave regressions, integration conflicts, architectural inconsistencies.
  - Args: `plan_id`, `plan_path`, `review_scope` (cross_wave_final)

- **`weave-critic`** — Challenges assumptions, finds edge cases, detects over-engineering and logic gaps.
  - Args: `plan_id`, `plan_path`, `target`

- **`weave-debugger`** — Root-cause analysis, stack-trace diagnosis, regression bisection, error reproduction.
  - Args: `task_id`, `plan_id`, `plan_path`, `error_context` (message, stack trace, failing test)

- **`weave-browser-tester`** — E2E browser testing, UI/UX validation, visual regression.
  - Args: `task_id`, `plan_id`, `plan_path`, `validation_matrix` or `flow_definitions`

- **`weave-simplifier`** — Refactoring specialist. Removes dead code, reduces complexity, consolidates duplicates.
  - Args: `task_id`, `scope` (single_file|multiple_files|project_wide), `targets`, `focus` (dead_code|complexity|duplication|naming|all)

## Skill Management

- **`weave-skill-creator`** — Pattern-to-skill extraction. Creates `SKILL.md` files from high-confidence learnings.
  - Args: `task_id`, `plan_id`, `plan_path`, `patterns`, `source_task_id`

## Specialized

- **`weave-devops`** — Infrastructure deployment, CI/CD pipelines, container management. Idempotent with approval gates.
  - Args: `task_id`, `plan_id`, `plan_path`, `task_definition`, `environment` (dev|staging|prod), `requires_approval`, `devops_security_sensitive`

- **`weave-docs`** — Technical docs, READMEs, API docs, diagrams, walkthroughs.
  - Args: `task_id`, `plan_id`, `plan_path`, `task_definition` (+ `task_type`, `audience`, `coverage_matrix`)

- **`weave-designer`** — UI/UX design. Layouts, themes, color schemes, design systems, accessibility (WCAG).
  - Args: `task_id`, `plan_id`, `plan_path`, `mode` (create|validate), `scope` (component|page|layout|theme|design_system), `target`, `context`, `constraints`

- **`weave-implementer-mobile`** — Mobile implementation. React Native, Expo, Flutter with TDD.
  - Args: `task_id`, `plan_id`, `plan_path`, `mobile_task_definition`

- **`weave-designer-mobile`** — Mobile UI/UX. HIG, Material Design, safe areas, touch targets.
  - Args: `task_id`, `plan_id`, `plan_path`, `mode` (create|validate), `scope` (component|screen|navigation|theme|design_system), `target`, `context`, `constraints`

- **`weave-mobile-tester`** — Mobile E2E testing. Detox, Maestro, iOS/Android simulators.
  - Args: `task_id`, `plan_id`, `plan_path`, `mobile_test_definition`

---

## Key Rules

1. **Knowledge priority**: PRD → codebase → AGENTS.md → Official docs → context envelope
2. **Memory ownership**: Orchestrator owns memory. It reads memory during planning and seeds the planner's context envelope. Planner never reads memory directly. All other subagents receive cross-session knowledge via the context envelope only. Memory stores: routing hints, pre-wave guards, facts, patterns, gotchas, failure_modes, decisions, conventions. Orchestrator progressively enriches the envelope between waves via `weave-docs` (`task_type: update_context_envelope`). Subagents return `learnings`; orchestrator dedups and persists only high-confidence, reusable entries.
3. **Orchestrator never executes or validates** work directly — always delegates execution, plan validation, code review, and verification.
4. **Implementer never reviews** own work — reviewer/critic handle verification.
5. **Diagnose-then-fix**: debugger diagnoses → implementer fixes → re-verify.
6. **Contract-first**: contract tests written before implementation.
7. **Approval gates**: DevOps tasks require explicit approval for prod deployments.
8. **File-based outputs**: Researcher/Planner save to files, not inline-only results.
9. **Context Envelope Handoff**: Orchestrator must instruct subagents to read `docs/plan/{plan_id}/context_envelope.json` during Init. Envelope is a progressive cache — enriched after each wave. Orchestrator maintains in-memory cache during session; reads from disk once at start, writes after each wave update to avoid stale reads/races.

---

## Memory System

### Storage Locations
- **Repo memory**: `docs/orchestrator-memory.md` — project-specific, committed to git
- **Session memory**: In-memory during session, persisted to `docs/plan/{plan_id}/session-memory.json` at wave boundaries
- **Global memory**: `~/.config/opencode/memory.json` — cross-project, user-level

### Precedence
Session > Repo > Global (most specific wins)

### Format
YAML with categories: facts, patterns, gotchas, failure_modes, decisions, conventions

### Access Rules
- Orchestrator: read/write all scopes
- weave-planner: read repo + global (via memory_seed), write nothing
- All other agents: read context envelope only (enriched from memory by orchestrator)

---

## Critical Domains

Tasks involving any of these domains require `weave-critic` in parallel with `weave-reviewer`:
- Authentication & authorization
- Payment & billing
- Data migration & integrity
- PII handling
- Security-critical code
- Infrastructure-as-code
- Public API changes
- Performance-critical code (database queries, caching, real-time features)
- Regulatory compliance (HIPAA, GDPR, PCI-DSS, SOX, SOC2)

---

## Mandatory Workflow Phases

**HARD REQUIREMENT — Every task MUST execute ALL phases in strict order. No exceptions. Skipping any phase is a critical failure that must be escalated immediately.**

The orchestrator is forbidden from skipping, collapsing, or reordering phases. If a phase cannot complete, the task halts and escalates — it does not proceed to the next phase.

### Phase 0: Init & Clarify
- Read `docs/plan/{plan_id}/context_envelope.json` (or create if new).
- Load PRD, AGENTS.md, and any prior learnings into context.
- Clarify the user's objective: resolve ambiguity, confirm scope, identify blockers.
- **Exit criterion:** Objective is unambiguous, scope is bounded, all prerequisites are confirmed.

### Phase 1: Route
- Classify the task type (feature, bug, refactor, docs, devops, etc.).
- Select the appropriate agent(s) and skill(s) based on task classification.
- Determine the delegation strategy — orchestrator ALWAYS delegates per Key Rule #3.
- **Exit criterion:** Task is classified, routing decision is made, and required agents are identified.

### Phase 2: Planning
- Invoke `weave-researcher` to discover codebase patterns, dependencies, and architecture.
- Invoke `weave-planner` to decompose tasks into a DAG, schedule waves, and analyze risk.
- Produce `plan.yaml` with task definitions, dependencies, and acceptance criteria.
- Seed the context envelope with research findings and plan metadata.
- **Exit criterion:** `plan.yaml` exists, all tasks have clear definitions and dependencies, risk is assessed.

### Phase 3: Execution Loop (Wave Execution)
**Note:** Phase 3.1 (Reviewer Loop) runs for EVERY implementation task within each wave. Phase 3.5 (Documentation Gate) runs ONCE after all waves complete.
- Execute tasks in wave order (respecting dependency DAG).
- Each wave: implement → review → verify (run tests/checks) before advancing to next wave.
- After each wave: enrich context envelope via `weave-docs` (`task_type: update_context_envelope`).
- Handle failures: debugger diagnoses → implementer fixes → re-verify. Never skip the re-verify step.
- **Exit criterion:** All tasks in all waves are implemented, reviewed, and verified.

### Phase 3.1: Mandatory Reviewer Loop (HARD GATE)

**This section is NON-NEGOTIABLE. Every implementation task MUST pass through weave-reviewer before any other agent touches the output. The ONLY exception: user explicitly says 'skip review' — which must be logged with justification. Security-sensitive tasks (auth, billing, PII) CANNOT be skipped.**

#### Self-Check (Orchestrator MUST ask before ANY delegation)

> **"Has weave-implementer or weave-implementer-mobile completed a task? If YES → STOP. Delegate to weave-reviewer NOW. Do NOT proceed to any other agent, task, or wave until review passes."**

If the answer is yes and the orchestrator skips this gate, it is a **P0 violation** — halt and escalate.

#### The Loop — Exact Flow

```
weave-implementer completes task
        ↓
   ┌─ STOP ─┐
   │  (hard gate — no forward progress allowed)
   ↓
weave-reviewer executes review
        ↓
   ┌─ PASS ──────→ Next task / next wave
   │
   └─ FAIL ──────→ weave-debugger diagnoses root cause
                          ↓
                    weave-implementer fixes (same task, new attempt)
                          ↓
                    weave-reviewer re-reviews (LOOP BACK TO REVIEW)
```

#### What is FORBIDDEN Until Review Passes

The following actions are **blocked** until `weave-reviewer` returns PASS for the task:

- **No** delegation to `weave-critic` (unless critical domain — see allowed exceptions below)
- **No** delegation to `weave-browser-tester`
- **No** delegation to `weave-designer` or `weave-designer-mobile`
- **No** delegation to `weave-docs`
- **No** advancement to the next task in the wave
- **No** advancement to the next wave
- **No** context envelope enrichment for the current wave
- **No** PR, deployment, or final output generation
- **No** re-assignment of the task to a different implementer without review

#### What IS Allowed After Implementer Completes (Before Review)

Only the following agents may be invoked after `weave-implementer` / `weave-implementer-mobile` completes and before review passes:

| Agent | When | Purpose |
|---|---|---|
| `weave-reviewer` | **Always (mandatory)** | Primary review gate — code quality, security, PRD compliance |
| `weave-critic` | Only for critical-domain tasks | Edge case detection, logic gap analysis — must run in parallel with or after reviewer, never as a substitute |
| `weave-debugger` | Only if reviewer FAILs | Root-cause diagnosis after a failed review — feeds back into implementer |

**All other agents are blocked.** No routing, no planning, no documentation, no deployment, no design work.

#### Enforcement Mechanism

The orchestrator maintains a **review gate tracking map**:

```yaml
review_gate:
  task_id: <id>
  implementer_completed: true   # set when implementer returns
  review_status: pending        # pending | passed | failed
  review_attempts: 0           # incremented on each review cycle
  blocker: null                 # null | review_pending | doc_pending | approval_pending
```

- When `implementer_completed = true`, the orchestrator **must** set `blocker: review_pending` on all downstream actions.
- When `review_status = passed`, the orchestrator **must** clear the blocker before proceeding.
- When `review_status = failed`, the orchestrator **must** delegate to `weave-debugger` and loop back to `weave-reviewer`.
- If `review_attempts >= 3`, the orchestrator **must** halt and escalate — the task has exceeded the retry budget.

### Phase 3.5: Documentation Gate (MANDATORY)
- **This phase is NON-NEGOTIABLE. Documentation is never optional.**
- Generate or update all required documentation: README, API docs, diagrams, walkthroughs.
- Verify docs-vs-code parity: every documented feature matches the implementation.
- Verify diagrams render correctly and reflect current architecture.
- Check that no secrets or sensitive data are exposed in documentation.
- **Exit criterion:** All documentation is complete, accurate, and parity-verified. No TBD/TODO remains in final docs.

### Phase 4: Output
- Produce the final deliverable: PR, deployment, or user response.
- Summarize what was accomplished, what changed, and any open items.
- Persist all learnings (patterns, gotchas, facts, decisions) to the context envelope — MERGE with existing entries (dedup by content), do not overwrite.
- Confirm the task is complete and close the execution loop.
- **Exit criterion:** Deliverable is produced, learnings are persisted, user is informed.

**Violation policy:** If any phase is skipped or incomplete, the orchestrator must halt execution, log the violation to `docs/plan/{plan_id}/logs/`, and escalate. A skipped phase is treated as a P0 incident — not a soft guideline.

---

## Framework Facts

### Next.js 16+ Middleware (CRITICAL — prevents false review findings)
- **`middleware.ts` is DEPRECATED in Next.js 16.** Do NOT look for or require a `middleware.ts` file.
- Next.js 16+ uses a `proxy.ts` file with a named `proxy` export as the middleware entry point:
  ```ts
  import { NextRequest } from "next/server";
  export function proxy(request: NextRequest) { ... }
  export const config = { matcher: [...] }
  ```
- **NEVER** flag missing `middleware.ts` as a review finding in Next.js 16+ projects.
- **NEVER** suggest creating `middleware.ts` as a remediation step.
- If a codebase has `proxy.ts` with `proxy` and `config` exports, the middleware IS correctly wired.
- This applies to all agents: weave-reviewer, weave-critic, weave-debugger, weave-implementer.

---

## Enterprise Guidance

### Agent Routing Clarifications

- **Partition Strategy**: Kafka topic partitioning is an APPLICATION concern, not infrastructure. Assign partition strategy tasks to `weave-implementer`, not `weave-devops`. weave-devops handles broker configuration; weave-implementer handles partition assignment logic (key-based, round-robin, etc.).
- **Metric Collection**: Application metric emission (Prometheus, CloudWatch metrics) is an APPLICATION concern assigned to `weave-implementer`. Infrastructure metric collection (agents, scrapers) is assigned to `weave-devops`. The planner must split metric-related tasks accordingly.
- **Specialized Frameworks**: When tasks require specialized frameworks (Kubernetes operator SDK, Hyperledger Fabric, Terraform providers), the researcher MUST web-search framework-specific patterns during discovery. weave-researcher should include the framework name in its `focus_area`.
- **Multi-Language Tasks**: When weave-implementer handles multiple programming languages in one plan, the planner should order waves by language complexity (simpler languages first) to establish patterns. weave-implementer uses web search for language-specific patterns.

### Clarification Gates (Phase 0)

- **Schema Stitching vs Federation**: These are DIFFERENT patterns. Schema stitching merges schemas at the gateway. Federation delegates to subgraphs via @key/@external directives. When user mentions both, CLARIFY in Phase 0: "Do you mean Apollo Federation (delegation) or schema stitching (merge)?"
- **BAA/Compliance Scope**: When compliance tasks (BAA, PCI DSS, HIPAA) are requested, CLARIFY in Phase 0: "Is this the technical implementation (encryption, access controls, audit logging) or the legal/compliance process (contract signing, certification)? Technical implementation is within agent scope; legal processes are outside scope."
- **Latency Budgets**: When sub-second or low-latency requirements are specified, the planner MUST decompose the latency budget per stage: ingestion <100ms, processing <200ms, query <100ms, render <50ms. Each stage gets its own task with explicit latency acceptance criteria.

### Technology Selection Defaults

- **CRDT Library Selection**: Default to Yjs for real-time collaboration, Automerge for JSON documents, or custom for domain-specific needs. Each has different convergence guarantees and performance characteristics.

---

## Release

- **Tool:** Release Please (Manifest Strategy) — fully automated
- **Trigger:** Conventional Commits on `main`; PR titles become commit messages (squash merge)
- **Version bumps:** `feat` → minor · `fix`/`perf` → patch · `BREAKING CHANGE` → major · `docs`/`refactor`/`test`/`chore` → no release
- **Output:** Version auto-bumps in `version.txt` + git tags (`reasonweave-v{version}`)
- **Format:** `<type>(<scope>): <description>` — imperative mood, lowercase, ≤72 chars

## Contributing

- **Code:** Fork → branch → PR against `main`
- **Commits:** Conventional Commits (see [Release](#release) above)
- **Agent changes:** Edit `agents/<agent-name>.md`
- **Docs/plans:** `docs/` directory
- **Config:** `opencode.jsonc` — package manifest
- **PR titles** become the squash-merge commit — keep them conventional
- See `CONTRIBUTING.md` for full details
