*Infrastructure Agent requirements artefact — produced May 2026. Complete. Decisions applied: D-002, D-003, D-004, D-005, D-006, D-008, D-017, D-018, D-019, D-022, D-023, D-024, D-025.*

---
# Block 27 — Infrastructure / IaC: Requirements Artefact

**Agent:** Infrastructure Agent
**Status:** Complete
**Session:** Block 27 requirements deepening, May 2026

---

## Purpose

Block 27 — Infrastructure / IaC is the capability that makes every other block real. It defines, provisions, and manages all infrastructure consumed by CLIVE across all environments, as code. Nothing is hand-built. Nothing is undocumented. Every environment can be destroyed and rebuilt from the IaC definition alone. Block 27 is not a deployment mechanism — it is the system's memory of what it is made of, and the control plane through which that composition changes in a safe, auditable, and reversible way. It provisions the substrate on which the Central Orchestrator runs, the storage on which knowledge lives, the event bridge through which evolution is contained, and the sandbox environments in which the system improves itself. It does all of this without making technology choices at the requirements stage — those choices follow when requirements are understood, and are recorded in DECISIONS.md before any implementation begins.

---

## Requirements

### What Block 27 Must Do

- Define all infrastructure as code. No environment depends on undocumented manual steps. If it is not in code, it does not exist.
- Provision and manage three structurally distinct environments: development, production, and experimental.
- Ensure any environment can be destroyed and rebuilt from the IaC definition alone, with no external dependencies on undocumented state.
- Maintain consistency between development and production — same IaC codebase, different configuration values. Structural differences between environments are a defect.
- Version and attribute every infrastructure change: who proposed it, when, what changed, what the previous state was.
- Require every infrastructure change to be reviewed before application. The planned change is the artifact under review, not the post-apply state.
- Support rollback for every infrastructure change applied through the pipeline. The previous state must be recoverable.
- Enforce Block 7 trust zone boundaries at the infrastructure level — not only as policy, but as structural separation. The experimental zone cannot reach production storage at the network or access layer.
- Tag every provisioned resource at provisioning time with: owning block, environment, zone, and operational category (compute, storage, network, secrets, observability). Untagged resources are a pipeline compliance failure.
- Expose a programmatic provisioning surface that Block 13 can invoke via the event bus, enabling the Evolution Engine (Block 21) to trigger sandbox provisioning without human initiation.
- Maintain a catalogue of approved sandbox IaC templates. Each template declares compute range (min/max), storage capacity, duration limit, and network access constraints.
- Validate all programmatic provisioning requests against the template catalogue before they reach the experimental environment. Requests outside declared template parameters are rejected and logged.
- Enforce a structural cap on total concurrent sandbox instances, declared in IaC and not enforced only by application logic.
- Tear down sandbox instances automatically on duration expiry or experiment completion signal.
- Provision the cross-environment event bridge as independent infrastructure — not part of production, not part of experimental — with two declared event flows and full logging of all traffic crossing in either direction.
- Enforce at the bridge what may cross it: only structured event payloads conforming to a declared schema. No raw knowledge, no owner personal data, no production credentials, no direct storage references.
- Provision storage infrastructure capable of enforcing write-once immutability for Block 16's audit log at the storage layer, not only at the application layer. The specific immutability model is a Block 16 requirement to be specified when the Knowledge Agent is activated.
- Provision secrets management infrastructure. All credentials are held there. They are never in IaC definitions, environment variables visible in logs, or application code.
- Give all credentials a declared maximum lifetime at provisioning time. Automate rotation where the infrastructure supports it.
- Provide cost visibility at the block level via mandatory resource tagging, feeding Block 20 (Cost / Rate Management) through Block 25 (Observability).
- Apply a three-tier governance model to infrastructure changes: routine, significant, and boundary-class (see Infrastructure Change Governance section).
- Route boundary-class changes through Block 9 (Action Layer) confirmation gate before application. Timeout means no application.
- Implement point-in-time recovery for production storage, with recovery bounded to a declared maximum data loss window. The window value is configuration, not hardcoded.
- Emit structured observability events to Block 13 for routing to Block 25 for all infrastructure state changes, sandbox lifecycle events, bridge activity, and cost threshold events.
- Maintain IaC definitions for production and experimental environments in separate codebases with separate change pipelines. A change committed to one environment's IaC cannot be applied to another's infrastructure without an explicit promotion step.

