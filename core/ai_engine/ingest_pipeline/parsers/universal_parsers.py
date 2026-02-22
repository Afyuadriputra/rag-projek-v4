from typing import Any, Callable, Dict, List, Optional


class UniversalTranscriptParserCore:
    def __init__(
        self,
        *,
        model_name: str,
        timeout: int,
        max_retries: int,
        max_pages: int,
        max_rows: int,
        chat_openai_cls: Any,
        system_message_cls: Any,
        human_message_cls: Any,
        norm_fn: Callable[[Any], str],
        safe_int_fn: Callable[[Any], Optional[int]],
        extract_json_fn: Callable[[str], Optional[Dict[str, Any]]],
        normalize_rows_fn: Callable[[List[Dict[str, Any]], Optional[int]], List[Dict[str, Any]]],
        system_prompt: str,
    ) -> None:
        self.model_name = str(model_name).strip()
        self.timeout = int(timeout)
        self.max_retries = int(max_retries)
        self.max_pages = int(max_pages)
        self.max_rows = int(max_rows)
        self._chat_openai_cls = chat_openai_cls
        self._system_message_cls = system_message_cls
        self._human_message_cls = human_message_cls
        self._norm = norm_fn
        self._safe_int = safe_int_fn
        self._extract_json = extract_json_fn
        self._normalize_rows = normalize_rows_fn
        self._system_prompt = system_prompt

    def _build_llm(self) -> Optional[Any]:
        if self._chat_openai_cls is None:
            return None
        import os

        api_key = self._norm(os.environ.get("OPENROUTER_API_KEY", ""))
        if not api_key:
            return None
        try:
            return self._chat_openai_cls(
                openai_api_key=api_key,
                openai_api_base="https://openrouter.ai/api/v1",
                model_name=self.model_name,
                temperature=0.0,
                request_timeout=self.timeout,
                max_retries=self.max_retries,
                default_headers={
                    "HTTP-Referer": "http://localhost:8000",
                    "X-Title": "AcademicChatbot-TranscriptParser",
                },
            )
        except Exception:
            return None

    def parse_pages(self, pages: List[Dict[str, Any]], source: str, fallback_semester: Optional[int] = None) -> Dict[str, Any]:
        llm = self._build_llm()
        if llm is None:
            return {"ok": False, "error": "llm_unavailable", "data_rows": [], "stats": {"pages": 0, "rows": 0}}

        prepared: List[str] = []
        for p in (pages or [])[: max(1, self.max_pages)]:
            page_no = self._safe_int(p.get("page")) or 0
            raw = self._norm(p.get("raw_text", ""))
            rough = self._norm(p.get("rough_table_text", ""))
            if not raw and not rough:
                continue
            prepared.append(f"[PAGE {page_no}]\nRAW_TEXT:\n{raw}\nROUGH_TABLE:\n{rough}")
        if not prepared:
            return {"ok": False, "error": "empty_page_payload", "data_rows": [], "stats": {"pages": 0, "rows": 0}}

        user_prompt = (
            "Output hanya JSON object valid, tanpa markdown dan tanpa teks tambahan.\n"
            "Jika tidak ada data, kembalikan {\"data_rows\": []}.\n"
            f"Source: {source}\n"
            f"Max rows: {self.max_rows}\n\n"
            "Data halaman:\n"
            + "\n\n".join(prepared)
        )
        try:
            if self._system_message_cls is not None and self._human_message_cls is not None:
                out = llm.invoke(
                    [
                        self._system_message_cls(content=self._system_prompt),
                        self._human_message_cls(content=user_prompt),
                    ]
                )
            else:
                out = llm.invoke(self._system_prompt + "\n\n" + user_prompt)
            content = out.content if hasattr(out, "content") else str(out)
            obj = self._extract_json(content if isinstance(content, str) else str(content))
            if not obj:
                return {"ok": False, "error": "invalid_json", "data_rows": [], "stats": {"pages": len(prepared), "rows": 0}}
            normalized = self._normalize_rows(obj.get("data_rows") or [], fallback_semester=fallback_semester)
            normalized = normalized[: max(1, self.max_rows)]
            return {
                "ok": True,
                "error": None,
                "data_rows": normalized,
                "stats": {"pages": len(prepared), "rows": len(normalized), "model": self.model_name},
            }
        except Exception as e:
            return {"ok": False, "error": f"llm_exception:{e}", "data_rows": [], "stats": {"pages": len(prepared), "rows": 0}}


