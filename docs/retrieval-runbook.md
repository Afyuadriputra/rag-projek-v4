# Retrieval Runbook

## Primary SLOs
- p95 response time for chat endpoints.
- grounded-answer rate for structured transcript/schedule queries.
- fallback/error rates from `RagRequestMetric`.

## Incident Signals
- `validation=failed_fallback` spike.
- `validation=no_grounding_evidence` unusual spike.
- p95 latency regression above agreed threshold.
- 5xx increase on RAG endpoints.

## Immediate Mitigations
1. Turn off modular path flags if recent rollout causes instability.
2. Reduce heavy retrieval options (hybrid/rerank/query-rewrite) via env.
3. Force strict transcript mode for critical periods.

## Rollback Controls
- `RAG_REFACTOR_CHAT_SERVICE_ENABLED=0`
- `RAG_REFACTOR_STRUCTURED_PIPELINE_ENABLED=0`
- `RAG_SEMANTIC_OPTIMIZED_RETRIEVAL_ENABLED=0`
- Keep legacy path serving all traffic.

## Rollback Procedure (Feature Flag)
1. Disable target flag on staging first, then production.
2. Reload app workers.
3. Verify smoke query:
   - transcript recap query
   - schedule query
   - semantic policy query
4. Check metric recovery:
   - `validation=no_grounding_evidence`
   - `fallback_used`
   - `status_code>=500`
5. Keep rollback state until p95/error normal at least 30 minutes.

## Diagnostics Checklist
1. Check route distribution (`intent_route`).
2. Check docs retrieval counts and top score.
3. Inspect answer validation statuses.
4. Verify OpenRouter model fallback behavior.
5. Verify vector store connectivity and user filtering.

## Canary Commands
- Canary report (clean window):
  - `./venv/Scripts/python.exe manage.py rag_canary_report --minutes 30`
- Canary report by stage/prefix:
  - `./venv/Scripts/python.exe manage.py rag_canary_report --minutes 30 --request-prefix canary-10-`
  - `./venv/Scripts/python.exe manage.py rag_canary_report --minutes 30 --request-prefix canary-50-`
  - `./venv/Scripts/python.exe manage.py rag_canary_report --minutes 30 --request-prefix canary-100-`
- Semantic ON vs OFF benchmark + threshold gate:
  - `./venv/Scripts/python.exe manage.py rag_semantic_benchmark --user-id <id> --iterations 3 --warmup-runs 1`

## Staged Rollout (10% -> 50% -> 100%)
1. Set flags (staging/internal first):
   - `RAG_REFACTOR_CHAT_SERVICE_ENABLED=1`
   - `RAG_REFACTOR_STRUCTURED_PIPELINE_ENABLED=1`
   - `RAG_SEMANTIC_OPTIMIZED_RETRIEVAL_ENABLED=1`
   - `RAG_SEMANTIC_OPTIMIZED_TRAFFIC_PCT=<10|50|100>`
2. Run canary traffic for the stage.
3. Evaluate clean report window (`--request-prefix`) for 2-3 consecutive runs.
4. Promote to next stage only if all gates pass.

Gate criteria:
- p95 total/retrieval within `docs/retrieval-performance-budget.md`.
- fallback/error stable (no spike).
- validation quality stable (`no_grounding_evidence` and `failed_fallback` not anomalous).

## Environment Injection Note (Local)
When running `./venv/Scripts/python.exe` from bash, inline prefix env style can be ignored by Windows Python process.

Recommended local options:
1. Set env inside Python process before calling `ask_bot` (via `manage.py shell`), or
2. Run from PowerShell/CMD with native env syntax.

Example (`manage.py shell`):
- set `os.environ[...]` first, then call `ask_bot(...)` for canary requests with stable request_id prefix.

## Final Cleanup Gate
Do legacy minimization only after 100% stage is stable:
- `main_legacy.py` reduced to adapter-minimum.
- prune non-used compatibility aliases in `main.py` and `structured_analytics.py`.
- rerun full retrieval sign-off suite and keep results as release evidence.

## Current Release Decision (2026-02-22)
- Keep:
  - `RAG_REFACTOR_CHAT_SERVICE_ENABLED=1`
  - `RAG_REFACTOR_STRUCTURED_PIPELINE_ENABLED=1`
- Hold:
  - `RAG_SEMANTIC_OPTIMIZED_RETRIEVAL_ENABLED=0`
- Reason:
  - functional and regression suites are stable, but real canary p95 for semantic optimized path is not yet consistently within budget.
  - semantic optimized rollout is postponed to a dedicated performance-tuning sprint.
