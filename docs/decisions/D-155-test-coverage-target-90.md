---
id: D-155
title: Test coverage target of 90% for all CLIVE Python services
status: Accepted
date: 2026-05-17
blocks: Block 8, 9, 10, 11, 12, 13, 14, 15, 19, 20, 23, 24, Block 2/3/4/5 (dashboard), Block 28
agents: Architect
---

## Context

SonarCloud reported 58% test coverage across CLIVE Python services. Owner directed
that coverage be raised to 90%+. This decision records the target, approach, and
enforcement mechanism.

## Decision

**Test coverage target: ≥90% statement coverage per service, enforced in CI.**

## Scope

Applies to the five measured services:
- `src/orchestrator/` (Block 13, 9, 10, 19, 20, 22 runtime)
- `src/query/` (Block 8, 11, 12)
- `src/telegram/` (Block 23)
- `src/processing/` (Block 14, 15)
- `src/dashboard/` (Block 2, 3, 4, 5)

## Implementation approach

Unit tests using pytest with `unittest.mock` (AsyncMock/MagicMock) are the primary
mechanism. Tests must not require live DB, network, or external API calls in CI.
All external dependencies are mocked at the service boundary.

CI enforcement: `--cov-fail-under=90` added to each `pytest` invocation in
`.github/workflows/ci.yml`. The build fails if any service drops below 90%.

## Achieved coverage (2026-05-17)

| Service | Coverage |
|---------|----------|
| orchestrator | 90% |
| query | 90% |
| telegram | 92% |
| processing | 91% |
| dashboard | 97% |

## Test files added

**Orchestrator:**
- `test_push.py` — all push routing functions
- `test_health_handlers.py` — all HTTP handler routes
- `test_audit_and_config.py` — audit.write, config_handler functions
- `test_search_and_reminder.py` — search_handler, reminder_handler, dispatch routing
- `test_retrieval_functions.py` — retrieval.py DB-backed functions
- `test_alignment_extended.py` — alignment gate remaining paths
- `test_action_extended.py` — action.py remaining paths
- `test_scheduler_extended.py` — scheduler startup and worker execution
- `test_bus_extended.py` — bus override, queue full, delivery failed
- `test_schema_and_taxonomy.py` — CLIVEEvent schema
- `test_start_health_server.py` — start_health_server function

**Query:**
- `test_handler_extended.py` — _detect_self_knowledge_intent, _detect_spend_cap_intent, _find_tool_in_registry, handle_query action/self-knowledge/idempotency paths
- `test_llm.py` — complete, embed, embed_batch, extract_entities, summarise_turns
- `test_memory_and_registry.py` — memory.py, registry.py, spend.py, db.py
- `test_self_knowledge_query.py` — all self-knowledge intent variants
- `test_context_extended.py` — context.py memory entity paths

**Telegram:**
- `test_session_and_db.py` — SessionManager, db.py, minio_client.py
- `test_bot_intent_detection.py` — detect_search_intent, detect_reminder_intent, command handler basics
- `test_bot_handlers.py` — deliver_* functions, handle_list, handle_status, handle_help, handle_bad
- `test_bot_commands_extended.py` — _emit_action_pending, handle_ingest, handle_document_received, handle_ingest_confirm, handle_delete, handle_tools, deliver_tool_updated/error
- `test_bot_edge_cases.py` — remaining edge cases
- `test_bot_guard_returns.py` — update.message=None guard returns, _send_message, handle_activate
- `test_main_http.py` — main.py HTTP push handler endpoints
- `test_main_startup.py` — main() startup sequence
- `test_auth_extended.py` — auth.py extended paths

**Processing:**
- `test_store.py` — write_chunks function
- `test_pipeline_extended.py` — rejection paths, deletion.py, main.py handlers

**Dashboard:**
- `test_api_and_push.py` — all API and push HTTP endpoints
- `test_auth_extended.py` — auth.py functions, handle_login, handle_logout, main.py handlers

## Related decisions

- D-028 (Block 28, CI/CD) — CI pipeline is the enforcement mechanism
- D-095 — CI integration tests use containerised PostgreSQL
- D-084 — CI secrets stub pattern

## Notes

- `main.py` files for each service (startup loops) are partially excluded from
  the 90% target rationale since they cannot be meaningfully unit-tested without
  spinning up the full service. These are covered where possible via startup mocks.
- The `--cov-fail-under=90` threshold is per-service, not aggregate.
  A service dropping below 90% fails CI even if others are higher.
