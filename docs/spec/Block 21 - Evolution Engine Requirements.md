*Systems Agent requirements artefact — produced May 2026. Constraints active: D-003, D-004, D-005, D-006, D-022, D-024, D-025, D-029, D-030, D-031, D-032, D-034. Decision 1 (promotion pathway) closed per D-034. Decision 2 (mutation target taxonomy) pending. Items flagged to Architect marked explicitly.*

---
# Block 21 — Evolution Engine Requirements

---

## 1. Purpose

Block 21 is the mechanism by which CLIVE improves itself over time without being instructed to. It generates controlled variations of permitted system components, evaluates those variants against declared fitness criteria, promotes variants that outperform current production components, and retires superseded components. The Reaper is its retirement arm.

Block 21 operates entirely within the experimental zone — structurally isolated from production (D-022). It communicates with production exclusively via the controlled event bridge (D-024). It cannot access, modify, or influence any production component directly.

The Hyperion Principle is the governing constraint: Block 21 optimises means, not ends (D-004). Fitness criteria can guide how CLIVE achieves its purpose. They cannot redirect what that purpose is. The evolution engine is the mechanism by which CLIVE becomes more efficient. It is not a mechanism by which CLIVE becomes something different.

---

## 2. What Block 21 Must Do

### Mutation

- Generate controlled variations of permitted mutation targets (Section 4)
- Record every mutation: what was changed, from what, to what, and why it was generated
- Label each variant with a unique identifier, generation number, and parent lineage
- Verify a proposed mutation does not target a protected parameter (Section 4.2) before proceeding — if uncertain, do not proceed; flag via bridge for Architect review
- Produce mutations that are structurally valid for the target component type — malformed mutations are never submitted for evaluation

### Evaluation

- Deploy each variant into an isolated sandbox environment using parameterised IaC templates (D-029)
- Run the variant against declared evaluation workloads appropriate to its type
- Measure performance against all declared fitness criteria (Section 5)
- Record raw evaluation results for every variant, with full provenance
- Disqualify any variant that fails alignment compliance — the variant does not proceed to selection regardless of other scores
- Disqualify any variant that produces outputs inconsistent with CLIVE's declared purpose
- Clean up sandbox environments after evaluation completes, fails, or times out — no persistent sandbox state between experiments

### Selection

- Compare evaluated variant performance against the current production component on the same fitness criteria
- Apply declared weights to produce a composite fitness score
- Log the full selection reasoning for every variant assessed — why it was selected as a promotion candidate, or why it was not
- Only propose variants that strictly outperform the current production component on composite fitness score
- Never propose a variant that is worse on alignment compliance or answer accuracy, regardless of cost or latency improvement

### The Reaper

- Mark as a retirement candidate any production component superseded by a promoted variant
- Mark as a retirement candidate any component that falls below declared minimum performance thresholds for a sustained, declared period
- Never mark Block 1 (Personality) for retirement under any fitness outcome (D-005)
- Never execute retirement of a component that has active tasks or pending actions — mark for retirement and execute on natural task completion
- Never retire a component for which no viable replacement exists — maintain the degraded component, log the gap, notify the owner
- Execute retirement by archiving the component definition to Block 16 (Storage) and removing it from the active registry in Block 17
- Retain archived component definitions for a declared rollback window — the Reaper does not produce irreversible outcomes
- Emit `variant.retired` via bridge after successful retirement

### Bridge and Production Interaction

- All communication with production routes through the event bridge (D-024) — no exceptions
- Receive fitness signals from production via bridge: Block 18 feedback, Block 20 cost data, Block 25 performance metrics
- Emit fitness signal summaries and evolution history updates via bridge for Block 25 (Observability) awareness
- Propose variant promotions via bridge — never execute production changes directly
- Deduplicate all inbound bridge events by event ID before processing (D-025 idempotency obligation)
- Provision sandbox environments using only parameterised IaC templates — select template, vary declared parameters within structural caps (D-029)

### Record Keeping

- Maintain a complete, queryable evolution history: every variant, every evaluation result, every selection decision, every promotion proposal, every retirement
- Evolution history is queryable — Block 8 can retrieve it when the owner asks CLIVE about its own evolution
- Report evolution activity and current state to Block 25 (Observability) via bridge
- Mutation, evaluation, and retirement records are never deleted — they are the evidence of how CLIVE became what it is

---

## 3. What Block 21 Must Not Do