class UniversalScheduleParserCore:
    def __init__(
        self,
        *,
        model_name: str,
        timeout: int,
        max_retries: int,
        max_pages: int,
        max_rows: int,
        chat_openai_cls: Any,
        system_message_cls: Any,
        human_message_cls: Any,
        norm_fn: Callable[[Any], str],
        safe_int_fn: Callable[[Any], Optional[int]],
        extract_json_fn: Callable[[str], Optional[Dict[str, Any]]],
        normalize_rows_fn: Callable[[List[Dict[str, Any]], Optional[int]], List[Dict[str, Any]]],
        system_prompt: str,
    ) -> None:
        self.model_name = str(model_name).strip()
        self.timeout = int(timeout)
        self.max_retries = int(max_retries)
        self.max_pages = int(max_pages)
        self.max_rows = int(max_rows)
        self._chat_openai_cls = chat_openai_cls
        self._system_message_cls = system_message_cls
        self._human_message_cls = human_message_cls
        self._norm = norm_fn
        self._safe_int = safe_int_fn
        self._extract_json = extract_json_fn
        self._normalize_rows = normalize_rows_fn
        self._system_prompt = system_prompt

    def _build_llm(self) -> Optional[Any]:
        if self._chat_openai_cls is None:
            return None
        import os

        api_key = self._norm(os.environ.get("OPENROUTER_API_KEY", ""))
        if not api_key:
            return None
        try:
            return self._chat_openai_cls(
                openai_api_key=api_key,
                openai_api_base="https://openrouter.ai/api/v1",
                model_name=self.model_name,
                temperature=0.0,
                request_timeout=self.timeout,
                max_retries=self.max_retries,
                default_headers={
                    "HTTP-Referer": "http://localhost:8000",
                    "X-Title": "AcademicChatbot-ScheduleParser",
                },
            )
        except Exception:
            return None

    def parse_pages(self, pages: List[Dict[str, Any]], source: str, fallback_semester: Optional[int] = None) -> Dict[str, Any]:
        llm = self._build_llm()
        if llm is None:
            return {"ok": False, "error": "llm_unavailable", "data_rows": [], "stats": {"pages": 0, "rows": 0}}

        prepared: List[str] = []
        for p in (pages or [])[: max(1, self.max_pages)]:
            page_no = self._safe_int(p.get("page")) or 0
            raw = self._norm(p.get("raw_text", ""))
            rough = self._norm(p.get("rough_table_text", ""))
            if not raw and not rough:
                continue
            prepared.append(f"[PAGE {page_no}]\nRAW_TEXT:\n{raw}\nROUGH_TABLE:\n{rough}")
        if not prepared:
            return {"ok": False, "error": "empty_page_payload", "data_rows": [], "stats": {"pages": 0, "rows": 0}}

        user_prompt = (
            "Output hanya JSON object valid, tanpa markdown dan tanpa teks tambahan.\n"
            "Jika tidak ada data, kembalikan {\"data_rows\": []}.\n"
            f"Source: {source}\n"
            f"Max rows: {self.max_rows}\n\n"
            "Data halaman:\n"
            + "\n\n".join(prepared)
        )
        try:
            if self._system_message_cls is not None and self._human_message_cls is not None:
                out = llm.invoke(
                    [
                        self._system_message_cls(content=self._system_prompt),
                        self._human_message_cls(content=user_prompt),
                    ]
                )
            else:
                out = llm.invoke(self._system_prompt + "\n\n" + user_prompt)
            content = out.content if hasattr(out, "content") else str(out)
            obj = self._extract_json(content if isinstance(content, str) else str(content))
            if not obj:
                return {"ok": False, "error": "invalid_json", "data_rows": [], "stats": {"pages": len(prepared), "rows": 0}}
            normalized = self._normalize_rows(obj.get("data_rows") or [], fallback_semester=fallback_semester)
            normalized = normalized[: max(1, self.max_rows)]
            return {
                "ok": True,
                "error": None,
                "data_rows": normalized,
                "stats": {"pages": len(prepared), "rows": len(normalized), "model": self.model_name},
            }
        except Exception as e:
            return {"ok": False, "error": f"llm_exception:{e}", "data_rows": [], "stats": {"pages": len(prepared), "rows": 0}}

