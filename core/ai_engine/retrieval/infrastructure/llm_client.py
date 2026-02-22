from __future__ import annotations

import os
import time
from typing import Any, Dict, List

from ..llm import get_runtime_openrouter_config, get_backup_models, build_llm, invoke_text
from ..config.settings import get_retrieval_settings


def _env_int(name: str, default: int) -> int:
    try:
        return int(str((os.environ.get(name, str(default))) or str(default)).strip())
    except Exception:
        return int(default)


def runtime_config() -> Dict[str, Any]:
    return get_runtime_openrouter_config()


def backup_models(model: str, configured: Any) -> List[str]:
    return get_backup_models(model, configured)


def build(model_name: str, cfg: Dict[str, Any]) -> Any:
    return build_llm(model_name, cfg)


def invoke(llm: Any, text: str) -> str:
    return invoke_text(llm, text)


def get_retry_sleep_seconds() -> float:
    settings = get_retrieval_settings()
    return max(float(settings.rag_retry_sleep_ms), 0.0) / 1000.0


def invoke_with_model_fallback(
    *,
    prompt: str,
    cfg: Dict[str, Any] | None = None,
    primary_model: str | None = None,
) -> Dict[str, Any]:
    runtime = dict(cfg or runtime_config())
    settings = get_retrieval_settings()
    if settings.semantic_optimized_retrieval_enabled:
        opt_timeout = max(_env_int("RAG_OPT_LLM_TIMEOUT_S", 12), 1)
        runtime["timeout"] = min(int(runtime.get("timeout", opt_timeout) or opt_timeout), opt_timeout)
        runtime["max_retries"] = min(int(runtime.get("max_retries", 0) or 0), _env_int("RAG_OPT_LLM_MAX_RETRIES", 0))

    selected_model = str(primary_model or runtime.get("model") or "").strip()
    candidates = backup_models(selected_model, runtime.get("backup_models"))
    if settings.semantic_optimized_retrieval_enabled:
        max_models = max(_env_int("RAG_OPT_MAX_MODELS", 1), 1)
        candidates = candidates[:max_models]

    last_error = ""
    for idx, model_name in enumerate(candidates):
        t0 = time.time()
        try:
            llm = build(model_name, runtime)
            output = str(invoke(llm, prompt) or "").strip()
            return {
                "ok": True,
                "text": output,
                "model": model_name,
                "fallback_used": idx > 0,
                "llm_ms": int(max((time.time() - t0) * 1000, 0)),
            }
        except Exception as exc:
            last_error = str(exc)
            if idx < len(candidates) - 1:
                if settings.semantic_optimized_retrieval_enabled:
                    retry_sleep = max(float(_env_int("RAG_OPT_RETRY_SLEEP_MS", 0)), 0.0) / 1000.0
                else:
                    retry_sleep = get_retry_sleep_seconds()
                time.sleep(retry_sleep)
                continue
    return {
        "ok": False,
        "text": "",
        "model": "",
        "fallback_used": len(candidates) > 1,
        "llm_ms": 0,
        "error": last_error,
    }
