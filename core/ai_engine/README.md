# AI Engine Documentation (End-to-End)

Dokumen ini menjelaskan alur end-to-end `core/ai_engine` dari upload dokumen sampai jawaban chatbot, termasuk routing RAG, observability, dan mode operasional production saat ini.

## 1. Scope dan Tujuan

`core/ai_engine` adalah mesin utama untuk:
- ingest dokumen akademik user ke vector store (Chroma),
- retrieval konteks berdasarkan pertanyaan,
- generate jawaban dengan LLM (OpenRouter),
- menjaga jawaban tetap grounded ke dokumen user,
- mengirim metrik runtime ke `RagRequestMetric`.

Stack utama:
- Django monolith,
- Chroma (`collection_name=academic_rag`),
- Embedding HuggingFace (`intfloat/multilingual-e5-large` default),
- LLM OpenRouter.

## 2. Struktur Folder AI Engine

- `core/ai_engine/config.py`: inisialisasi embedding + vector store Chroma.
- `core/ai_engine/ingest.py`: facade ingest kompatibel lama (delegasi ke pipeline baru).
- `core/ai_engine/ingest_pipeline/*`: pipeline ingest modular (extract/parse/chunk/write).
- `core/ai_engine/retrieval/main.py`: facade publik `ask_bot(...)`.
- `core/ai_engine/retrieval/main_legacy.py`: legacy core untuk fallback kompatibilitas.
- `core/ai_engine/retrieval/application/*`: orchestrator modular (guard, mention, route, structured, semantic).
- `core/ai_engine/retrieval/pipelines/structured/*`: analytics terstruktur (KHS/jadwal).
- `core/ai_engine/retrieval/pipelines/semantic/*`: retrieval + answer semantic.
- `core/ai_engine/retrieval/infrastructure/*`: adapter LLM, metric, vector repo.
- `core/ai_engine/retrieval/domain/*`: model/policy grounding.
- `core/ai_engine/retrieval/config/settings.py`: single source of truth flag retrieval.

## 3. End-to-End Flow

### 3.1 Flow Upload dan Ingest Dokumen

Flow request:
1. API menerima file (`core/views.py:606` jalur chat/planner; upload via service layer).
2. Service membuat `AcademicDocument` lalu memanggil `process_document(doc)` (`core/service.py:57-93`).
3. `core/ai_engine/ingest.py:323` meneruskan ke `ingest_pipeline.orchestrator.process_document(...)`.
4. Orchestrator melakukan:
- ekstraksi konten file (PDF/Excel/CSV/TXT),
- parser chain schedule/transcript (rule + optional LLM parser),
- normalisasi row canonical,
- chunking text + row chunks,
- build metadata chunk (user_id, doc_id, doc_type, semester, dst),
- write ke Chroma.
5. Jika sukses, `AcademicDocument.is_embedded=True`.

File kunci:
- `core/ai_engine/ingest_pipeline/orchestrator.py:38`
- `core/ai_engine/ingest.py:323`
- `core/ai_engine/config.py:106`

### 3.2 Flow Chat/RAG

Flow request:
1. Frontend memanggil `/api/chat/` (`core/views.py:606`).
2. `service.chat_and_save(...)` memanggil `core.ai_engine.retrieval.main.ask_bot(...)` (`core/service.py:47-55`).
3. `main.ask_bot(...)` memilih jalur modular atau legacy via flag (`core/ai_engine/retrieval/main.py:90-97`).
4. Jalur modular (`application/chat_service.py`) menjalankan urutan:
- safety guard,
- doc mention resolution (`@file`),
- intent routing,
- structured pipeline bila relevan,
- semantic pipeline bila structured tidak dipakai.
5. Response dinormalisasi ke kontrak frontend:
- `answer`, `sources`, `meta`.

File kunci:
- `core/ai_engine/retrieval/main.py:90`
- `core/ai_engine/retrieval/application/chat_service.py:164`

## 4. Routing Jalur Jawaban

## 4.1 Guard Layer

Modul guard (`application/guards_service.py`) menangani query terlarang/out-of-domain.
Jika query ditolak, sistem return cepat tanpa retrieval berat.

## 4.2 Mention Resolution

Modul mention (`application/mention_service.py`) memproses `@nama_file`, resolve ke `doc_id`, serta status:
- `resolved_doc_ids`,
- `unresolved_mentions`,
- `ambiguous_mentions`.

## 4.3 Structured Pipeline (Transcript/Schedule)

Structured aktif saat route `analytical_tabular` + user punya dokumen.
Alur:
- fetch -> normalize -> filter -> render -> polish.

Modul:
- `core/ai_engine/retrieval/pipelines/structured/fetch.py`
- `core/ai_engine/retrieval/pipelines/structured/normalize.py`
- `core/ai_engine/retrieval/pipelines/structured/filter.py`
- `core/ai_engine/retrieval/pipelines/structured/render.py`
- `core/ai_engine/retrieval/pipelines/structured/polish.py`
- orchestrator: `core/ai_engine/retrieval/pipelines/structured/run.py`

Aturan penting transcript:
- strict transcript mode dapat mengembalikan deterministic/no-fallback (`validation=strict_no_fallback`).

## 4.4 Semantic Pipeline

Jika tidak masuk structured, sistem masuk semantic path:
1. retrieval docs (dense / hybrid / rerank sesuai route),
2. no-grounding policy check,
3. LLM answer generation,
4. citation enrichment + unresolved mention note,
5. metric emit.