### What Block 27 Must Not Do

- Name specific databases, cloud platforms, infrastructure tools, CI/CD platforms, monitoring services, or edge hardware in requirements or IaC definitions at the specification stage. Technology choices are made after requirements are understood and recorded in DECISIONS.md (D-002).
- Allow any environment to be modified by a path other than the IaC pipeline. Manual changes to production are a defect, not a shortcut.
- Allow the experimental environment to share infrastructure, network, or accounts with the production environment. Isolation is structural, not policy-only (D-022).
- Allow the bridge to carry raw knowledge, owner personal data, production credentials, or direct storage references in either direction.
- Provision experimental environment credentials with access to production secrets infrastructure.
- Allow the pipeline to modify its own underlying infrastructure through an automated run. Changes to pipeline infrastructure travel through a separate human-initiated process.
- Apply a failed or partial infrastructure change without stopping, logging, and requiring a corrected proposal.
- Accept a provisioning request from Block 21 that specifies infrastructure outside declared template parameters.
- Allow sandbox instances to persist beyond their declared duration limit without escalating to owner notification.
- Provision indefinite credentials. All credentials have a declared maximum lifetime.
- Allow secrets to appear in logs, IaC definitions, or application code under any circumstance.
- Restore a backup of the audit log infrastructure without owner confirmation and Architect review. This is a boundary-class irreversible action.
- Modify the alignment constitution or the alignment layer. Block 22 is owned by the Architect (D-012).

---

## Environment Definitions

### Production

The running system serving the owner. Contains the owner's knowledge, actions, and personal data. All production blocks — the Central Orchestrator (Block 13), the event bus, storage (Block 16), workers (Block 10), query layer (Block 8) — run here. No direct human access to the underlying infrastructure outside of declared operational procedures. Infrastructure changes reach production only through the IaC pipeline after passing the full validation sequence and, for significant or boundary-class changes, human review and owner awareness.

### Development

Where CLIVE is built and tested before any change reaches production. A permanent standing environment — not spun up on demand — available at all times to validate changes before the production pipeline is unblocked. Structurally identical to production: same IaC codebase, environment-specific configuration values only. Structural differences between development and production are a defect. Development contains no owner knowledge or personal data. No disaster recovery applies. Development environments are rebuilt from IaC and re-seeded with test data as needed.

### Experimental

Hosts Block 21 (Evolution Engine) variant testing and Block 24 (Sandboxing) execution. Separate infrastructure from production — separate network, separate accounts or projects, no shared resources (D-022). Connected to production only via the event bridge. No access to production knowledge, state, owner data, or secrets. Sandbox environments within this zone are ephemeral: provisioned per experiment from the approved template catalogue, torn down on completion, expiry, or failure. Experimental storage is ephemeral by design. No disaster recovery applies to the experimental environment.

---

## Isolation Requirements

### Experimental / Production Isolation

**Requirement:** The experimental environment has no read or write access to production knowledge or state. Isolation is structural, not policy-only.

**How it is met:**

- Separate infrastructure accounts or projects for experimental and production — no shared compute, storage, or network (D-022).
- The event bridge is the only connection between environments. It is provisioned as independent infrastructure, belonging to neither environment.
- Bridge traffic is restricted to structured event payloads conforming to a declared schema. The bridge rejects and logs anything outside the schema.
- Experimental environment credentials are scoped to the experimental environment only. They have no path to production secrets infrastructure.
- Bridge credentials have a shorter maximum lifetime than static infrastructure credentials.
- All bridge traffic — inbound and outbound — is logged. No unlogged crossing exists.
- Changes to the bridge or to environment isolation boundaries are boundary-class changes requiring explicit owner confirmation before application.

### Trust Zone Isolation (Block 7)

