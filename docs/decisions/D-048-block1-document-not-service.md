---
id: D-048
title: Block 1 is a document stored in Block 16 at runtime; not a runtime service
status: Accepted
date: 2026-05-01
blocks: Block 1 (Personality), Block 8 (Query/RAG), Block 16 (Storage)
agents: Experience Agent (Block 1 content), Intelligence Agent (Block 8),
        Knowledge Agent (Block 16 storage)
---

## Context
D-039 defines personality as a versioned constitutional document loaded from
the central store. D-040 distinguishes build-phase agents from runtime
entities. It needs to be made explicit that Block 1 has no runtime process.

## Options Considered
Options not explicitly recorded in original decision entry.

## Decision
At runtime, Block 1 is a document stored in Block 16, not a service with
its own process. Block 8 retrieves the personality document from Block 16
via the orchestrator-mediated retrieval pattern (D-043). The Knowledge Agent
is responsible for ensuring the personality document is retrievable as a
first-class stored item with version metadata. The Experience Agent (when
activated) owns the content and structure of the personality document, not
its storage or retrieval mechanism.

## Rationale
D-039 defines personality as a versioned constitutional document loaded from
the central store. D-040 distinguishes build-phase agents from runtime
entities. Block 1 has no runtime process — it is the document.

## Consequences
Rules out Block 1 as a runtime service or process. Rules out personality
retrieval bypassing Block 16. Rules out the Knowledge Agent defining
personality content. Rules out the Experience Agent owning personality
storage infrastructure.

## Related Decisions
D-005 (personality survives Reaper), D-039 (personality encoding),
D-040 (build vs runtime), D-054 (personality document structure).
