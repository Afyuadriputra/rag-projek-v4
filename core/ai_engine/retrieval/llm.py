import os
from typing import Dict, Any
from django.db import OperationalError, ProgrammingError

from langchain_openai import ChatOpenAI

DEFAULT_MODEL = "google/gemini-2.5-flash-lite"
DEFAULT_BACKUP_MODELS = [
    "openai/gpt-5-nano",
    "minimax/minimax-m2.5",
    "nvidia/nemotron-3-nano-30b-a3b:free",
    "arcee-ai/trinity-large-preview:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    
]


def _parse_models(raw: str | None) -> list[str]:
    text = (raw or "").replace("\r", "\n")
    text = text.replace(",", "\n")
    items = [x.strip() for x in text.split("\n")]
    return [x for x in items if x]


def get_runtime_openrouter_config() -> Dict[str, Any]:
    env_backups = _parse_models(os.environ.get("OPENROUTER_BACKUP_MODELS", ""))
    if not env_backups:
        env_backups = list(DEFAULT_BACKUP_MODELS)

    cfg: Dict[str, Any] = {
        "api_key": os.environ.get("OPENROUTER_API_KEY", "").strip(),
        "model": os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL,
        "backup_models": env_backups,
        "timeout": int(os.environ.get("OPENROUTER_TIMEOUT", "45")),
        "max_retries": int(os.environ.get("OPENROUTER_MAX_RETRIES", "1")),
        "temperature": float(os.environ.get("OPENROUTER_TEMPERATURE", "0.2")),
    }

    try:
        from core.models import LLMConfiguration
        db_cfg = (
            LLMConfiguration.objects.filter(is_active=True)
            .order_by("-updated_at", "-id")
            .first()
        ) or LLMConfiguration.objects.order_by("-updated_at", "-id").first()
        if db_cfg:
            if (db_cfg.openrouter_api_key or "").strip():
                cfg["api_key"] = db_cfg.openrouter_api_key.strip()
            if (db_cfg.openrouter_model or "").strip():
                cfg["model"] = db_cfg.openrouter_model.strip()
            db_backups = _parse_models(getattr(db_cfg, "openrouter_backup_models", ""))
            if db_backups:
                cfg["backup_models"] = db_backups
            cfg["timeout"] = int(db_cfg.openrouter_timeout)
            cfg["max_retries"] = int(db_cfg.openrouter_max_retries)
            cfg["temperature"] = float(db_cfg.openrouter_temperature)
    except (OperationalError, ProgrammingError):
        # DB belum siap (misal saat migrate) -> fallback env.
        pass
    except Exception:
        pass

    return cfg


def get_backup_models(primary_model: str, configured_backup_models: list[str] | None = None) -> list[str]:
    models = [primary_model] + (configured_backup_models or list(DEFAULT_BACKUP_MODELS))
    out: list[str] = []
    for m in models:
        name = (m or "").strip()
        if not name or name in out:
            continue
        out.append(name)
    return out


def build_llm(model_name: str, cfg: Dict[str, Any]) -> ChatOpenAI:
    return ChatOpenAI(
        openai_api_key=cfg.get("api_key"),
        openai_api_base="https://openrouter.ai/api/v1",
        model_name=model_name,
        temperature=float(cfg.get("temperature", 0.2)),
        request_timeout=int(cfg.get("timeout", 45)),
        max_retries=int(cfg.get("max_retries", 1)),
        default_headers={
            "HTTP-Referer": "http://localhost:8000",
            "X-Title": "AcademicChatbot",
        },
    )


def invoke_text(llm: ChatOpenAI, prompt: str) -> str:
    out = llm.invoke(prompt)
    if hasattr(out, "content"):
        return out.content or ""
    return str(out)


def llm_fallback_message(last_error: str) -> Dict[str, Any]:
    return {"answer": f"Maaf, semua server AI sedang sibuk. (Error: {last_error})", "sources": []}