**Requirement:** Block 7 trust zone boundaries — personal, work, client, experimental — are enforced at the infrastructure level, not only by application access controls.

**How it is met:**

- Each trust zone is provisioned with structurally isolated storage. Zones do not share storage infrastructure.
- Network segmentation prevents cross-zone traffic outside of declared event bus paths.
- Every provisioned resource is tagged with its zone at provisioning time. Tag compliance is enforced in the pipeline.
- Cross-zone access, where explicitly permitted by Block 7, is routed through Block 13 (Central Orchestrator) via the event bus — not through shared infrastructure.

### Audit Log Immutability

**Requirement:** The infrastructure hosting Block 16's audit log must enforce write-once immutability. Restoration of audit log infrastructure is a boundary-class irreversible action.

**How it is met:**

- Block 27 provisions storage infrastructure with write-once capability at the storage layer.
- The specific immutability model (storage-layer enforcement, access control layer, or both) is a Block 16 requirement. Block 27 commits to provisioning infrastructure that can satisfy whatever model Block 16 specifies.
- Deprovisioning or modifying audit log infrastructure requires explicit owner confirmation via Block 9, and Architect review, before any change is applied.
- The audit log is backed up separately from general storage recovery. Its restoration procedure is governed independently and never overwrites audit log entries without confirmation.

---

## Disaster Recovery Requirements

**Scope:** Production storage (Block 16) is the recovery target. Compute and infrastructure are rebuilt from IaC definitions — they are not snapshotted, because IaC is the source of truth for infrastructure shape.

**Model:** Point-in-time recovery. Production storage state is captured at a frequency sufficient to bound data loss to a declared maximum window. The window value is a configuration parameter, not a hardcoded infrastructure property — it can be adjusted without changing IaC structure.

**Recovery point objective:** Data loss is bounded to the declared window. This value must be set before production is operational.

**Audit log recovery:** Excluded from standard recovery procedures. The audit log is immutable-class infrastructure. Restoration of a backup that would overwrite audit log entries is a boundary-class irreversible action requiring owner confirmation and Architect review.

**Experimental environment:** No disaster recovery. Experimental storage is ephemeral by design. If an experimental environment is lost, experiments are re-run. This is expected behaviour.

**Development environment:** No disaster recovery. Development contains no owner knowledge or personal data. Rebuilt from IaC and re-seeded with test data as needed.

**Scope exclusion:** Block 27 does not manage business continuity or availability beyond data recovery. Consistent with D-023, the Central Orchestrator (Block 13) runs as a single instance with no redundancy in v1. Brief downtime is acceptable. A distributed orchestrator is a future consideration.

---

## IaC Pipeline Requirements

### Change Validation Sequence

All infrastructure changes must pass the following sequence before reaching production, in order:

1. **Plan review.** The IaC tooling produces a complete description of what will change before any change is applied. The plan is the artifact under review. No change proceeds without a reviewed plan.
2. **Policy compliance checks.** Automated checks verify the proposed change does not: introduce direct block-to-block connections (D-003), weaken environment isolation boundaries, remove mandatory resource tagging, or modify audit log infrastructure without boundary-class governance. Compliance failure blocks the pipeline.
3. **Cost impact assessment.** The estimated cost delta of the proposed change is surfaced before apply. Changes exceeding a declared cost impact threshold require explicit acknowledgment before proceeding.
4. **Development validation.** The change is applied to the development environment and validated before the production pipeline is unblocked.

A change passing all four stages may proceed to production. A change failing at any stage is stopped, logged, and requires a corrected proposal — not a bypass.

### Change Governance Tiers

| Tier | Examples | Governance |
|---|---|---|
| Routine | Scaling, configuration tuning, dependency updates | Automated tests pass → applied; owner not notified unless requested |
| Significant | New block provisioned, storage capacity change, pipeline modification | Automated tests + human review before production apply; owner notified |
| Boundary-class | Bridge modification, environment isolation change, audit log infrastructure change, secrets infrastructure change | Automated tests + human review + explicit owner confirmation via Block 9 before apply |

