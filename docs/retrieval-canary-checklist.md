# Retrieval Canary Checklist

## 1) Setup Flags (staging/canary)
- `RAG_REFACTOR_CHAT_SERVICE_ENABLED=1`
- `RAG_REFACTOR_STRUCTURED_PIPELINE_ENABLED=1`
- `RAG_GROUNDING_POLICY_V2_ENABLED=1`
- `RAG_METRIC_ENRICHMENT_ENABLED=1`
- `RAG_SEMANTIC_OPTIMIZED_RETRIEVAL_ENABLED=0`

## 2) Run Smoke Queries
- `coba rekap hasil studi saya`
- `rekap matakuliah saya yang tidak lulus`
- `bagaimana progres hasil studi saya?`
- `berapa nilai saya?` (expected: abstain jika evidence kosong)
- `apa syarat lulus skripsi?`

## 3) Generate Canary Metrics
```bash
./venv/Scripts/python.exe manage.py rag_canary_report --minutes 60 --limit 5000 --top-slow 10
```

### 3b) Compare Semantic Optimized ON vs OFF
```bash
./venv/Scripts/python.exe manage.py rag_semantic_benchmark --user-id 1 --iterations 3 \
  --query "apa syarat lulus skripsi?" \
  --query "apa itu sks?" \
  --query "jelaskan aturan cuti kuliah"
```

### 3c) Enforce Threshold Gate (CI-friendly)
```bash
./venv/Scripts/python.exe manage.py rag_semantic_benchmark --user-id 1 --iterations 3 \
  --max-on-p95-total-ms 2500 \
  --max-on-p95-retrieval-ms 1800 \
  --max-on-p95-llm-ms 2000 \
  --max-on-error-rate-pct 2.0
```
Jika threshold terlewati, command exit non-zero (fail gate). Untuk mode observasi tanpa fail gunakan `--soft`.

## 4) Go/No-Go Threshold
- Error rate (5xx) <= 2%
- Fallback rate stabil (tidak spike > 2x baseline)
- p95 total latency:
  - structured transcript <= 2000ms
  - structured schedule <= 1600ms
  - semantic policy <= 2500ms

## 5) Rollout Steps
1. Internal canary only
2. 10% traffic
3. 50% traffic
4. 100% traffic

Di setiap step: ulangi metrics report + smoke queries.

## 6) Rollback
Jika threshold gagal:
- set `RAG_REFACTOR_CHAT_SERVICE_ENABLED=0`
- set `RAG_REFACTOR_STRUCTURED_PIPELINE_ENABLED=0`
- redeploy config only

## 7) Post-rollout Validation
- Pastikan `validation=no_grounding_evidence` muncul untuk personal query tanpa evidence.
- Pastikan query KHS faktual tetap grounded (tidak ada halusinasi tabel/nilai).