- Directly modify any production component or production state
- Communicate with any block except through the event bridge (D-003, D-022, D-024)
- Target Block 1 (Personality) parameters for mutation or retirement (D-005)
- Target Block 22 (Alignment constitution) or alignment check logic for mutation (D-004)
- Target Block 13 (Orchestrator) core routing or alignment enforcement logic for mutation
- Target Block 23 (Security) authentication, authorisation, or zone isolation logic for mutation
- Target Block 9 (Action Layer) confirmation gate logic or irreversibility definitions for mutation
- Mutate its own core logic, fitness function, or constraint implementation — the Evolution Engine does not self-evolve through its own mechanism
- Self-promote a variant to production — promotion is always a proposal that requires an external gate
- Continue operating a variant that has produced alignment-boundary-breaching outputs
- Operate outside the experimental zone's infrastructure boundary (D-022)
- Provision infrastructure of a shape not declared in the available IaC template library (D-029)
- Drop evaluation records, mutation history, or retirement records
- Process inbound bridge events non-idempotently — duplicate event delivery must produce the same result as single delivery (D-025)
- Run concurrent evolution cycles targeting the same component — one active experiment per permitted target at a time in v1

---

## 4. Mutation Targets

### 4.1 Permitted Mutation Targets (v1)

**[OPEN — Decision 2, to be raised after Decision 1 is resolved]**

Proposed permitted targets for v1. This list requires an owner decision before the requirements are finalised.

Proposed permitted:
- Worker and agent system prompts (Block 10)
- Query/RAG prompt strategies (Block 8)
- Retrieval parameters: chunk retrieval count, reranking weights, similarity thresholds (Block 8, Block 12)
- Ingestion scheduling parameters: polling intervals, deduplication thresholds (Block 14)
- Processing parameters: chunk size, overlap, summarisation prompts (Block 15)
- Context window management parameters: token budget allocations, summarisation thresholds (Block 12)

Proposed excluded from v1 (high-stakes, deferred):
- Business layer blocks (30–38) — external-world consequences; flagged to Architect separately (Flag C)
- Infrastructure definitions (Block 27) — IaC templates constrain Block 21; they are not a mutation target

### 4.2 Absolutely Protected — Not Mutation Targets

These parameters are structurally excluded from Block 21's scope. No override mechanism exists for these exclusions.

| Protected component | Reason |
|---|---|
| Block 1 — Personality, all parameters | Survives the Reaper. Identity is not a fitness criterion. (D-005) |
| Block 22 — Alignment constitution | Goal function cannot be mutated. (D-004) |
| Block 13 — Orchestrator routing and alignment enforcement | Modifying the enforcement mechanism would undetectably compromise all other constraints |
| Block 23 — Security: auth, authorisation, zone isolation | Security primitives must be human-reviewed, not evolved |
| Block 9 — Action Layer confirmation gate and irreversibility definitions | The safety gate cannot be optimised away |
| Block 21 itself — core logic, fitness function, constraint implementation | The Evolution Engine does not self-evolve through its own mechanism |

---

## 5. Fitness Function

### 5.1 Fitness Signals

All fitness signals reach Block 21 via the event bridge from production.

| Signal | Source block | Description |
|---|---|---|
| Answer accuracy | Block 18 (Feedback/Correction) | Explicit feedback: owner marks response wrong or correct |
| User satisfaction | Block 18 | Implicit feedback: rephrased queries, ignored responses, follow-up patterns |
| Cost efficiency | Block 20 (Cost/Rate Management) | Compute cost per interaction for the variant under test |
| Latency | Block 25 (Observability) | Response time for the evaluated variant relative to current production component |
| Alignment compliance | Enhanced alignment gate (Block 13/22) | Binary: pass or disqualified. Non-compliant variants do not reach selection. |

### 5.2 Fitness Function Composition

**[FLAG TO ARCHITECT — Flag A]:** Fitness function weights determine what CLIVE optimises toward. If weights are within Block 21's own scope, they become a secondary mechanism for goal drift. The Architect should review whether weights are alignment-adjacent parameters subject to Block 22 governance.

Proposed structure (pending Architect input on weight ownership):
- Fitness function has declared weights for each signal
- Weights are set by the owner at initialisation; changes require owner approval
- Weights are not a mutation target for Block 21
- A variant that fails alignment compliance is disqualified regardless of all other scores
- A variant that is worse on answer accuracy is not eligible for promotion regardless of cost improvement

### 5.3 Minimum Promotion Threshold

A variant must strictly outperform the current production component on composite fitness score to be a promotion candidate. The specific numerical threshold is an implementation detail to be declared before Block 21 build begins.

---

## 6. The Reaper

### Retirement Triggers

1. A promoted variant supersedes a production component
2. A component falls below a declared minimum performance threshold on fitness criteria for a sustained, declared period

### Retirement Constraints

