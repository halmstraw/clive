"""Event type constants — Block 13 taxonomy.

All event types used in CLIVE. Grouped by class as defined in
the Block 13 requirements artefact.
"""

# Class 1 — Interaction
QUERY_RECEIVED = "query.received"
QUERY_RESPONSE = "query.response"
APPROVAL_GRANTED = "approval.granted"
APPROVAL_REJECTED = "approval.rejected"
APPROVAL_TIMEOUT = "approval.timeout"
FEEDBACK_EXPLICIT = "feedback.explicit"
FEEDBACK_IMPLICIT = "feedback.implicit"
ACTION_REQUESTED_UNAVAILABLE = "action.requested_unavailable"

# Class 2 — Knowledge
INGESTION_TRIGGERED = "ingestion.triggered"
INGESTION_COMPLETED = "ingestion.completed"
PROCESSING_COMPLETED = "processing.completed"
RETRIEVAL_REQUESTED = "retrieval.requested"
RETRIEVAL_COMPLETED = "retrieval.completed"

# Ingestion pipeline — Block 14 / Block 15 (D-099, D-101)
INGEST_RECEIVED = "ingest.received"
INGEST_PROCESSED = "ingest.processed"
INGEST_REJECTED = "ingest.rejected"

# Class 3 — Action
ACTION_PROPOSED = "action.proposed"
ACTION_DISPATCHED = "action.dispatched"
ACTION_COMPLETED = "action.completed"
ACTION_FAILED = "action.failed"
ACTION_CANCELLED = "action.cancelled"

# Block 9 — Action Layer (v0.3, D-006, D-105)
# Full lifecycle: pending → confirmation_requested → owner_response → confirmed | rejected
ACTION_PENDING = "action.pending"                           # Block 23 → Block 9
ACTION_CONFIRMATION_REQUESTED = "action.confirmation_requested"  # Block 9 → Block 23
ACTION_OWNER_RESPONSE = "action.owner_response"             # Block 23 → Block 9
ACTION_CONFIRMED = "action.confirmed"                       # Block 9 → deletion handler
ACTION_REJECTED = "action.rejected"                         # Block 9 → Block 23

# T8 — Deletion pipeline (v0.3)
DELETION_COMPLETE = "deletion.complete"                     # processing → Block 23
DELETION_NOT_FOUND = "deletion.not_found"                   # processing → Block 23

# Class 4 — Worker
WORKER_SPAWNED = "worker.spawned"
WORKER_HEARTBEAT = "worker.heartbeat"
WORKER_COMPLETED = "worker.completed"
WORKER_FAILED = "worker.failed"
WORKER_RETIRED = "worker.retired"
WORKER_HEARTBEAT_MISSED = "worker.heartbeat.missed"

# Class 5 — Evolution
VARIANT_CREATED = "variant.created"
VARIANT_EVALUATED = "variant.evaluated"
VARIANT_PROMOTED = "variant.promoted"
VARIANT_RETIRED = "variant.retired"
EVOLUTION_BOUNDARY_BREACH = "evolution.boundary.breach"

# Class 6 — System
COST_THRESHOLD_APPROACHED = "cost.threshold.approached"
COST_THRESHOLD_EXCEEDED = "cost.threshold.exceeded"
SYSTEM_HEALTH_DEGRADED = "system.health.degraded"
SYSTEM_OVERRIDE_ISSUED = "system.override.issued"
SYSTEM_OVERRIDE_ACTIVE = "system.override.active"
CONFIG_CHANGED = "config.changed"
SECURITY_ANOMALY_DETECTED = "security.anomaly.detected"

# Orchestrator-emitted
ALIGNMENT_REJECTED = "alignment.rejected"
DELIVERY_FAILED = "delivery.failed"
ALERT_TRIGGERED = "alert.triggered"
