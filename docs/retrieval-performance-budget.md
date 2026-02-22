# Retrieval Performance Budget

## Priority
Primary KPI: **chat p95 latency** while preserving grounded accuracy.

## Budget Targets (initial)
- transcript structured queries: p95 <= 2.0s
- schedule structured queries: p95 <= 1.6s
- semantic policy queries: p95 <= 2.5s
- fallback/error rate: < 2%

## Budget Components
- retrieval stage: <= 35%
- rerank stage: <= 20%
- llm stage: <= 45%

## Optimization Rules
- Enable rerank only for doc-targeted semantic routes.
- Use hybrid retrieval only when dense-only confidence is low.
- Keep strict no-grounding abstain for personal doc queries without evidence.
- Reuse cached settings and user doc checks to reduce overhead.

## Measurement
Use `RagRequestMetric` fields:
- `retrieval_ms`, `rerank_ms`, `llm_time_ms`
- `mode`, `status_code`, `fallback_used`

Track p50/p95 per route and per pipeline weekly.

## CI Gate (Semantic ON vs OFF)
Command:
- `./venv/Scripts/python.exe manage.py rag_semantic_benchmark --user-id <id> --iterations 3 --query "apa itu sks?"`

Default thresholds:
- `max_on_p95_total_ms=2500`
- `max_on_p95_retrieval_ms=1800`
- `max_on_p95_llm_ms=2000`
- `max_on_error_rate_pct=2.0`
- `max_delta_p95_total_ms=800`
- `max_delta_p95_retrieval_ms=600`
- `max_delta_p95_llm_ms=800`

Behavior:
- Command returns non-zero (`CommandError`) when gate fails.
- Use `--soft` only for exploratory profiling, not CI.