Boundary-class changes route through Block 9 (Action Layer) confirmation gate. Timeout means no application.

### Change Failure Model

- Failed changes are rolled back automatically where rollback is possible.
- Partial applies — where some resources changed and others did not — are detected and treated as failures requiring remediation, not accepted as partial success.
- Failed production changes are an immediate Block 25 observability event and owner notification.
- The failed state is fully logged: what was attempted, what succeeded, what failed, what was rolled back.
- No subsequent change to the same infrastructure may be applied until the failure is resolved and the current state is confirmed.

### Sandbox Provisioning via Pipeline

- Sandbox IaC templates are part of Block 27's IaC definitions and are managed through the normal pipeline.
- Block 21 cannot create or modify templates. Template promotion requires human review.
- The template catalogue is versioned. Block 21 references a specific template version, not a floating latest.
- Programmatic provisioning requests are validated against the template catalogue at the bridge before reaching the experimental environment.
- A structural cap on concurrent sandbox instances is declared in IaC. Provisioning requests exceeding the cap are queued up to a declared queue depth, then rejected and logged.

### Pipeline Self-Governance

The IaC pipeline (Block 28) runs on infrastructure Block 27 provisions. Modifications to Block 28 infrastructure are significant-tier changes. The pipeline cannot modify its own underlying infrastructure through an automated run. Changes to the pipeline definition travel through the pipeline; changes to the pipeline's infrastructure travel through a separate human-initiated process.

### Technology Selection

Technology choices for infrastructure are made after requirements are understood, proposed through the D-010 protocol, and recorded in DECISIONS.md before implementation begins. No technology choice is locked speculatively. Choices may be revisited when requirements change; reversals are recorded as superseding decisions. The Evolution Engine (Block 21) may surface infrastructure optimisations over time; these travel through the same pipeline and selection process as human-proposed changes.

---

## Interface Specification

### Events Emitted by Block 27

All events are emitted to Block 13 (Central Orchestrator) via the event bus for routing to Block 25 (Observability) and, where relevant, to Block 20 (Cost / Rate Management).

| Event | Description |
|---|---|
| `infrastructure.change.applied` | Change completed successfully. Includes plan summary and cost delta. |
| `infrastructure.change.failed` | Change failed. Includes failure detail and rollback status. |
| `infrastructure.change.rolled_back` | Rollback completed or failed following a change failure. |
| `infrastructure.change.boundary_class.pending` | Boundary-class change awaiting owner confirmation via Block 9. |
| `sandbox.provisioned` | Experimental sandbox spun up. Includes template version, parameters used, instance identifier. |
| `sandbox.torn_down` | Sandbox terminated. Includes reason (expiry, completion, failure) and resource consumption summary. |
| `sandbox.teardown_failed` | Automated teardown did not complete within the declared window. Escalation required. |
| `bridge.event.rejected` | Provisioning request or result crossing the bridge was rejected. Includes rejection reason. |
| `cost.threshold.approached` | Resource consumption approaching a declared cap. Includes current level and cap value. |
| `secrets.rotation.failed` | Credential rotation did not complete. Includes affected credential category, never credential value. |

No event emitted by Block 27 contains raw credential values under any circumstance.

### Events Consumed by Block 27

Block 27 subscribes to the following event types via Block 13:

| Event | Source | Purpose |
|---|---|---|
| `sandbox.provision.requested` | Block 21 via Block 13 | Trigger experimental environment sandbox provisioning from template catalogue |
| `sandbox.teardown.requested` | Block 21 via Block 13 | Trigger teardown of a named sandbox instance before duration expiry |
| `infrastructure.change.confirmation.received` | Block 9 via Block 13 | Owner has confirmed a boundary-class change; proceed with application |
| `infrastructure.change.confirmation.rejected` | Block 9 via Block 13 | Owner has rejected a boundary-class change or timeout has elapsed; do not apply |

Block 27 has no direct block-to-block connections. All event flows route through Block 13 (D-003).

### Cross-Environment Bridge Interface

The bridge is provisioned by Block 27 as independent infrastructure. It is not part of production or experimental environments.

