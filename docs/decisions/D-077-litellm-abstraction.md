---
id: D-077
title: Block 8 calls LLMs via LiteLLM; default provider Anthropic; no provider hardcoded
status: Accepted
date: 2026-05-01
blocks: Block 8 (Query/RAG), Block 21 (Evolution Engine), Block 27 (Infrastructure/IaC)
agents: Intelligence Agent, Systems Agent (Block 21)
---

## Context
Block 8 must call an LLM. The Evolution Engine will want to test different
models as a fitness variable. Hardcoding a provider makes each model
experiment a code change rather than a configuration change.

## Options Considered
A. LiteLLM abstraction layer (chosen) — provider is configuration; Evolution
   Engine experiments require no code changes.
B. Direct Anthropic SDK — hardcodes provider; model experiments require code
   changes; violates D-002 intent.
C. Direct OpenAI SDK — same problems as B.

## Decision
Block 8 calls LLMs via LiteLLM as an abstraction layer. No provider is
hardcoded. The default provider at v0.1 is Anthropic (Claude). Provider and
model are configuration values, not code changes.

## Rationale
Provider abstraction costs almost nothing at this stage. The Evolution Engine
will want to test different models as a fitness variable — with LiteLLM, that
is a configuration change. Consistent with D-002's intent to avoid lock-in.
LiteLLM supports Anthropic, OpenAI, and most other providers.

## Consequences
Rules out hardcoding any specific LLM provider or SDK in Block 8. Rules out
direct Anthropic or OpenAI SDK calls in Block 8 application code. Rules out
any LLM call that cannot be redirected by configuration change alone.

## Related Decisions
D-002 (no technology lock-in), D-096 (LiteLLM also used for embeddings).
