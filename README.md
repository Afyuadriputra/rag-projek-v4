
# Academic RAG Project

## Ingestion Pipeline (Current)
`core/ai_engine/ingest.py` sekarang berperan sebagai **facade kompatibilitas**.  
Logic berat ingestion dipindahkan ke `core/ai_engine/ingest_pipeline/*`.

Alur utama:
1. `process_document(doc_instance)` dipanggil dari facade `core.ai_engine.ingest`.
2. Facade membangun `PipelineOps` lalu mendelegasikan ke `core/ai_engine/ingest_pipeline/orchestrator.py`.
3. Orchestrator menjalankan tahapan:
   - `extract`: ekstraksi PDF/CSV/XLSX/TXT.
   - `parse`: parser transcript/schedule (deterministic + LLM fallback).
   - `chunk`: pembentukan chunk + metadata.
   - `write`: tulis ke vector store.
4. Setiap dokumen sekarang memiliki log timing:
   - `INGEST_TIMING source=... extract_ms=... parse_ms=... chunk_ms=... write_ms=... total_ms=...`

## Patch-Path Compatibility (Dijaga)
Walaupun dipecah modular, patch path lama pada `core.ai_engine.ingest.*` tetap dipertahankan untuk test lama dan shim kompatibilitas.

Contoh symbol yang sengaja tetap tersedia:
- `process_document`
- `_norm`
- `_normalize_time_range`
- `_extract_pdf_tables`
- `_extract_pdf_page_raw_payload`
- `UniversalTranscriptParser`
- `UniversalScheduleParser`

Artinya test dengan pola `patch("core.ai_engine.ingest.<symbol>")` tetap valid.