**Production → Experimental (inbound to experimental):**
- Provisioning commands: sandbox provision requests, teardown requests
- Fitness signal delivery: data from Block 18 (Feedback) and Block 20 (Cost) forwarded to Block 21

**Experimental → Production (outbound from experimental):**
- Variant results: performance data, evaluation outcomes
- Data feeding Block 18 and Block 20 for fitness assessment

All bridge traffic is logged. The bridge enforces schema compliance on all payloads in both directions. Alignment enforcement on bridge-crossing events is a Block 22 (Alignment Layer) responsibility — the Architect has been notified of this interface requirement.

---

## Constraints Inherited from DECISIONS.md

| Decision | Constraint on Block 27 |
|---|---|
| D-002 | No technology choices at specification stage. Infrastructure requirements describe what must be done and what constraints must be satisfied. Technology decisions follow when requirements are understood and are recorded before implementation. |
| D-003 | No direct block-to-block communication. All inter-block communication routes through Block 13 via events. Block 27's programmatic provisioning surface is accessible only via the event bus. |
| D-004 | The alignment constitution cannot be modified by Block 27 or by any mechanism Block 27 provisions. The Evolution Engine may optimise infrastructure means but cannot modify alignment ends. |
| D-005 | CI/CD and IaC pipelines that interact with the Evolution Engine may not enable deprecation or rollback of personality parameters (Block 1) without explicit owner confirmation. |
| D-006 | Destructive or irreversible infrastructure actions — deprovisioning production resources, modifying audit log infrastructure, weakening environment boundaries — route through Block 9 confirmation gate. Timeout means no action. |
| D-008 | No implementation begins without a corresponding decision record in DECISIONS.md. Infrastructure technology choices are made and recorded before any build begins. |
| D-017 | Block 13 (Central Orchestrator) and Block 16 (Storage) are the first things built. Block 27 must be able to provision the infrastructure for these two blocks before any other block infrastructure is provisioned. |
| D-018 | Infrastructure supports stateless agent execution. All state lives in a central store outside the agent. Block 27 provisions the storage infrastructure that makes this possible. |
| D-022 | The experimental zone runs in entirely separate infrastructure from production. Separate network, separate accounts or projects, no shared resources. Policy-only isolation is explicitly ruled out. |
| D-023 | The Central Orchestrator runs as a single instance with no redundancy in v1. Block 27 does not provision orchestrator redundancy. Simplicity and debuggability outweigh availability for a single-owner system at this stage. |
| D-024 | Cross-environment communication is governed by the controlled event bridge. Production and experimental share no storage or compute. The bridge is the only connection and is fully logged. |
| D-025 | All subscriber blocks must be idempotent — receiving the same event twice must produce the same result as receiving it once. Block 27's event consumers are designed to this constraint. |

---

## Open Items

### Cross-Block Interface: Block 27 / Block 16 — Audit Log Immutability Model

**Status:** Pending Knowledge Agent activation.

Block 27 commits to provisioning storage infrastructure capable of enforcing write-once immutability for the audit log. The specific immutability model — whether enforced at the storage layer, the access control layer, or both — is a Block 16 design decision. Block 27 will implement it at the infrastructure layer once Block 16 specifies it. This interface must be resolved before audit log infrastructure is provisioned.

### Cross-Block Interface: Block 27 / Block 23 — Secrets Management Policy

**Status:** Pending Access and Security Agent activation.

Block 23 (Access and Security Agent) owns secrets management policy. Block 27 provisions the infrastructure that policy runs on. When the Access and Security Agent is activated, the secrets infrastructure requirements — rotation cadence, credential lifetime limits per category, access scoping — will need cross-block alignment on this interface.

### Technology Choices

**Status:** Deferred per D-002.

No technology choices have been made for Block 27 infrastructure. Choices will be proposed through the D-010 protocol when requirements are sufficiently understood, and recorded in DECISIONS.md before implementation begins.

---

*Block 27 — Infrastructure / IaC Requirements Artefact*
*Produced by the Infrastructure Agent, May 2026*