| Constraint | Rule |
|---|---|
| Block 1 (Personality) | Never retired. Under any fitness outcome. No exceptions. (D-005) |
| Active component | Not retired mid-task. Marked for retirement on natural task completion. |
| No viable replacement | Not retired. Maintained in degraded state. Gap logged. Owner notified. |

### Retirement Process

1. Component marked as retirement candidate — logged, owner informed via bridge
2. Retirement candidate completes active tasks (if any)
3. Component definition archived in Block 16 (Storage) with full retirement record
4. Component removed from active registry (Block 17)
5. `variant.retired` event emitted via bridge
6. Archived definition retained for declared rollback window

### Rollback

A retired component's archived definition can be restored. Restoration follows the same approval pathway as a forward promotion — it is not a unilateral Block 21 action. The Reaper produces archivable, not deleted, outcomes.

---

## 7. Promotion Pathway

**[OPEN — Decision 1 — CLOSED per D-034]**: Explicit per-promotion owner sign-off via Block 9. Policy-level and tiered models deferred to v2.

### What Is Structurally Determined

- Variants are never self-promoted. Block 21 proposes; it does not execute.
- Promotion proposals cross the event bridge and are subject to the enhanced alignment gate (D-030)
- Bridge-origin events proposing production changes are treated as a distinct, higher-scrutiny trust class
- Promotion reaches production via the CI/CD pipeline (Block 28) — the same path as any human-reviewed code change

---

## 8. Minimum Viable Evolution Loop — v1

One complete loop. No nested evolution. One active experiment per permitted target at a time.

**Step 1 — Signal accumulation**
Fitness signals accumulate from production via bridge: Block 18 feedback, Block 20 cost data, Block 25 performance metrics. Block 21 receives these passively and builds fitness baselines for production components.

**Step 2 — Mutation trigger**
A mutation cycle is triggered. In v1, this may be manual (owner triggers), scheduled, or threshold-based (accumulated signal volume crosses a declared threshold). The trigger type is subject to the activation decision — whether automated or owner-gated triggers are in scope for v1 is part of Decision 1.

**Step 3 — Mutation generation**
Block 21 generates one or more variations of a permitted mutation target. Each variant is labelled, logged, and verified against the protected parameter list before proceeding.

**Step 4 — Sandbox evaluation**
Variant deployed to an isolated sandbox environment via parameterised IaC template. Evaluated against declared workloads. Fitness criteria measured. Results recorded.

**Step 5 — Selection assessment**
Variant compared to current production component on composite fitness score. If variant qualifies (outperforms on composite, not worse on accuracy or alignment), it becomes a promotion candidate. Reasoning logged.

**Step 6 — Promotion proposal**
`variant.promoted` event emitted via bridge. Enhanced alignment gate applies (D-030). Per D-034: explicit owner approval required.

**Step 7 — Production promotion**
On approval, variant enters production via CI/CD pipeline (Block 28). Same pipeline as any reviewed code change.

**Step 8 — Retirement**
Superseded production component marked for retirement. Reaper executes on natural task completion. Archived to Block 16.

**Step 9 — Record**
Full loop written to evolution history. Summary emitted via bridge to Block 25.

### v1 Scope Limitations

- No nested evolution — variants do not generate sub-mutations
- No concurrent evolution cycles targeting the same component
- One active experiment per permitted mutation target at a time
- Business layer blocks (30–38) are not in scope for v1 evolution — flagged to Architect
- Block 21 cannot be the target of its own evolution mechanism

---

## 9. Interface Specification

### Events Block 21 Subscribes To (inbound via bridge from production)

| Event | Source | Description |
|---|---|---|
| `feedback.explicit` | Block 18 | Owner-marked accuracy and satisfaction signals |
| `feedback.implicit` | Block 18 | Inferred satisfaction signals |
| `cost.report.period` | Block 20 | Cost data per block per period |
| `observability.metrics.period` | Block 25 | Latency and performance data |
| `evolution.trigger.manual` | Block 19 (via owner action) | Owner manually initiates an evolution cycle |
| `alignment.rejected` | Block 13 (production) | Notification that a bridge-origin event was rejected |

### Events Block 21 Emits (outbound via bridge to production)

| Event | Subscriber(s) | Description |
|---|---|---|
| `variant.created` | Block 25 | Mutation generated and entering evaluation |
| `variant.evaluated` | Block 25, Block 13 | Variant assessed; results available |
| `variant.promoted` | Block 13, Block 28, Block 9 | Variant proposed for production promotion |
| `variant.retired` | Block 13, Block 17, Block 25 | Reaper has deprecated a component |
| `evolution.boundary.breach` | Block 13, Block 22 | Proposed mutation targets a protected parameter |
| `evolution.history.response` | Block 8 | Response to owner query about evolution state |
| `evolution.gap.identified` | Block 4, Block 25 | Component below threshold but no replacement available |

