import os

from .universal_parsers import UniversalScheduleParserCore, UniversalTranscriptParserCore


class UniversalTranscriptParserFacade(UniversalTranscriptParserCore):
    def __init__(self) -> None:
        from core.ai_engine import ingest as facade

        super().__init__(
            model_name=str(os.environ.get("TRANSCRIPT_LLM_MODEL", "google/gemini-2.5-flash-lite")).strip(),
            timeout=int(os.environ.get("TRANSCRIPT_LLM_TIMEOUT", "45") or 45),
            max_retries=int(os.environ.get("TRANSCRIPT_LLM_MAX_RETRIES", "1") or 1),
            max_pages=int(os.environ.get("TRANSCRIPT_LLM_MAX_PAGES", "12") or 12),
            max_rows=int(os.environ.get("TRANSCRIPT_LLM_MAX_ROWS", "2500") or 2500),
            chat_openai_cls=facade.ChatOpenAI,
            system_message_cls=facade.SystemMessage,
            human_message_cls=facade.HumanMessage,
            norm_fn=facade._norm,
            safe_int_fn=facade._safe_int,
            extract_json_fn=facade._extract_transcript_json_object,
            normalize_rows_fn=facade._normalize_transcript_rows,
            system_prompt=facade._UNIVERSAL_TRANSCRIPT_SYSTEM_PROMPT,
        )


class UniversalScheduleParserFacade(UniversalScheduleParserCore):
    def __init__(self) -> None:
        from core.ai_engine import ingest as facade

        super().__init__(
            model_name=str(os.environ.get("SCHEDULE_LLM_MODEL", "google/gemini-2.5-flash-lite")).strip(),
            timeout=int(os.environ.get("SCHEDULE_LLM_TIMEOUT", "45") or 45),
            max_retries=int(os.environ.get("SCHEDULE_LLM_MAX_RETRIES", "1") or 1),
            max_pages=int(os.environ.get("SCHEDULE_LLM_MAX_PAGES", "12") or 12),
            max_rows=int(os.environ.get("SCHEDULE_LLM_MAX_ROWS", "2500") or 2500),
            chat_openai_cls=facade.ChatOpenAI,
            system_message_cls=facade.SystemMessage,
            human_message_cls=facade.HumanMessage,
            norm_fn=facade._norm,
            safe_int_fn=facade._safe_int,
            extract_json_fn=facade._extract_schedule_json_object,
            normalize_rows_fn=facade._normalize_schedule_rows,
            system_prompt=facade._UNIVERSAL_SCHEDULE_SYSTEM_PROMPT,
        )

