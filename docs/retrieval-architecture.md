# Retrieval Architecture (Modular Monolith)

## Goals
- Improve readability and maintainability of retrieval engine.
- Keep backward compatibility for existing `ask_bot` API.
- Enable feature-flagged migration from legacy orchestration.

## Current Transition Design
- Public entrypoint: `core.ai_engine.retrieval.main.ask_bot`
- Facade compatibility: `core.ai_engine.retrieval.main_legacy._ask_bot_legacy`
- Modular entrypoint (flagged): `core.ai_engine.retrieval.application.chat_service.ask_bot`
- Structured pipeline executor: `core.ai_engine.retrieval.pipelines.structured.run`
- Semantic pipeline executor: `core.ai_engine.retrieval.pipelines.semantic.run`

## Layering
- `config/`: settings parser and flags.
- `domain/`: typed models and grounding policies.
- `infrastructure/`: wrappers for vector, llm, metrics.
- `pipelines/`: structured and semantic processing paths.
- `application/`: orchestration and route service.

## Semantic Path (Current)
1. `application.chat_service` resolves guard + mention + route.
2. `application.semantic_service` executes semantic flow.
3. Retrieval stage delegates to `pipelines.semantic.run_retrieval` (dense/hybrid/rerank).
4. Answer stage delegates to `pipelines.semantic.answer` (LLM, citation enrichment, table enrichment).
5. Response always normalized to:
   - `answer`, `sources`, `meta`

## Import Conventions
- For cross-domain dependencies (outside `retrieval` package), use absolute imports from `core.*`.
- Avoid deep relative imports in infrastructure modules (e.g. `...monitoring`) because static analysis can mis-resolve from nested packages.
- Inside the same subpackage, relative imports are allowed for local cohesion.
- `main.py` and `structured_analytics.py` should avoid wildcard re-export (`*`) and keep explicit compatibility exports only.

## Compatibility Contract
- Input/Output of `ask_bot` remains unchanged:
  - `answer`, `sources`, `meta`
- `meta` is enriched with route/pipeline/validation/answer_mode.
- Stable `meta` keys:
  - `pipeline`, `intent_route`, `validation`, `answer_mode`
  - `retrieval_docs_count`, `top_score`, `structured_returned`
  - `stage_timings_ms`

## Compatibility Aliases (Must Keep)
These aliases are intentionally retained in facades because tests and existing consumers patch/import them directly.

`core.ai_engine.retrieval.main`:
- `ask_bot`: public contract entrypoint.
- `_ask_bot_legacy`: compatibility hook used by semantic parity tests.
- `_has_user_documents`: mention/doc existence compatibility hook.
- `_resolve_user_doc_mentions`: mention resolution compatibility hook.
- `_extract_doc_mentions`: imported by mention parser tests.
- `_normalize_doc_key`: imported by mention parser tests.
- `_build_chroma_filter`: imported by retrieval unit tests.
- `AcademicDocument`: patched by mention tests.
- `build_llm`, `get_backup_models`, `get_runtime_openrouter_config`, `invoke_text`: patched by fallback/LLM flow tests.
- `create_stuff_documents_chain`: patched by retrieval flow tests.
- `get_vectorstore`: patched by retrieval/structured flow tests.
- `retrieve_dense`, `retrieve_sparse_bm25`, `fuse_rrf`, `rerank_documents`: patched by hybrid/rerank flow tests.
- `run_structured_analytics`, `polish_structured_answer`: patched by structured flow tests.
- `_classify_transcript_answer_mode`: used by structured orchestration path.

`core.ai_engine.retrieval.structured_analytics`:
- `run_structured_analytics`: public compatibility entrypoint.
- `polish_structured_answer`: public compatibility hook.
- `get_vectorstore`: patched by structured analytics tests.
- `_invoke_polisher_llm`: patched by structured guardrail tests.

Decommission rule:
- Alias can be removed only after strict usage-map check across `core/test` and runtime consumers, followed by full retrieval sign-off suite pass.

## Feature Flags
- `RAG_REFACTOR_CHAT_SERVICE_ENABLED`
- `RAG_REFACTOR_STRUCTURED_PIPELINE_ENABLED`
- `RAG_GROUNDING_POLICY_V2_ENABLED`
- `RAG_METRIC_ENRICHMENT_ENABLED`
- `RAG_SEMANTIC_OPTIMIZED_RETRIEVAL_ENABLED`

## Runtime Settings (Selected)
- `RAG_RETRY_SLEEP_MS`: delay antar percobaan model fallback.
- `RAG_ROUTE_CACHE_TTL_S`: TTL cache resolusi route intent.
- `RAG_MENTION_CACHE_TTL_S`: TTL cache resolusi mention `@file`.
- `RAG_USER_DOCS_CACHE_TTL_S`: TTL cache cek keberadaan dokumen user.