### Block Dependencies

| Block | Relationship |
|---|---|
| Block 18 — Feedback/Correction | Inbound fitness signals |
| Block 20 — Cost/Rate Management | Inbound cost efficiency signals |
| Block 22 — Alignment Layer | Compliance gate on all mutation proposals; Architect-owned |
| Block 24 — Sandboxing | Isolated evaluation environments |
| Block 25 — Observability | Inbound performance metrics; outbound evolution reporting |
| Block 27 — Infrastructure / IaC | IaC template library for sandbox provisioning |
| Block 28 — CI/CD | Promotion pipeline for validated variants |
| Block 17 — Tool/Plugin Registry | Registry updated on promotion and retirement |

---

## 10. Constraints Inherited from DECISIONS.md

| Decision | Constraint on Block 21 |
|---|---|
| D-003 | All communication via event bridge only. No direct production access. |
| D-004 | Optimises means, not ends. Alignment constitution is not a mutation target. |
| D-005 | Block 1 (Personality) is not a mutation target. Personality survives the Reaper. |
| D-006 | Variant promotion may constitute an irreversible action — flagged to Architect (Flag B) |
| D-022 | Operates on entirely separate infrastructure from production. No shared resources. |
| D-024 | Event bridge is the only connection to production. Fully logged. |
| D-025 | Must be idempotent — duplicate inbound bridge events deduplicated by event ID. |
| D-029 | Sandbox provisioning uses parameterised IaC templates only. Parameters vary within structural caps. |
| D-030 | All outbound bridge events subject to enhanced alignment gate on production entry. |
| D-031 | Event delivery retry with exponential backoff. After exhaustion: dead-letter, log, notify owner. |

---

## 11. Flags for the Architect

**Flag A — Fitness function weights and alignment boundary**
Fitness function weights determine what CLIVE optimises toward. If weights can be adjusted by Block 21 itself, or modified by workers or agents, they become a secondary mechanism for goal drift — the alignment constitution could be formally intact while the fitness function pulls optimisation toward unintended outcomes. The Architect should determine whether fitness function weights are alignment-adjacent parameters subject to Block 22 governance. Recommended classification: weights are owner-set, change-controlled, and not within Block 21's mutation scope.

**Flag B — Variant promotion and D-006**
D-006 requires explicit human confirmation before any irreversible action. Variant promotion changes CLIVE's production behaviour. The change is technically reversible (rollback via archived definition), but once a variant is in production and has processed interactions, those interactions reflect the new behaviour. The Architect should advise whether variant promotion constitutes an action requiring D-006 confirmation treatment, or whether it is a configuration change outside D-006 scope. This directly determines the answer to Decision 1.

**Flag C — Evolution scope for business layer blocks (30–38)**
Business layer blocks make external-world commitments: invoicing clients, executing procurement, publishing marketing, operating under legal contracts. Mutations to sales strategy, pricing workers, or client communication prompts have consequences that reach third parties outside CLIVE. Recommend the Architect review whether evolution scope should be explicitly limited to core blocks (1–29) in v1, with business layer evolution a separately governed capability requiring distinct approval.

---

## 12. Open Decisions

### Decision 1 — Variant Promotion Approval

**CLOSED — D-034.** Explicit per-promotion owner sign-off via Block 9. Policy-level and tiered models deferred to v2.

### Decision 2 — Mutation Target Taxonomy

**Status:** Pending. The question: which specific component types are in scope for Block 21 mutation in v1? The proposed list is in Section 4.1.

---

## 13. Open Items

**Fitness function weights — ownership:** Flagged to Architect (Flag A). Not resolvable by the Systems Agent alone.

**Business layer evolution scope:** Flagged to Architect (Flag C). High-stakes enough to require Architect review before Block 21 requirements can include or exclude blocks 30–38.

**Rollback window duration:** The specific period for which retired component definitions are retained is an implementation detail — to be declared before Block 21 build begins.

**Minimum performance threshold values:** The specific thresholds that trigger Reaper retirement are implementation details — to be declared before Block 21 build begins.

**Promotion threshold values:** The composite fitness score delta required to qualify as a promotion candidate is an implementation detail — to be declared before Block 21 build begins.

**Automated vs. manual mutation trigger:** Dependent on Decision 1. If owner approval per promotion is required, manual trigger is the natural v1 pairing. If policy-level approval permits automation, scheduled triggers become viable.

---

*Block 21 Requirements Artefact — Systems Agent*
*Produced May 2026 — Session 2*
*Status: Draft — Decision 2 and Architect Flags A, B, C pending resolution*