Modul:
- `core/ai_engine/retrieval/pipelines/semantic/run.py`
- `core/ai_engine/retrieval/pipelines/semantic/retrieve.py`
- `core/ai_engine/retrieval/pipelines/semantic/rerank.py`
- `core/ai_engine/retrieval/pipelines/semantic/answer.py`

Executor semantic service:
- `core/ai_engine/retrieval/application/semantic_service.py:29`

## 5. Kapan LLM Menjawab?

Ya, LLM kamu dipakai aktif di jalur retrieval:
- semantic answer: `invoke_with_model_fallback(...)` di `infrastructure/llm_client.py:39`.
- structured polish: dipakai untuk polishing jawaban structured (kecuali strict mode skip).

Sumber konfigurasi LLM:
- prioritas DB `LLMConfiguration` aktif,
- fallback ke env (`OPENROUTER_*`).

File:
- `core/ai_engine/retrieval/llm.py:25`
- `core/ai_engine/retrieval/infrastructure/llm_client.py:39`

## 6. Kontrak Response (Frontend)

Selalu bentuk:
- `answer: str`
- `sources: list`
- `meta: dict`

Field `meta` yang harus stabil:
- `pipeline`
- `intent_route`
- `validation`
- `answer_mode`

Field enrichment umum:
- `retrieval_docs_count`
- `top_score`
- `structured_returned`
- `stage_timings_ms` (route/structured/retrieval/llm)

## 7. Observability dan Metrics

Metrik request RAG disimpan ke `RagRequestMetric`:
- latensi: `retrieval_ms`, `rerank_ms`, `llm_time_ms`,
- quality flags: `validation`, `answer_mode`,
- routing: `pipeline`, `intent_route`, `mode`,
- reliability: `fallback_used`, `status_code`.

Writer metrik:
- `core/ai_engine/retrieval/infrastructure/metrics.py:8`
- `core/monitoring.py:105`

Command operasional:
- Canary report: `python manage.py rag_canary_report --minutes 30`
- Canary per prefix: `python manage.py rag_canary_report --minutes 30 --request-prefix canary-10-`
- Benchmark ON/OFF semantic: `python manage.py rag_semantic_benchmark --user-id 1 --iterations 3 --warmup-runs 1`

## 8. Feature Flags Retrieval

Sumber setting tunggal:
- `core/ai_engine/retrieval/config/settings.py`

Flag utama:
- `RAG_REFACTOR_CHAT_SERVICE_ENABLED`
- `RAG_REFACTOR_STRUCTURED_PIPELINE_ENABLED`
- `RAG_GROUNDING_POLICY_V2_ENABLED`
- `RAG_METRIC_ENRICHMENT_ENABLED`
- `RAG_SEMANTIC_OPTIMIZED_RETRIEVAL_ENABLED`
- `RAG_SEMANTIC_OPTIMIZED_TRAFFIC_PCT`

## 9. Status Operasional Saat Ini (Recommended)

Untuk stabilitas produksi saat ini:
- `RAG_REFACTOR_CHAT_SERVICE_ENABLED=1`
- `RAG_REFACTOR_STRUCTURED_PIPELINE_ENABLED=1`
- `RAG_SEMANTIC_OPTIMIZED_RETRIEVAL_ENABLED=0`

Alasan:
- fungsional suite retrieval sudah hijau,
- semantic optimized masih ditunda sampai sprint tuning p95 khusus.

## 10. Troubleshooting Cepat

### 10.1 Jawaban tidak grounded ke dokumen

Cek:
- user punya `AcademicDocument.is_embedded=True`,
- metadata chunk punya `user_id` benar,
- `validation` di response/meta (`no_grounding_evidence` atau bukan),
- filter mention `@file` resolve/ambiguous.

### 10.2 LLM tidak menjawab

Cek:
- `OPENROUTER_API_KEY` atau `LLMConfiguration` aktif,
- timeout/retry model (`OPENROUTER_TIMEOUT`, `OPENROUTER_MAX_RETRIES`),
- fallback model list (`OPENROUTER_BACKUP_MODELS`).

### 10.3 Latency tinggi

Cek:
- `rag_canary_report` mode/pipeline paling lambat,
- `stage_timings_ms` di meta,
- rerank/hybrid dipakai atau tidak,
- matikan semantic optimized sementara jika canary p95 gagal.

## 11. Checklist Release AI Engine

1. Jalankan sign-off retrieval suite.
2. Simpan baseline hasil test/benchmark.
3. Validasi canary report clean window.
4. Pastikan flag operasional sesuai target rollout.
5. Jika ada regresi p95/error, rollback dengan flag tanpa revert kode.

## 12. File Referensi Utama

- `core/ai_engine/ingest.py`
- `core/ai_engine/ingest_pipeline/orchestrator.py`
- `core/ai_engine/config.py`
- `core/ai_engine/retrieval/main.py`
- `core/ai_engine/retrieval/application/chat_service.py`
- `core/ai_engine/retrieval/application/semantic_service.py`
- `core/ai_engine/retrieval/application/structured_service.py`
- `core/ai_engine/retrieval/infrastructure/llm_client.py`
- `core/ai_engine/retrieval/infrastructure/metrics.py`
- `core/monitoring.py`
- `docs/retrieval-architecture.md`
- `docs/retrieval-runbook.md`
- `docs/retrieval-performance-budget.md`
