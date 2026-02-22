# Retrieval Alias Usage Map

Generated: 2026-02-22T18:06:17+07:00

## main.py aliases
- ask_bot: 15 hit(s)
- _ask_bot_legacy: 10 hit(s)
- _has_user_documents: 30 hit(s)
- _resolve_user_doc_mentions: 8 hit(s)
- _extract_doc_mentions: 0 hit(s)
- _normalize_doc_key: 0 hit(s)
- _build_chroma_filter: 4 hit(s)
- AcademicDocument: 4 hit(s)
- build_llm: 24 hit(s)
- get_backup_models: 20 hit(s)
- get_runtime_openrouter_config: 54 hit(s)
- invoke_text: 2 hit(s)
- create_stuff_documents_chain: 46 hit(s)
- get_vectorstore: 26 hit(s)
- retrieve_dense: 36 hit(s)
- retrieve_sparse_bm25: 2 hit(s)
- fuse_rrf: 2 hit(s)
- rerank_documents: 2 hit(s)
- run_structured_analytics: 10 hit(s)
- polish_structured_answer: 4 hit(s)
- infer_doc_type: 2 hit(s)
- _dedup_docs: 2 hit(s)
- _has_citation: 4 hit(s)
- _rewrite_queries: 2 hit(s)
- _classify_transcript_answer_mode: 0 hit(s)

## structured_analytics.py aliases
- run_structured_analytics: 5 hit(s)
- polish_structured_answer: 2 hit(s)
- get_vectorstore: 18 hit(s)
- _invoke_polisher_llm: 4 hit(s)

## Decision
- No alias pruned in this pass. All compatibility aliases still have active test/consumer references in-repo.
- Safe pruning requires consumer migration first, then rerun full sign-off.
